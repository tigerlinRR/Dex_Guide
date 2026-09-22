"""FastAPI backend — the operator's web control console + live state push.

REST:  POST /api/start /next /stop /estop /clear, POST /api/goto/{id}.
Live:  WebSocket /ws — the engine broadcasts a snapshot on every state change, and the
       page refreshes from it.
Static: GET / returns guide/web/index.html (responsive, works on phone and desktop).

The hardware backend is chosen by the GUIDE_BACKEND env var:
  sim (default) — touches no robot, runs the flow on a dev machine.
  real          — wired to the robot (must be on the Jetson, and real.py must be wired).
"""
from __future__ import annotations

import os

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse

from guide.config import DEFAULT_CONFIG, load_stations
from guide.engine import TourEngine

WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")


def _make_hardware(backend: str):
    if backend == "real":
        from guide.hardware.real import RealArm, RealAudio, RealChassis, RealHand
        host = os.environ.get("GUIDE_CHASSIS_HOST", "192.168.12.131")
        return RealChassis(host), RealArm(), RealHand(), RealAudio()
    from guide.hardware.sim import SimArm, SimAudio, SimChassis, SimHand
    return SimChassis(), SimArm(), SimHand(), SimAudio()


class Hub:
    """Keeps all WebSocket connections and broadcasts engine state."""

    def __init__(self):
        self.clients: set[WebSocket] = set()

    async def broadcast(self, snapshot: dict) -> None:
        dead = []
        for ws in self.clients:
            try:
                await ws.send_json(snapshot)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.clients.discard(ws)


def create_app() -> FastAPI:
    app = FastAPI(title="Dex Guide Console")
    hub = Hub()
    backend = os.environ.get("GUIDE_BACKEND", "sim")
    stations = load_stations(os.environ.get("GUIDE_STATIONS", DEFAULT_CONFIG))
    chassis, arm, hand, audio = _make_hardware(backend)
    engine = TourEngine(stations, chassis, arm, hand, audio,
                        on_change=hub.broadcast)
    app.state.engine = engine
    app.state.backend = backend

    @app.get("/")
    async def index():
        return FileResponse(os.path.join(WEB_DIR, "index.html"))

    @app.get("/api/state")
    async def state():
        return JSONResponse({**engine.snapshot(), "backend": backend})

    @app.post("/api/start")
    async def start():
        await engine.start()
        return {"ok": True}

    @app.post("/api/next")
    async def nxt():
        await engine.next()
        return {"ok": True}

    @app.post("/api/stop")
    async def stop():
        await engine.stop_tour()
        return {"ok": True}

    @app.post("/api/estop")
    async def estop():
        await engine.estop()
        return {"ok": True}

    @app.post("/api/clear")
    async def clear():
        await engine.clear_estop()
        return {"ok": True}

    @app.post("/api/goto/{station_id}")
    async def goto(station_id: str):
        await engine.goto(station_id)
        return {"ok": True}

    @app.websocket("/ws")
    async def ws(websocket: WebSocket):
        await websocket.accept()
        hub.clients.add(websocket)
        await websocket.send_json({**engine.snapshot(), "backend": backend})
        try:
            while True:
                await websocket.receive_text()   # keep-alive; commands go over REST
        except WebSocketDisconnect:
            hub.clients.discard(websocket)

    return app


app = create_app()
