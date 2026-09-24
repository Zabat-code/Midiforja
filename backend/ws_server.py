#!/usr/bin/env python3
"""
Hardened WebSocket server for MidiMate ↔ Midiforja.

Features:
  - Envelope with event_id, sequence, timestamp
  - Reconnect/reconnect_count tracking
  - Duplicate detection (dedup ring buffer)
  - Connection state (registered/active/reconnecting/stale/closed)
  - Heartbeat timeout detection
  - State resync on connect/reconnect

QA scenarios:
  - kill backend during WS → client reconnects, receives state
  - duplicate events → dedup by event_id
  - out-of-order events → sequence tracking
"""
import json
import time
import asyncio
import uuid
import logging
from typing import Dict, Optional, Any, List
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger("midiforja.ws")


class ConnState(Enum):
    REGISTERED = "registered"
    ACTIVE = "active"
    RECONNECTING = "reconnecting"
    STALE = "stale"
    CLOSED = "closed"


@dataclass
class Envelope:
    type: str
    payload: Any
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    sequence: int = 0
    timestamp: float = field(default_factory=lambda: time.time())

    def to_dict(self) -> Dict:
        return {
            "type": self.type,
            "event_id": self.event_id,
            "sequence": self.sequence,
            "timestamp": self.timestamp,
            "payload": self.payload,
        }

    def serialize(self) -> str:
        return json.dumps(self.to_dict())


@dataclass
class Connection:
    client_id: str
    client_type: str
    ws: Any
    state: ConnState = ConnState.REGISTERED
    connected_at: float = 0.0
    last_heartbeat: float = 0.0
    last_sequence: int = 0
    reconnect_count: int = 0

    def __post_init__(self):
        self.connected_at = time.time()
        self.last_heartbeat = time.time()


class HardenedHub:
    HEARTBEAT_TIMEOUT = 30.0
    MAX_RECONNECT = 5
    DEDUP_WINDOW = 1000

    def __init__(self):
        self.connections: Dict[str, Connection] = {}
        self._midi_state: Dict[str, Any] = {
            "playing": False, "position": 0.0, "tempo": 120,
            "current_file": None, "note_count": 0, "duration": 0.0,
            "tracks": [], "loop": False, "volume": 80,
        }
        self._sequence = 0
        self._seen_events: List[str] = []

    def _next_seq(self) -> int:
        self._sequence += 1
        return self._sequence

    async def register(self, client_id: str, client_type: str, ws) -> Connection:
        existing = self.connections.get(client_id)
        if existing:
            existing.state = ConnState.ACTIVE
            existing.ws = ws
            existing.reconnect_count += 1
            existing.last_heartbeat = time.time()
            logger.info(f"Reconnected {client_type} {client_id} (count={existing.reconnect_count})")
            conn = existing
        else:
            conn = Connection(client_id=client_id, client_type=client_type, ws=ws)
            conn.state = ConnState.ACTIVE
            self.connections[client_id] = conn
            logger.info(f"Registered {client_type} {client_id}")

        # Always send current state on register/reconnect
        await self._send_to(conn, Envelope(
            type="state_response",
            payload=self._midi_state,
            sequence=self._next_seq(),
        ))

        await self.broadcast(Envelope(
            type="client_joined",
            payload={
                "client_id": client_id,
                "client_type": client_type,
                "total_clients": len(self.connections),
                "reconnect_count": conn.reconnect_count,
            },
        ), exclude=client_id)

        return conn

    async def unregister(self, client_id: str, reason: str = "unknown"):
        conn = self.connections.pop(client_id, None)
        if conn:
            conn.state = ConnState.CLOSED
            logger.info(f"Unregistered {conn.client_type} {client_id}: {reason}")
            await self.broadcast(Envelope(
                type="client_left",
                payload={
                    "client_id": client_id,
                    "client_type": conn.client_type,
                    "total_clients": len(self.connections),
                    "reason": reason,
                },
            ))

    async def _send_to(self, conn: Connection, envelope: Envelope):
        envelope.sequence = self._next_seq()
        try:
            msg = envelope.serialize()
            await conn.ws.send_text(msg)
            conn.last_heartbeat = time.time()
        except Exception as e:
            logger.warning(f"Send failed to {conn.client_id}: {e}")
            conn.state = ConnState.STALE
            await self.unregister(conn.client_id, reason="send_failure")

    async def send_to(self, client_id: str, envelope: Envelope):
        conn = self.connections.get(client_id)
        if conn:
            await self._send_to(conn, envelope)

    async def broadcast(self, envelope: Envelope, exclude: Optional[str] = None):
        envelope.sequence = self._next_seq()
        disconnected = []
        for cid, conn in list(self.connections.items()):
            if cid == exclude:
                continue
            if conn.state != ConnState.ACTIVE:
                continue
            try:
                msg = envelope.serialize()
                await conn.ws.send_text(msg)
                conn.last_heartbeat = time.time()
            except Exception:
                disconnected.append(cid)
        for cid in disconnected:
            await self.unregister(cid, reason="broadcast_failure")

    def is_duplicate(self, event_id: str) -> bool:
        return event_id in self._seen_events

    def mark_seen(self, event_id: str):
        self._seen_events.append(event_id)
        if len(self._seen_events) > self.DEDUP_WINDOW:
            self._seen_events = self._seen_events[-self.DEDUP_WINDOW // 2:]

    async def heartbeat_check(self):
        now = time.time()
        stale = []
        for cid, conn in list(self.connections.items()):
            if now - conn.last_heartbeat > self.HEARTBEAT_TIMEOUT:
                conn.state = ConnState.STALE
                stale.append(cid)
        for cid in stale:
            await self.unregister(cid, reason="heartbeat_timeout")

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
            {
                "client_id": c.client_id,
                "client_type": c.client_type,
                "state": c.state.value,
                "connected_at": c.connected_at,
                "reconnect_count": c.reconnect_count,
                "last_heartbeat": c.last_heartbeat,
            }
            for c in self.connections.values()
        ]

    def get_stats(self) -> Dict[str, Any]:
        states = {}
        for c in self.connections.values():
            s = c.state.value
            states[s] = states.get(s, 0) + 1
        return {
            "total_connections": len(self.connections),
            "by_state": states,
            "seen_events_buffer": len(self._seen_events),
            "sequence": self._sequence,
        }


# Global hub instance
hub = HardenedHub()
