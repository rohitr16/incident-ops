import os
import sys
import threading

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

_REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
# Support both:
#  - `uvicorn backend.main:app --app-dir /repo`
#  - imports from project root with repo root on sys.path
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from api.routes import router as api_router, orchestrator

app = FastAPI(title="Incident Dashboard API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)

# Shared orchestrator instance imported from api.routes


def _maybe_mount_static() -> None:
    static_dir = os.path.join(_REPO_ROOT, "..", "frontend", ".next", "static")
    if os.path.isdir(static_dir):
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="frontend-static")


async def start_pg_listener():
    import asyncpg
    import json
    import asyncio
    from database import is_postgres, _get_incident_by_id
    from services.graph import run_langgraph_pipeline
    from api.routes import manager, orchestrator
    
    db_path = orchestrator.db_path
    
    try:
        # Connect to PostgreSQL
        conn = await asyncpg.connect(db_path)
        
        # Define callback for incident NOTIFY events
        def listener_callback(connection, pid, channel, payload):
            try:
                incident_id = int(payload)
                print(f"[POSTGRES] Received notification: new incident_id={incident_id}", flush=True)
                
                async def run_pipeline_bg():
                    try:
                        # Re-fetch the incident details
                        incident = _get_incident_by_id(incident_id, db_path)
                        raw_line = incident.get("raw_line") or ""
                        detection = incident.get("detection") or {}
                        severity = detection.get("severity", "ERROR")
                        
                        await run_langgraph_pipeline(
                            incident_id,
                            raw_line,
                            severity,
                            db_path,
                            manager.broadcast,
                            orchestrator.llm_service
                        )
                    except Exception as ex:
                        print(f"[POSTGRES] Error running pipeline for incident {incident_id}: {ex}", flush=True)
                        
                asyncio.create_task(run_pipeline_bg())
            except Exception as cb_err:
                print(f"[POSTGRES] Callback error: {cb_err}", flush=True)
                
        await conn.add_listener('incident_new', listener_callback)
        print("[POSTGRES] Listening for 'incident_new' notifications...", flush=True)
        
        # Reconciliation: process pending incidents on startup
        try:
            rows = await conn.fetch("SELECT incident_id, raw_line, detection FROM incidents WHERE resolution_status = 'pending'")
            print(f"[POSTGRES] Startup reconciliation: found {len(rows)} pending incidents.", flush=True)
            for row in rows:
                inc_id = row["incident_id"]
                raw_line = row["raw_line"]
                det = json.loads(row["detection"]) if isinstance(row["detection"], str) else row["detection"]
                severity = det.get("severity", "ERROR")
                
                print(f"[RECONCILE] Launching pipeline for incident {inc_id}", flush=True)
                asyncio.create_task(
                    run_langgraph_pipeline(
                        inc_id,
                        raw_line or "",
                        severity,
                        db_path,
                        manager.broadcast,
                        orchestrator.llm_service
                    )
                )
        except Exception as rec_err:
            print(f"[RECONCILE] Error during startup reconciliation: {rec_err}", flush=True)
            
        # Keep listener active
        while True:
            await asyncio.sleep(3600)
    except Exception as e:
        print(f"[POSTGRES] Error starting asyncpg listener: {e}. Reconnecting in 5s...", flush=True)
        await asyncio.sleep(5.0)
        asyncio.create_task(start_pg_listener())


@app.on_event("startup")
async def on_startup():
    _maybe_mount_static()
    import asyncio
    from database import is_postgres
    from api.routes import manager
    
    if is_postgres(orchestrator.db_path):
        asyncio.create_task(start_pg_listener())
    else:
        loop = asyncio.get_event_loop()
        
        def _bg():
            import sys
            from concurrent.futures import ThreadPoolExecutor
            executor = ThreadPoolExecutor(max_workers=5)
            
            for filename, line in orchestrator.collector.watch():
                def run_job(f_name, l_content):
                    try:
                        result = orchestrator.start_pipeline(source=f_name, raw_line=l_content)
                        asyncio.run_coroutine_threadsafe(manager.broadcast(result), loop)
                    except Exception as e:
                        print(f"Error processing background log line: {e}", file=sys.stderr)
                executor.submit(run_job, filename, line)
                
        threading.Thread(target=_bg, daemon=True).start()


@app.on_event("shutdown")
async def on_shutdown():
    pass


def create_app() -> FastAPI:
    return app
