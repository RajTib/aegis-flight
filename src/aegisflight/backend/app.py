"""FastAPI backend for the AegisFlight dashboard.

Exposes REST control/status endpoints and a WebSocket that streams live
telemetry + threat assessments from the :class:`LiveEngine`. If a built
frontend exists at ``frontend/dist`` it is served at ``/`` so ``aegis serve``
hosts the whole app; otherwise ``/`` returns a small JSON banner.

Every payload carries ``sim: true`` — the dashboard must always show this is a
simulation, never a real airframe.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .. import __version__
from ..attacks import ATTACK_REGISTRY
from ..config import load_config
from .engine import LiveEngine

engine: LiveEngine | None = None


def get_engine() -> LiveEngine:
    global engine
    if engine is None:
        engine = LiveEngine()
    return engine


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    get_engine().start()  # auto-start the live simulation
    yield
    if engine is not None:
        engine.stop()


app = FastAPI(title="AegisFlight IDS", version=__version__, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # local demo only
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------------------------------- #
# REST API
# --------------------------------------------------------------------------- #
@app.get("/health")
def health() -> dict:
    return {"status": "ok", "version": __version__, "sim": True}


@app.get("/api/status")
def status() -> dict:
    return get_engine().status()


@app.get("/api/metrics")
def metrics() -> dict:
    return get_engine().metrics()


@app.get("/api/events")
def events(limit: int = 50) -> dict:
    eng = get_engine()
    return {"events": eng.recent_alerts(limit), "run_id": eng._run_id}


@app.get("/api/config")
def config() -> dict:
    cfg = load_config()
    det = cfg.detector
    return {
        "attacks": sorted(ATTACK_REGISTRY.keys()),
        "decision_rate_hz": det.get("decision_rate_hz"),
        "sample_rate_hz": cfg.simulation.get("sample_rate_hz"),
        "fusion": {
            "threat_threshold": det["fusion"]["threat_threshold"],
            "weights": det["fusion"]["weights"],
            "severity_bands": det["fusion"]["severity_bands"],
        },
        "home": cfg.simulation.get("home"),
    }


@app.post("/api/simulation/start")
def sim_start() -> dict:
    get_engine().start()
    return {"ok": True, "running": True}


@app.post("/api/simulation/stop")
def sim_stop() -> dict:
    get_engine().stop()
    return {"ok": True, "running": False}


@app.post("/api/simulation/reset")
def sim_reset() -> dict:
    eng = get_engine()
    eng.reset()
    eng.start()
    return {"ok": True, "reset": True}


@app.post("/api/simulation/attack")
def sim_attack(payload: dict) -> JSONResponse:
    name = (payload or {}).get("attack")
    if name and name not in ATTACK_REGISTRY and name not in ("none", "benign"):
        return JSONResponse(
            status_code=400,
            content={"ok": False, "error": f"unknown attack '{name}'",
                     "choices": sorted(ATTACK_REGISTRY.keys())},
        )
    get_engine().set_attack(name)
    return JSONResponse(content={"ok": True, "attack": name or "cleared"})


# --------------------------------------------------------------------------- #
# WebSocket — live telemetry + threat stream
# --------------------------------------------------------------------------- #
@app.websocket("/ws/telemetry")
async def ws_telemetry(ws: WebSocket) -> None:
    await ws.accept()
    eng = get_engine()
    q = eng.subscribe()
    try:
        while True:
            msg = await q.get()
            await ws.send_json(msg)
    except WebSocketDisconnect:
        pass
    except Exception:  # noqa: BLE001 - client vanished mid-send
        pass
    finally:
        eng.unsubscribe(q)
        with contextlib.suppress(Exception):
            await ws.close()


# --------------------------------------------------------------------------- #
# Static frontend (if built)
# --------------------------------------------------------------------------- #
_DIST = Path(__file__).resolve().parents[3] / "frontend" / "dist"
if _DIST.exists():
    app.mount("/", StaticFiles(directory=str(_DIST), html=True), name="frontend")
else:
    @app.get("/")
    def root() -> dict:
        return {
            "name": "AegisFlight IDS",
            "version": __version__,
            "sim": True,
            "note": "frontend not built; run `npm --prefix frontend install && "
                    "npm --prefix frontend run build`, or use the dev server",
            "endpoints": ["/health", "/api/status", "/api/metrics", "/api/events",
                          "/api/config", "/ws/telemetry"],
        }
