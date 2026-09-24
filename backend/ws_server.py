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
from typing import Dict, Optional, Any, List
from dataclasses import dataclass, field

logger = logging.getLogger("midiforja.ws")


@dataclass
class Connection:
    client_id: str
    client_type: str  # "midimate" | "hernesto" | "other"
    ws: Any
    connected_at: float = field(default_factory=time.time)


class WebSocketHub:
    def __init__(self):
        self.connections: Dict[str, Connection] = {}
        self._midi_state: Dict[str, Any] = {
            "playing": False, "position": 0.0, "tempo": 120,
            "current_file": None, "note_count": 0, "duration": 0.0,
            "tracks": [], "loop": False, "volume": 80,
        }

    async def register(self, client_id: str, client_type: str, ws) -> Connection:
        conn = Connection(client_id=client_id, client_type=client_type, ws=ws)
        self.connections[client_id] = conn
        logger.info(f"Registered {client_type}: {client_id}")
        # Send current state to new client
        await self._send_to(conn, "state_response", self._midi_state)
        # Notify others
        await self.broadcast("client_joined", {
            "client_id": client_id, "client_type": client_type,
            "total_clients": len(self.connections)
        }, exclude=client_id)
        return conn

    async def unregister(self, client_id: str):
        conn = self.connections.pop(client_id, None)
        if conn:
            logger.info(f"Unregistered {conn.client_type}: {client_id}")
            await self.broadcast("client_left", {
                "client_id": client_id, "client_type": conn.client_type,
                "total_clients": len(self.connections)
            })

    async def _send_to(self, conn: Connection, event: str, data: Any):
        try:
            msg = json.dumps({"event": event, "data": data, "ts": time.time()})
            await conn.ws.send_text(msg)
        except Exception as e:
            logger.warning(f"Send failed to {conn.client_id}: {e}")
            await self.unregister(conn.client_id)

    async def send_to(self, client_id: str, event: str, data: Any):
        conn = self.connections.get(client_id)
        if conn:
            await self._send_to(conn, event, data)

    async def broadcast(self, event: str, data: Any, exclude: Optional[str] = None):
        msg = json.dumps({"event": event, "data": data, "ts": time.time()})
        disconnected = []
        for cid, conn in list(self.connections.items()):
            if cid == exclude:
                continue
            try:
                await conn.ws.send_text(msg)
            except Exception:
                disconnected.append(cid)
        for cid in disconnected:
            await self.unregister(cid)

    def update_state(self, **kwargs) -> Dict[str, Any]:
        changed = {}
        for k, v in kwargs.items():
            if self._midi_state.get(k) != v:
                self._midi_state[k] = v
                changed[k] = v
        return changed

    def get_state(self) -> Dict[str, Any]:
        return dict(self._midi_state)

    def get_connections_info(self) -> List[Dict[str, Any]]:
        return [
            {"client_id": c.client_id, "client_type": c.client_type, "connected_at": c.connected_at}
            for c in self.connections.values()
        ]


hub = WebSocketHub()
