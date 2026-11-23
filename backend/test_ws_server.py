"""Tests del hub WebSocket (protocolo, secuencias, dedup y heartbeat)."""
import asyncio
import json

import pytest

from ws_server import Envelope, HardenedHub, WebSocketHub


class FakeWS:
    def __init__(self):
        self.sent_messages = []
        self.open = True

    async def send_text(self, msg):
        if self.open:
            self.sent_messages.append(msg)

    async def close(self):
        self.open = False


@pytest.fixture
def hub():
    return HardenedHub()


@pytest.fixture
def fake_ws():
    return FakeWS()


def decoded(ws):
    return [json.loads(m) for m in ws.sent_messages]


@pytest.mark.asyncio
async def test_alias_backwards_compatible():
    assert WebSocketHub is HardenedHub


@pytest.mark.asyncio
async def test_register_client(hub, fake_ws):
    conn = await hub.register("test_1", "test", fake_ws)
    assert conn.client_id == "test_1"
    assert conn.client_type == "test"
    assert "test_1" in hub.connections


@pytest.mark.asyncio
async def test_unregister_client(hub, fake_ws):
    await hub.register("test_2", "test", fake_ws)
    await hub.unregister("test_2", ws=fake_ws)
    assert "test_2" not in hub.connections


@pytest.mark.asyncio
async def test_envelope_has_both_wire_formats():
    msg = json.loads(Envelope(type="ping", payload={"a": 1}, sequence=7).serialize())
    assert msg["type"] == msg["event"] == "ping"
    assert msg["payload"] == msg["data"] == {"a": 1}
    assert msg["sequence"] == 7
    assert msg["event_id"]


@pytest.mark.asyncio
async def test_sequences_are_per_client(hub):
    a, b = FakeWS(), FakeWS()
    await hub.register("a", "midimate", a)
    await hub.register("b", "hernesto", b)
    await hub.broadcast(Envelope(type="tick", payload={}))

    seq_a = [m["sequence"] for m in decoded(a)]
    seq_b = [m["sequence"] for m in decoded(b)]
    # Cada cliente empieza en 1 y no tiene huecos, aunque el otro haya recibido más.
    assert seq_a == list(range(1, len(seq_a) + 1))
    assert seq_b == list(range(1, len(seq_b) + 1))
    assert len(seq_a) != len(seq_b)  # 'a' recibió client_joined de 'b'


@pytest.mark.asyncio
async def test_reconnect_resets_sequence_and_old_socket_cannot_unregister(hub):
    old, new = FakeWS(), FakeWS()
    await hub.register("same", "midimate", old)
    await hub.register("same", "midimate", new)
    await hub.unregister("same", ws=old, reason="old_socket")

    assert "same" in hub.connections  # la reconexión sobrevive
    assert [m["sequence"] for m in decoded(new)] == [1]


@pytest.mark.asyncio
async def test_broadcast(hub, fake_ws):
    await hub.register("a", "midimate", fake_ws)
    await hub.register("b", "hernesto", fake_ws)
    await hub.broadcast(Envelope(type="test_event", payload={"msg": "hello"}))
    assert len(fake_ws.sent_messages) >= 2


@pytest.mark.asyncio
async def test_update_state_broadcasts(hub, fake_ws):
    await hub.register("a", "midimate", fake_ws)
    changed = hub.update_state(playing=True)
    assert changed == {"playing": True}

    fake_ws2 = FakeWS()
    await hub.register("b", "test", fake_ws2)
    state_msgs = [m for m in decoded(fake_ws2) if m.get("type") == "state_response"]
    assert len(state_msgs) == 1
    assert state_msgs[0]["payload"]["playing"] is True


@pytest.mark.asyncio
async def test_dedup(hub):
    assert hub.is_duplicate("") is False
    hub.mark_seen("")
    assert hub.is_duplicate("") is False
    hub.mark_seen("evt-1")
    assert hub.is_duplicate("evt-1") is True


@pytest.mark.asyncio
async def test_heartbeat_check_marks_stale(hub):
    ws = FakeWS()
    conn = await hub.register("slow", "midimate", ws)
    conn.last_heartbeat -= hub.HEARTBEAT_TIMEOUT + 1
    await hub.heartbeat_check()
    assert "slow" not in hub.connections


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
