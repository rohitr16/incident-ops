import sys

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from orchestrator import IncidentOrchestrator

router = APIRouter()

orchestrator = IncidentOrchestrator(logs_dir="logs")


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
    return JSONResponse(content=orchestrator.incidents_store)


@router.websocket("/ws/incidents")
async def ws_incidents(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
