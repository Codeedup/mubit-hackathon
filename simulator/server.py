"""
Robot telemetry simulator - FastAPI server.

Endpoints
---------
GET  /                 Interactive dashboard (static/index.html)
WS   /ws/telemetry     <-- LISTENERS CONNECT HERE. Receives telemetry packets at
                       `rate_hz`; send {"type": "command", ...} messages back to
                       fix the robot. Optional query param ?name=my-listener
WS   /ws/ui            Dashboard channel (state + sim controls). Not for listeners.
GET  /api/schema       Every telemetry field, command and fault, documented.
GET  /api/packet       The latest telemetry packet.
POST /api/command      Send a robot command over HTTP (same format as over WS).

Run:  python -m simulator.server   (or: uvicorn simulator.server:app)
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import random
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .protocol import schema
from .robot import Robot

STATIC = Path(__file__).parent / "static"
UI_HZ = 20.0


class Hub:
    """Owns the robot, runs the real-time loop and fans out messages."""

    def __init__(self) -> None:
        self.robot = Robot()
        self.listeners: dict[WebSocket, dict[str, Any]] = {}
        self.uis: set[WebSocket] = set()
        self.last_packet: dict[str, Any] | None = None
        self.stats = {"sent": 0, "dropped": 0, "commands": 0}
        self._last_event_sent = 0

    # ------------------------------------------------------------------ loop
    async def run(self) -> None:
        r = self.robot
        dt = r.PHYS_DT
        last = time.perf_counter()
        acc = 0.0
        next_tx = 0.0
        next_ui = 0.0
        while True:
            await asyncio.sleep(0.005)
            now = time.perf_counter()
            elapsed, last = min(now - last, 0.25), now  # cap catch-up after stalls
            if r.running:
                acc += elapsed
                while acc >= dt:
                    r.step(dt)
                    acc -= dt
            if now >= next_tx:
                next_tx = now + 1.0 / r.comms["rate_hz"]
                if r.running:
                    await self._send_telemetry()
            if now >= next_ui:
                next_ui = now + 1.0 / UI_HZ
                await self._send_ui()

    async def _send_telemetry(self) -> None:
        pkt = self.robot.build_packet()
        if pkt is None:  # MCU rebooting -> silence on the link
            return
        self.last_packet = pkt
        if random.random() * 100 < self.robot.effective_packet_loss():
            self.stats["dropped"] += 1
            return
        self.stats["sent"] += 1
        await self._broadcast(list(self.listeners), json.dumps(pkt), self.listeners)

    async def _send_ui(self) -> None:
        if not self.uis:
            return
        r = self.robot
        events = [e for e in r.events if e["id"] > self._last_event_sent]
        if events:
            self._last_event_sent = events[-1]["id"]
        msg = {
            "type": "state",
            "state": r.ui_state(),
            "events": events,
            "packet": self.last_packet,
            "listeners": [{"name": v["name"], "addr": v["addr"], "commands": v["commands"]} for v in self.listeners.values()],
            "stats": self.stats,
        }
        await self._broadcast(list(self.uis), json.dumps(msg), self.uis)

    @staticmethod
    async def _broadcast(sockets: list[WebSocket], text: str, registry: Any) -> None:
        async def send(ws: WebSocket) -> None:
            try:
                await asyncio.wait_for(ws.send_text(text), timeout=1.0)
            except Exception:
                if isinstance(registry, dict):
                    registry.pop(ws, None)
                else:
                    registry.discard(ws)

        await asyncio.gather(*(send(ws) for ws in sockets))

    # ------------------------------------------------------------------ commands
    def handle_command(self, msg: dict[str, Any], source: str) -> dict[str, Any]:
        ok, message = self.robot.apply_command(msg, source)
        self.stats["commands"] += 1
        return {"type": "ack", "id": msg.get("id"), "ok": ok, "message": message}


hub = Hub()


@contextlib.asynccontextmanager
async def lifespan(_: FastAPI):
    task = asyncio.create_task(hub.run())
    yield
    task.cancel()


app = FastAPI(title="Robot Telemetry Simulator", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/api/schema")
async def api_schema() -> JSONResponse:
    return JSONResponse(schema())


@app.get("/api/packet")
async def api_packet() -> JSONResponse:
    return JSONResponse(hub.last_packet or {})


@app.post("/api/command")
async def api_command(msg: dict[str, Any]) -> JSONResponse:
    if msg.get("kind") == "sim" or msg.get("action") in ("inject_fault", "clear_fault", "clear_all_faults", "set", "pause", "reset"):
        ok, m = hub.robot.apply_sim(msg)
        return JSONResponse({"type": "ack", "id": msg.get("id"), "ok": ok, "message": m})
    return JSONResponse(hub.handle_command(msg, "http"))


@app.post("/api/sim")
async def api_sim(msg: dict[str, Any]) -> JSONResponse:
    ok, m = hub.robot.apply_sim(msg)
    return JSONResponse({"type": "ack", "id": msg.get("id"), "ok": ok, "message": m})


@app.websocket("/ws/telemetry")
async def ws_telemetry(ws: WebSocket) -> None:
    await ws.accept()
    name = ws.query_params.get("name") or f"listener-{random.randint(100, 999)}"
    addr = f"{ws.client.host}:{ws.client.port}" if ws.client else "?"
    info = {"name": name, "addr": addr, "commands": 0}
    await ws.send_text(json.dumps({
        "type": "hello",
        "robot_id": hub.robot.ROBOT_ID,
        "schema": "robot.telemetry.v1",
        "rate_hz": hub.robot.comms["rate_hz"],
        "message": "Telemetry packets will follow. Send {'type':'command','target':...,'action':...,'value':...,'reason':...} to act. "
                   "Full docs: GET /api/schema",
    }))
    hub.listeners[ws] = info
    hub.robot.log("sim", "system", f"Listener '{name}' connected ({addr})")
    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
                if not isinstance(msg, dict):
                    raise ValueError("message must be a JSON object")
            except ValueError as e:
                await ws.send_text(json.dumps({"type": "ack", "ok": False, "message": f"bad JSON: {e}"}))
                continue
            mtype = msg.get("type", "command")
            if mtype == "command":
                info["commands"] += 1
                await ws.send_text(json.dumps(hub.handle_command(msg, name)))
            elif mtype == "note":  # free-text diagnosis shown in the dashboard log
                hub.robot.log(name, "note", str(msg.get("text", ""))[:300])
            elif mtype == "ping":
                await ws.send_text(json.dumps({"type": "pong", "id": msg.get("id")}))
            else:
                await ws.send_text(json.dumps({"type": "ack", "id": msg.get("id"), "ok": False,
                                               "message": f"unknown type '{mtype}' (use command | note | ping)"}))
    except WebSocketDisconnect:
        pass
    finally:
        hub.listeners.pop(ws, None)
        hub.robot.log("sim", "system", f"Listener '{name}' disconnected")


@app.websocket("/ws/ui")
async def ws_ui(ws: WebSocket) -> None:
    await ws.accept()
    hub.uis.add(ws)
    await ws.send_text(json.dumps({"type": "events_backlog", "events": list(hub.robot.events)}))
    try:
        while True:
            msg = json.loads(await ws.receive_text())
            kind = msg.pop("kind", None)
            if kind == "command":
                res = hub.handle_command(msg, "dashboard")
            elif kind == "sim":
                ok, m = hub.robot.apply_sim(msg)
                res = {"type": "ack", "ok": ok, "message": m}
            else:
                res = {"type": "ack", "ok": False, "message": "unknown kind"}
            if not res["ok"]:
                await ws.send_text(json.dumps({"type": "error", "message": res["message"]}))
            else:
                await hub._send_ui()
    except (WebSocketDisconnect, json.JSONDecodeError):
        pass
    finally:
        hub.uis.discard(ws)


def main() -> None:
    import uvicorn

    p = argparse.ArgumentParser(description="Robot telemetry simulator")
    p.add_argument("--host", default="0.0.0.0", help="0.0.0.0 = reachable by teammates on the same network")
    p.add_argument("--port", type=int, default=8000)
    a = p.parse_args()
    print(f"\n  Dashboard:  http://localhost:{a.port}\n  Listeners:  ws://<this-machine-ip>:{a.port}/ws/telemetry\n")
    uvicorn.run(app, host=a.host, port=a.port, log_level="warning")


if __name__ == "__main__":
    main()
