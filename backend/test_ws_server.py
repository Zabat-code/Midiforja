"""Tests for WebSocket server."""
import asyncio
import json
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from ws_server import WebSocketHub


@pytest.fixture
def hub():
    return WebSocketHub()


@pytest.fixture
def fake_ws():
    """Mock WebSocket for testing."""
    class FakeWS:
        def __init__(self):
            self.sent_messages = []
            self.open = True
        
        async def send(self, msg):
            if self.open:
                self.sent_messages.append(msg)
        
        async def close(self):
            self.open = False
    
    return FakeWS()


@pytest.mark.asyncio
async def test_register_client(hub, fake_ws):
    """Test client registration."""
    conn = await hub.register("test_1", "test", fake_ws)
    assert conn.client_id == "test_1"
    assert conn.client_type == "test"
    assert "test_1" in hub.connections


@pytest.mark.asyncio
async def test_unregister_client(hub, fake_ws):
    """Test client unregistration."""
    await hub.register("test_2", "test", fake_ws)
    await hub.unregister("test_2")
    assert "test_2" not in hub.connections


@pytest.mark.asyncio
async def test_broadcast(hub, fake_ws):
    """Test message broadcasting."""
    await hub.register("a", "midimate", fake_ws)
    await hub.register("b", "hernesto", fake_ws)
    
    await hub.broadcast("test_event", {"msg": "hello"})
    
    # Both should have received the broadcast
    assert len(fake_ws.sent_messages) == 2


@pytest.mark.asyncio
async def test_update_state_broadcasts(hub, fake_ws):
    """Test that state updates broadcast changes."""
    await hub.register("a", "midimate", fake_ws)
    
    changed = hub.update_state(playing=True)
    assert changed == {"playing": True}
    
    # New connections should get the state
    fake_ws2 = type(fake_ws)()
    await hub.register("b", "test", fake_ws2)
    
    # The last sent message to new client should include state
    msgs = [json.loads(m) for m in fake_ws2.sent_messages]
    state_msgs = [m for m in msgs if m.get("event") == "state_response"]
    assert len(state_msgs) >= 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
