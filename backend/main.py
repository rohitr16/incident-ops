import os
import sys
import threading

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

_REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
# Support both:
#  - `uvicorn backend.main:app --app-dir /repo`
#  - imports from project root with repo root on sys.path
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from api.routes import router as api_router
from orchestrator import IncidentOrchestrator

app = FastAPI(title="Incident Dashboard API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)

orchestrator = IncidentOrchestrator(logs_dir=os.path.join(_REPO_ROOT, "..", "logs"))


def _maybe_mount_static() -> None:
    static_dir = os.path.join(_REPO_ROOT, "..", "frontend", ".next", "static")
    if os.path.isdir(static_dir):
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="frontend-static")


@app.on_event("startup")
async def on_startup():
    _maybe_mount_static()
    def _bg():
        for _ in orchestrator.collector.watch():
            pass
    threading.Thread(target=_bg, daemon=True).start()


@app.on_event("shutdown")
async def on_shutdown():
    pass


def create_app() -> FastAPI:
    return app
