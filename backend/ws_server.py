"""
WebSocket server for MidiMate <-> Midiforja real-time communication.

Events:
  - note_on(pitch, velocity, channel, timestamp)
  - note_off(pitch, channel, timestamp)
  - transport_play(position)
  - transport_stop()
  - transport_pause()
  - midi_loaded(name, duration, tracks)
  - state_request() -> state_response(...)
"""
import json
import time
import asyncio
import logging
from typing import Dict, Set, Optional, Any
from dataclasses import dataclass, field, asdict
from datetime import datetime

logger = logging.getLogger("midiforja.ws")

@dataclass
class Connection:
    """Represents a connected client."""
    client_id: str
    client_type: str  # "midimate" | "hernesto" | "other"
    ws: Any  # WebSocket object
    connected_at: float = field(default_factory=time.time)
    last_ping: float = field(default_factory=time.time)

class WebSocketHub:
    """Central hub managing all WebSocket connections."""
    
    def __init__(self):
        self.connections: Dict[str, Connection] = {}
        self._lock = asyncio.Lock()
        self._midi_state: Dict[str, Any] = {
            "playing": False,
            "position": 0.0,
            "tempo": 120,
            "current_file": None,
            "note_count": 0,
            "duration": 0.0,
            "tracks": [],
            "loop": False,
            "volume": 80,
        }
    
    async def register(self, client_id: str, client_type: str, ws) -> Connection:
        """Register a new connection."""
        async with self._lock:
            conn = Connection(
                client_id=client_id,
                client_type=client_type,
                ws=ws
            )
            self.connections[client_id] = conn
            logger.info(f"Registered {client_type} client: {client_id}")
            # Send current state to new client
            await self._send_to(conn, "state_response", self._midi_state)
            # Notify others
            await self.broadcast("client_joined", {
                "client_id": client_id,
                "client_type": client_type,
                "total_clients": len(self.connections)
            }, exclude=client_id)
            return conn
    
    async def unregister(self, client_id: str):
        """Remove a connection."""
        async with self._lock:
            if client_id in self.connections:
                conn = self.connections.pop(client_id)
                logger.info(f"Unregistered {conn.client_type} client: {client_id}")
                await self.broadcast("client_left", {
                    "client_id": client_id,
                    "client_type": conn.client_type,
                    "total_clients": len(self.connections)
                })
    
    async def _send_to(self, conn: Connection, event: str, data: Any):
        """Send event to a specific connection."""
        try:
            msg = json.dumps({"event": event, "data": data, "ts": time.time()})
            await conn.ws.send(msg)
        except Exception as e:
            logger.warning(f"Send failed to {conn.client_id}: {e}")
    
    async def broadcast(self, event: str, data: Any, exclude: Optional[str] = None):
        """Send event to all connections."""
        msg = json.dumps({"event": event, "data": data, "ts": time.time()})
        tasks = []
        for cid, conn in self.connections.items():
            if cid == exclude:
                continue
            tasks.append(self._safe_send(conn, msg))
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _safe_send(self, conn: Connection, msg: str):
        try:
            await conn.ws.send(msg)
        except Exception:
            pass
    
    def update_state(self, **kwargs):
        """Update MIDI state and broadcast changes."""
        changed = {}
        for k, v in kwargs.items():
            if self._midi_state.get(k) != v:
                self._midi_state[k] = v
                changed[k] = v
        if changed:
            asyncio.create_task(self.broadcast("state_update", changed))
        return changed
    
    def get_state(self) -> Dict[str, Any]:
        """Get current MIDI state."""
        return dict(self._midi_state)
    
    def get_connections_info(self) -> list:
        """Get info about all connections."""
        return [
            {
                "client_id": c.client_id,
                "client_type": c.client_type,
                "connected_at": c.connected_at,
            }
            for c in self.connections.values()
        ]


# Global hub instance
hub = WebSocketHub()
