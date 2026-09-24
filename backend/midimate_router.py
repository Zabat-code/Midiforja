"""
REST API and WebSocket endpoints for MidiMate integration.

These endpoints allow MidiMate (browser) and Hernesto (Linux/PC)
to control and query the Midiforja backend in real time.
"""
import json
import time
import asyncio
import logging
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from ws_server import hub

logger = logging.getLogger("midiforja.api.midimate")
router = APIRouter(prefix="/api/midimate", tags=["midimate"])

# --- Pydantic models ---

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

# --- REST Endpoints ---

@router.get("/state", response_model=StateResponse)
async def get_state():
    """Get current playback state."""
    return hub.get_state()

@router.post("/transport")
async def transport_control(cmd: TransportCommand):
    """Control playback (play/stop/pause/seek/loop)."""
    changed = {}
    if cmd.action == "play":
        changed = hub.update_state(playing=True)
        await hub.broadcast("transport_play", {"source": "api"})
    elif cmd.action == "stop":
        changed = hub.update_state(playing=False, position=0.0)
        await hub.broadcast("transport_stop", {"source": "api"})
    elif cmd.action == "pause":
        changed = hub.update_state(playing=False)
        await hub.broadcast("transport_pause", {"source": "api"})
    elif cmd.action == "seek":
        changed = hub.update_state(position=cmd.position)
        await hub.broadcast("transport_seek", {"position": cmd.position, "source": "api"})
    elif cmd.action == "loop":
        changed = hub.update_state(loop=cmd.loop)
        await hub.broadcast("transport_loop", {"loop": cmd.loop, "source": "api"})
    return {"ok": True, "state": hub.get_state(), "changed": changed}

@router.post("/note")
async def note_event(event: NoteEvent):
    """Send a note event (on/off via velocity > 0 or = 0)."""
    action = "note_on" if event.velocity > 0 else "note_off"
    await hub.broadcast(action, {
        "pitch": event.pitch,
        "velocity": event.velocity,
        "channel": event.channel,
        "timestamp": event.timestamp,
    })
    return {"ok": True}

@router.post("/midi/load")
async def load_midi(request: MidiLoadRequest):
    """Load a MIDI file (from URL or direct data)."""
    state = hub.update_state(
        current_file=request.filename,
        tracks=request.tracks or [],
        playing=False,
        position=0.0,
    )
    await hub.broadcast("midi_loaded", {
        "filename": request.filename,
        "tracks": request.tracks,
    })
    return {"ok": True, "state": hub.get_state()}

@router.get("/connections")
async def list_connections():
    """List all active WebSocket connections."""
    return hub.get_connections_info()

# --- WebSocket endpoint for real-time ---

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket for real-time MidiMate communication."""
    await websocket.accept()
    
    # Receive handshake
    try:
        data = await asyncio.wait_for(websocket.receive_text(), timeout=5.0)
        handshake = json.loads(data)
        client_id = handshake.get("client_id", f"client_{int(time.time())}")
        client_type = handshake.get("client_type", "unknown")
    except asyncio.TimeoutError:
        client_id = f"client_{int(time.time())}"
        client_type = "unknown"
    except Exception as e:
        logger.warning(f"Handshake failed: {e}")
        await websocket.close(code=1008, reason="Invalid handshake")
        return
    
    conn = await hub.register(client_id, client_type, websocket)
    
    try:
        while True:
            data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
            msg = json.loads(data)
            event = msg.get("event", "")
            payload = msg.get("data", {})
            
            # Handle events from clients
            if event == "ping":
                await hub.send_to(client_id, "pong", {"ts": time.time()})
            elif event == "state_request":
                await hub.send_to(client_id, "state_response", hub.get_state())
            elif event == "state_update":
                hub.update_state(**payload)
                await hub.broadcast("state_update", payload)
            elif event in ("note_on", "note_off"):
                await hub.broadcast(event, payload, exclude=client_id)
            elif event.startswith("transport_"):
                action = event.replace("transport_", "")
                if action == "play":
                    hub.update_state(playing=True)
                elif action == "stop":
                    hub.update_state(playing=False, position=0.0)
                elif action == "pause":
                    hub.update_state(playing=False)
                await hub.broadcast(event, payload, exclude=client_id)
                
    except asyncio.TimeoutError:
        logger.info(f"Client {client_id} timed out")
    except WebSocketDisconnect:
        logger.info(f"Client disconnected: {client_id}")
    except Exception as e:
        logger.warning(f"WebSocket error for {client_id}: {e}")
    finally:
        await hub.unregister(client_id)
        try:
            await hub.broadcast("client_left", {
                "client_id": client_id,
                "client_type": client_type,
                "total_clients": len(hub.connections)
            })
        except Exception:
            pass
