"""
REST API and WebSocket endpoints for MidiMate integration.

Wire format: {event: "...", data: {...}}
Internal: Envelope(type, payload, event_id, sequence, timestamp)
"""
import json
import time
import asyncio
import logging
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from ws_server import hub, Envelope

logger = logging.getLogger("midiforja.api.midimate")
router = APIRouter(prefix="/api/midimate", tags=["midimate"])


class NoteEvent(BaseModel):
    pitch: int = Field(..., ge=0, le=127)
    velocity: int = Field(100, ge=0, le=127)
    channel: int = Field(0, ge=0, le=15)
    timestamp: float = Field(default_factory=time.time)


class TransportCommand(BaseModel):
    action: str = Field(..., pattern="^(play|stop|pause|seek|loop)$")
    position: float = Field(0.0, ge=0.0)
    loop: bool = False


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


# --- Helpers to adapt wire format <-> Envelope ---

def make_envelope(event_name: str, payload: Any) -> Envelope:
    return Envelope(type=event_name, payload=payload)


# --- REST Endpoints ---

@router.get("/state", response_model=StateResponse)
async def get_state():
    return hub.get_state()


@router.post("/transport")
async def transport(cmd: TransportCommand):
    action = cmd.action
    changed = {}
    if action == "play":
        changed = hub.update_state(playing=True)
    elif action == "stop":
        changed = hub.update_state(playing=False, position=0.0)
    elif action == "pause":
        changed = hub.update_state(playing=False)
    elif action == "seek":
        changed = hub.update_state(position=cmd.position)
    elif action == "loop":
        changed = hub.update_state(loop=cmd.loop)

    await hub.broadcast(make_envelope(f"transport_{action}", {
        "source": "api",
        "changed": changed,
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
        "filename": req.filename,
        "tracks": req.tracks,
    }))
    return {"ok": True, "state": hub.get_state()}


@router.get("/connections")
async def connections():
    return hub.get_connections_info()


@router.get("/stats")
async def stats():
    return hub.get_stats()


# --- WebSocket ---

@router.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    await websocket.accept()

    # Handshake
    try:
        raw = await asyncio.wait_for(websocket.receive_text(), timeout=5.0)
        hs = json.loads(raw)
        cid = hs.get("client_id", f"client_{int(time.time())}")
        ctype = hs.get("client_type", "unknown")
    except asyncio.TimeoutError:
        cid, ctype = f"client_{int(time.time())}", "unknown"
    except Exception as e:
        logger.warning(f"Handshake failed: {e}")
        await websocket.close(code=1008)
        return

    conn = await hub.register(cid, ctype, websocket)

    try:
        while True:
            raw = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
            msg = json.loads(raw)
            event = msg.get("event", "")
            payload = msg.get("data", {})

            if event == "ping":
                await hub.send_to(cid, Envelope(type="pong", payload={"ts": time.time()}))
            elif event == "state_request":
                await hub.send_to(cid, Envelope(type="state_response", payload=hub.get_state()))
            elif event == "state_update":
                changed = hub.update_state(**payload)
                await hub.broadcast(Envelope(type="state_update", payload={**payload, "_changed": changed}))
            elif event in ("note_on", "note_off"):
                if not hub.is_duplicate(msg.get("event_id", "")):
                    hub.mark_seen(msg.get("event_id", ""))
                    await hub.broadcast(make_envelope(event, payload), exclude=cid)
            elif event.startswith("transport_"):
                action = event.replace("transport_", "")
                if action == "play":
                    hub.update_state(playing=True)
                elif action == "stop":
                    hub.update_state(playing=False, position=0.0)
                elif action == "pause":
                    hub.update_state(playing=False)
                await hub.broadcast(make_envelope(event, payload), exclude=cid)

    except asyncio.TimeoutError:
        logger.info(f"WS timeout: {cid}")
    except WebSocketDisconnect:
        logger.info(f"WS disconnect: {cid}")
    except Exception as e:
        logger.warning(f"WS error {cid}: {e}")
    finally:
        await hub.unregister(cid)

