#!/usr/bin/env python3
"""
Hardened WebSocket hub for MidiMate <-> Midiforja.

Compatible con ambos formatos de cable:
  - nuevo: {type, payload, sequence, event_id, timestamp}
  - antiguo: {event, data, ...}

El cliente moderno de MidiMate exige que `sequence` sea consecutivo POR
CONEXIÓN (empieza en 1) y que cada mensaje tenga `event_id`. Por eso el contador
ya no es global.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

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

    def to_dict(self) -> Dict[str, Any]:
        # `event`/`data` are aliases so older MidiMate builds keep working.
        return {
            "type": self.type,
            "event": self.type,
            "sequence": self.sequence,
            "event_id": self.event_id,
            "timestamp": self.timestamp,
            "payload": self.payload,
            "data": self.payload,
        }

    def serialize(self) -> str:
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, msg: Dict[str, Any]) -> "Envelope":
        return cls(
            type=msg.get("type") or msg.get("event") or "",
            payload=msg.get("payload", msg.get("data", {})),
            event_id=msg.get("event_id") or str(uuid.uuid4()),
            sequence=int(msg.get("sequence") or 0),
            timestamp=float(msg.get("timestamp") or time.time()),
        )


@dataclass
class Connection:
    client_id: str
    client_type: str
    ws: Any
    state: ConnState = ConnState.REGISTERED
    connected_at: float = field(default_factory=time.time)
    last_heartbeat: float = field(default_factory=time.time)
    last_sequence: int = 0
    out_sequence: int = 0
    reconnect_count: int = 0

    def next_sequence(self) -> int:
        self.out_sequence += 1
        return self.out_sequence


class HardenedHub:
    HEARTBEAT_TIMEOUT = 30.0
    HEARTBEAT_INTERVAL = 10.0
    MAX_RECONNECT = 5
    DEDUP_WINDOW = 1000

    def __init__(self):
        self.HEARTBEAT_INTERVAL = float(
            os.environ.get("MIDIFORJA_WS_HEARTBEAT_INTERVAL", self.HEARTBEAT_INTERVAL)
        )
        self.HEARTBEAT_TIMEOUT = float(
            os.environ.get("MIDIFORJA_WS_HEARTBEAT_TIMEOUT", self.HEARTBEAT_TIMEOUT)
        )
        self.connections: Dict[str, Connection] = {}
        self._midi_state: Dict[str, Any] = {
            "playing": False, "position": 0.0, "tempo": 120,
            "current_file": None, "note_count": 0, "duration": 0.0,
            "tracks": [], "loop": False, "volume": 80,
        }
        self._seen_events: deque = deque(maxlen=self.DEDUP_WINDOW)
        self._seen_set = set()
        self._heartbeat_task: Optional[asyncio.Task] = None

    # ---- sequences / dedup -------------------------------------------------
    def _next_seq(self) -> int:
        """Compatibility helper: next sequence for the 'most recent' client."""
        conns = list(self.connections.values())
        return conns[-1].next_sequence() if conns else 1

    def is_duplicate(self, event_id: str) -> bool:
        return bool(event_id) and event_id in self._seen_set

    def mark_seen(self, event_id: str) -> None:
        if not event_id or event_id in self._seen_set:
            return
        self._seen_events.append(event_id)
        self._seen_set.add(event_id)
        if len(self._seen_events) == self._seen_events.maxlen:
            dropped = self._seen_events[0]
            # deque already rotated by the time we get here; keep set in sync
            self._seen_set.intersection_update(self._seen_events)

    # ---- connection lifecycle ---------------------------------------------
    async def register(self, client_id: str, client_type: str, ws) -> Connection:
        existing = self.connections.get(client_id)
        if existing:
            existing.state = ConnState.ACTIVE
            existing.ws = ws
            existing.reconnect_count += 1
            existing.last_heartbeat = time.time()
            existing.out_sequence = 0  # reinicia la secuencia tras reconexión
            conn = existing
            logger.info("Reconnected %s %s (count=%s)", client_type, client_id,
                        conn.reconnect_count)
        else:
            conn = Connection(client_id=client_id, client_type=client_type, ws=ws)
            conn.state = ConnState.ACTIVE
            self.connections[client_id] = conn
            logger.info("Registered %s %s", client_type, client_id)

        await self._send_to(conn, Envelope(
            type="state_response", payload=self._midi_state,
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

    async def unregister(self, client_id: str, reason: str = "unknown", ws=None):
        """Remove a client. If `ws` is given, only remove if it is still current.

        This prevents an old socket's `finally` from deleting a newer connection
        that reused the same client_id after a reconnect.
        """
        conn = self.connections.get(client_id)
        if not conn or (ws is not None and conn.ws is not ws):
            return
        self.connections.pop(client_id, None)
        conn.state = ConnState.CLOSED
        logger.info("Unregistered %s %s: %s", conn.client_type, client_id, reason)
        await self.broadcast(Envelope(
            type="client_left",
            payload={
                "client_id": client_id,
                "client_type": conn.client_type,
                "total_clients": len(self.connections),
                "reason": reason,
            },
        ))

    def touch(self, client_id: str) -> None:
        conn = self.connections.get(client_id)
        if conn:
            conn.last_heartbeat = time.time()

    # ---- sending -----------------------------------------------------------
    async def _send_to(self, conn: Connection, envelope: Envelope):
        envelope.sequence = conn.next_sequence()
        try:
            await conn.ws.send_text(envelope.serialize())
            conn.last_heartbeat = time.time()
        except Exception as exc:
            logger.warning("Send failed to %s: %s", conn.client_id, exc)
            conn.state = ConnState.STALE
            await self.unregister(conn.client_id, reason="send_failure", ws=conn.ws)

    async def send_to(self, client_id: str, envelope: Envelope):
        conn = self.connections.get(client_id)
        if conn:
            await self._send_to(conn, envelope)

    async def broadcast(self, envelope: Envelope, exclude: Optional[str] = None):
        disconnected = []
        for cid, conn in list(self.connections.items()):
            if cid == exclude or conn.state != ConnState.ACTIVE:
                continue
            try:
                envelope.sequence = conn.next_sequence()
                await conn.ws.send_text(envelope.serialize())
                conn.last_heartbeat = time.time()
            except Exception:
                disconnected.append((cid, conn.ws))
        for cid, ws in disconnected:
            await self.unregister(cid, reason="broadcast_failure", ws=ws)

    # ---- heartbeat ---------------------------------------------------------
    async def heartbeat_check(self):
        now = time.time()
        stale = [
            (cid, conn.ws) for cid, conn in list(self.connections.items())
            if now - conn.last_heartbeat > self.HEARTBEAT_TIMEOUT
        ]
        for cid, ws in stale:
            await self.unregister(cid, reason="heartbeat_timeout", ws=ws)

    async def heartbeat_loop(self):
        while True:
            await asyncio.sleep(self.HEARTBEAT_INTERVAL)
            await self.heartbeat_check()
            if self.connections:
                await self.broadcast(Envelope(
                    type="heartbeat", payload={"ts": time.time()},
                ))

    def start_heartbeat(self):
        if self._heartbeat_task is None or self._heartbeat_task.done():
            self._heartbeat_task = asyncio.create_task(self.heartbeat_loop())

    async def stop_heartbeat(self):
        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
        self._heartbeat_task = None

    # ---- shared state ------------------------------------------------------
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
                "sequence": c.out_sequence,
            }
            for c in self.connections.values()
        ]

    def get_stats(self) -> Dict[str, Any]:
        states: Dict[str, int] = {}
        for c in self.connections.values():
            states[c.state.value] = states.get(c.state.value, 0) + 1
        return {
            "total_connections": len(self.connections),
            "by_state": states,
            "seen_events_buffer": len(self._seen_events),
            "sequences": {cid: c.out_sequence for cid, c in self.connections.items()},
        }


# Global hub and backwards-compatible alias.
hub = HardenedHub()
WebSocketHub = HardenedHub
