"""
REST and WebSocket endpoints for MidiMate integration.

Acepta ambos formatos de cable (`event`/`data` y `type`/`payload`) y emite
siempre ambos alias, con `sequence` consecutivo por conexión y `event_id`.
"""
import asyncio
import json
import logging
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from ws_server import Envelope, hub

logger = logging.getLogger("midiforja.api.midimate")
router = APIRouter(prefix="/api/midimate", tags=["midimate"])


class NoteEvent(BaseModel):
    pitch: int = Field(..., ge=0, le=127)
    velocity: int = Field(100, ge=0, le=127)
    channel: int = Field(0, ge=0, le=15)
    timestamp: float = Field(default_factory=time.time)
    request_id: Optional[str] = None
    idempotency_key: Optional[str] = None


class TransportCommand(BaseModel):
    action: str = Field(..., pattern="^(play|stop|pause|seek|loop)$")
    position: float = Field(0.0, ge=0.0)
    loop: bool = False
    request_id: Optional[str] = None
    idempotency_key: Optional[str] = None


class MidiLoadRequest(BaseModel):
    url: Optional[str] = None
    filename: Optional[str] = None
    tracks: Optional[List[Dict[str, Any]]] = None


class StateResponse(BaseModel):
    playing: bool
    position: float
    tempo: int
    current_file: Optional[str]
    note_count: int
    duration: float
    tracks: List[Dict[str, Any]]
    loop: bool
    volume: int


def wire_event(msg: Dict[str, Any]):
    """Devuelve (nombre, payload) aceptando los dos formatos de cable."""
    name = msg.get("type") or msg.get("event") or ""
    payload = msg.get("payload", msg.get("data", {}))
    return name, payload or {}


def make_envelope(event_name: str, payload: Any) -> Envelope:
    return Envelope(type=event_name, payload=payload)


# --- REST endpoints --------------------------------------------------------

@router.get("/state", response_model=StateResponse)
async def get_state():
    return hub.get_state()


@router.post("/transport")
async def transport(cmd: TransportCommand):
    changed = {}
    if cmd.action == "play":
        changed = hub.update_state(playing=True)
    elif cmd.action == "stop":
        changed = hub.update_state(playing=False, position=0.0)
    elif cmd.action == "pause":
        changed = hub.update_state(playing=False)
    elif cmd.action == "seek":
        changed = hub.update_state(position=cmd.position)
    elif cmd.action == "loop":
        changed = hub.update_state(loop=cmd.loop)

    await hub.broadcast(make_envelope(f"transport_{cmd.action}", {
        "source": "api", "changed": changed,
    }))
    return {"ok": True, "state": hub.get_state(), "changed": changed}


@router.post("/note")
async def note(event: NoteEvent):
    action = "note_on" if event.velocity > 0 else "note_off"
    await hub.broadcast(make_envelope(action, {
        "pitch": event.pitch,
        "velocity": event.velocity,
        "channel": event.channel,
        "timestamp": event.timestamp,
    }))
    return {"ok": True}


@router.post("/midi/load")
async def load_midi(req: MidiLoadRequest):
    hub.update_state(
        current_file=req.filename,
        tracks=req.tracks or [],
        playing=False,
        position=0.0,
    )
    await hub.broadcast(make_envelope("midi_loaded", {
        "filename": req.filename, "tracks": req.tracks,
    }))
    return {"ok": True, "state": hub.get_state()}


@router.get("/connections")
async def connections():
    return hub.get_connections_info()


@router.get("/stats")
async def stats():
    return hub.get_stats()


# --- WebSocket -------------------------------------------------------------

@router.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    await websocket.accept()
    cid = None
    try:
        raw = await asyncio.wait_for(websocket.receive_text(), timeout=10.0)
        hello = json.loads(raw)
        payload = hello.get("payload", hello.get("data", hello))
        if not isinstance(payload, dict):
            payload = {}
        cid = payload.get("client_id") or hello.get("client_id") or f"client_{int(time.time())}"
        ctype = payload.get("client_type") or hello.get("client_type") or "unknown"
    except (asyncio.TimeoutError, ValueError, TypeError) as exc:
        logger.info("WS handshake fallback: %s", exc)
        cid, ctype = f"client_{int(time.time())}", "unknown"
    except Exception as exc:
        logger.warning("WS handshake failed: %s", exc)
        await websocket.close(code=1008)
        return

    await hub.register(cid, ctype, websocket)

    try:
        while True:
            raw = await asyncio.wait_for(websocket.receive_text(), timeout=35.0)
            msg = json.loads(raw)
            if not isinstance(msg, dict):
                continue
            event, payload = wire_event(msg)
            eid = msg.get("event_id") or ""
            hub.touch(cid)

            if event in ("ping", "heartbeat"):
                await hub.send_to(cid, make_envelope("pong", {
                    "ts": time.time(), "echo": payload.get("ts"),
                }))
                continue
            if event == "pong":
                continue
            if event == "state_request":
                await hub.send_to(cid, make_envelope("state_response", hub.get_state()))
                continue
            if event == "state_update":
                changed = hub.update_state(**payload)
                await hub.broadcast(make_envelope("state_update", {
                    **payload, "_changed": changed,
                }))
                continue

            if event in ("note_on", "note_off"):
                if eid and hub.is_duplicate(eid):
                    continue
                if eid:
                    hub.mark_seen(eid)
                await hub.broadcast(make_envelope(event, payload), exclude=cid)
                continue

            if event.startswith("transport_"):
                action = event.replace("transport_", "")
                if action == "play":
                    hub.update_state(playing=True)
                elif action == "stop":
                    hub.update_state(playing=False, position=0.0)
                elif action == "pause":
                    hub.update_state(playing=False)
                if eid and hub.is_duplicate(eid):
                    continue
                if eid:
                    hub.mark_seen(eid)
                await hub.broadcast(make_envelope(event, payload), exclude=cid)

    except (asyncio.TimeoutError, WebSocketDisconnect):
        logger.info("WS closed: %s", cid)
    except Exception as exc:
        logger.warning("WS error %s: %s", cid, exc)
    finally:
        await hub.unregister(cid, reason="disconnect", ws=websocket)
