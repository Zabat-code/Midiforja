"""Tests del pack de estudio, la base local y los endpoints nuevos."""
import asyncio
import json

import pytest
from fastapi import WebSocketDisconnect
from fastapi.testclient import TestClient

import midiwriter
import midi_reader
import music_analysis as analysis
import server
import study_db
from midimate_router import ws_endpoint
from ws_server import hub

NOTES = [
    (0.0, 0.5, 60, 100),
    (0.0, 0.5, 64, 90),
    (0.0, 0.5, 67, 95),
    (0.5, 1.0, 62, 100),
    (1.0, 1.5, 64, 100),
]


@pytest.fixture
def midi_bytes():
    return midiwriter.write_midi(NOTES, ticks_per_beat=480, bpm=120)


@pytest.fixture
def client():
    return TestClient(server.app)


# ---- lector SMF -----------------------------------------------------------

def test_midi_reader_roundtrip(midi_bytes):
    parsed = midi_reader.parse_midi(midi_bytes)
    assert parsed["ticks_per_beat"] == 480
    assert len(parsed["notes"]) == len(NOTES)
    notes, bpm = midi_reader.to_seconds(parsed)
    assert bpm == 120.0
    assert [(n[0], n[1], n[2]) for n in notes] == [
        (0.0, 0.5, 60), (0.0, 0.5, 64), (0.0, 0.5, 67),
        (0.5, 1.0, 62), (1.0, 1.5, 64),
    ]
    assert notes[0][3] == 100  # velocity del note_on, no del note_off


def test_midi_reader_rejects_non_midi():
    with pytest.raises(ValueError):
        midi_reader.parse_midi(b"no es midi")


# ---- análisis musical -----------------------------------------------------

def test_study_pack_from_midi(midi_bytes):
    pack, notes = analysis.pack_from_midi(midi_bytes, filename="tema.mid")
    assert pack["schema"] == analysis.SCHEMA
    assert pack["source"]["filename"] == "tema.mid"
    assert pack["summary"]["note_count"] == 5
    assert pack["summary"]["bpm"] == 120.0
    assert len(notes) == 5
    assert pack["notes"][0]["note"] == "C4"
    assert pack["analysis"]["chords"][0]["chord"] == "C"
    assert 1 <= pack["analysis"]["difficulty"]["level"] <= 4
    assert pack["analysis"]["key"]["mode"] in ("major", "minor")


def test_estimate_bpm():
    notes = [(i * 0.5, i * 0.5 + 0.4, 60, 90) for i in range(8)]
    assert analysis.estimate_bpm(notes) == 120.0


def test_chord_qualities():
    assert analysis.classify_chord([60, 64, 67])[1] == "C"
    assert analysis.classify_chord([60, 63, 67])[1] == "Cm"
    assert analysis.classify_chord([60, 64, 67, 70])[1] == "C7"


# ---- base de datos --------------------------------------------------------

def test_study_db_crud_and_filters(midi_bytes, tmp_path):
    db = study_db.StudyDB(str(tmp_path / "db.sqlite"))
    pack, _ = analysis.pack_from_midi(midi_bytes, filename="Crédito.mid")
    db.save(pack, midi_bytes, "Credito.mid")

    assert db.get(pack["id"])["summary"]["note_count"] == 5
    assert db.get_midi(pack["id"]) == midi_bytes
    assert len(db.list(search="crédito")) == 1
    assert len(db.list(key="E", kind="midi", min_difficulty=0, max_difficulty=100)) == 1
    assert db.stats()["total"] == 1
    assert db.delete(pack["id"]) is True
    assert db.get(pack["id"]) is None


# ---- endpoints ------------------------------------------------------------

def test_analyze_midi_endpoint_and_stash(client, midi_bytes):
    r = client.post(
        "/api/analyze-midi",
        files={"file": ("tema.mid", midi_bytes, "audio/midi")},
    )
    assert r.status_code == 200
    pack = r.json()
    aid = pack["id"]
    assert r.headers["X-Analysis-Id"] == aid
    assert client.get(pack["midi_url"]).status_code == 200
    assert client.get(f"/files/{aid}.mid").status_code == 200
    assert client.get("/files/../server.py").status_code == 404
    assert client.get(f"/api/study-pack/{aid}").status_code == 200
    assert client.get(f"/api/analyses/{aid}/midi").content == midi_bytes
    assert client.get("/api/stats").json()["total"] == 1
    assert client.delete(f"/api/analyses/{aid}").status_code == 200
    assert client.get("/api/stats").json()["total"] == 0


def test_analyze_midi_rejects_invalid(client):
    r = client.post(
        "/api/analyze-midi",
        files={"file": ("x.txt", b"hola", "text/plain")},
    )
    assert r.status_code == 400


def test_cors_allows_midimate_desktop(client):
    for origin in ("http://localhost:8765", "null", "http://localhost:5173"):
        r = client.options(
            "/api/analyses",
            headers={"Origin": origin, "Access-Control-Request-Method": "GET"},
        )
        assert r.headers.get("access-control-allow-origin") == origin


# ---- protocolo WS ---------------------------------------------------------

class FakeWS:
    def __init__(self, messages):
        self.queue = asyncio.Queue()
        for m in messages:
            self.queue.put_nowait(m if isinstance(m, str) else json.dumps(m))
        self.sent = []

    async def accept(self):
        pass

    async def receive_text(self):
        raw = await self.queue.get()
        if raw == "__CLOSE__":
            raise WebSocketDisconnect(1000)
        return raw

    async def send_text(self, raw):
        self.sent.append(json.loads(raw))

    async def close(self, code=1000):
        pass


@pytest.mark.asyncio
async def test_ws_accepts_both_formats_and_sequences():
    ws = FakeWS([
        {"client_id": "proto", "client_type": "midimate"},
        {"type": "state_request", "payload": {}, "event_id": "s1", "sequence": 0},
        {"type": "ping", "payload": {"ts": 1}, "event_id": "p1", "sequence": 0},
        {"event": "state_request", "data": {}, "event_id": "s2", "sequence": 1},
        "__CLOSE__",
    ])
    await asyncio.wait_for(ws_endpoint(ws), 3)
    types = [m["type"] for m in ws.sent]
    assert types == ["state_response", "state_response", "pong", "state_response"]
    assert [m["sequence"] for m in ws.sent] == [1, 2, 3, 4]
    assert all(m["event_id"] and "payload" in m and "data" in m for m in ws.sent)
    assert "proto" not in hub.connections
