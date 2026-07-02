import sys
import os

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import JSONResponse
from fastapi.concurrency import run_in_threadpool

# Ensure parent directory is in sys.path
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from orchestrator import IncidentOrchestrator
from database import update_playbook_steps, resolve_incident

router = APIRouter()

# Instantiate single global orchestrator instance
orchestrator = IncidentOrchestrator(logs_dir=os.path.join(_REPO_ROOT, "..", "logs"))


class ConnectionManager:
    def __init__(self) -> None:
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict) -> None:
        dead: list[WebSocket] = []
        for connection in list(self.active_connections):
            try:
                await connection.send_json(message)
            except Exception:  # noqa: BLE001
                dead.append(connection)
        for ws in dead:
            try:
                self.active_connections.remove(ws)
            except ValueError:
                pass


manager = ConnectionManager()


@router.get("/health")
async def health():
    return JSONResponse(content={"status": "ok"})


@router.post("/ingest")
async def ingest(payload: dict):
    source = payload.get("source") if isinstance(payload, dict) else None
    result = orchestrator.start_pipeline(source=source)
    await manager.broadcast(result)
    return JSONResponse(content=result)


@router.get("/incidents")
async def list_incidents():
    # Run blocking database reads in the thread pool to keep the asyncio event loop free
    incidents = await run_in_threadpool(lambda: orchestrator.incidents_store)
    return JSONResponse(content=incidents)


@router.post("/incidents/{incident_id}/steps")
async def update_steps(incident_id: int, payload: dict):
    steps = payload.get("steps_executed", [])
    try:
        # Run blocking database writes in the thread pool
        updated = await run_in_threadpool(update_playbook_steps, incident_id, steps, orchestrator.db_path)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    await manager.broadcast(updated)
    return JSONResponse(content=updated)


@router.post("/incidents/{incident_id}/resolve")
async def resolve(incident_id: int):
    try:
        # Run blocking database writes in the thread pool
        updated = await run_in_threadpool(resolve_incident, incident_id, orchestrator.db_path)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    await manager.broadcast(updated)
    return JSONResponse(content=updated)


@router.websocket("/ws/incidents")
async def ws_incidents(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        # Always disconnect cleanly, catching any other network/protocol exceptions
        manager.disconnect(websocket)
