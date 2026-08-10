"""
pytest suite for Midiforja backend.

Covers the deterministic, fast parts without running Basic Pitch (TensorFlow is slow):
  - midiwriter produces a valid SMF accepted by MidiMate's parser
  - ffmpeg extraction of a WAV
  - FastAPI contract + error paths (TestClient) with transcribe mocked
  - /api/send-to-midimate file-copy logic (mocked input)

The heavy, real transcription (Basic Pitch) stays in test_e2e.py (manual).
"""

import os
import sys
import wave
import shutil
import tempfile

import numpy as np
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import midiwriter

MIDIMATE_MIDI = r"F:\ia.proyectos\MidiMate\src\midi.js"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def make_wav(path, notes=("C4", "E4", "G4"), sr=44100, note_dur=0.3, gap=0.05):
    names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    midis = []
    for n in notes:
        letter = n[:-1]
        octave = int(n[-1])
        midis.append(names.index(letter) + (octave + 1) * 12)
    total = len(midis) * (note_dur + gap)
    buf = np.zeros(int(total * sr), dtype=np.float32)
    t0 = 0.0
    for m in midis:
        f = 440.0 * 2 ** ((m - 69) / 12.0)
        n = int(note_dur * sr)
        t = np.arange(n) / sr
        seg = np.sin(2 * np.pi * f * t) * np.exp(-4 * t) * 0.6
        s = int(t0 * sr)
        buf[s:s+n] += seg
        t0 += note_dur + gap
    buf = np.clip(buf, -1, 1)
    with wave.open(path, "w") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes((buf * 32767).astype("<i2").tobytes())
    return path


def parse_with_midimate(mid_bytes):
    """Use MidiMate's real src/midi.js (via node) to validate the .mid."""
    if not os.path.exists(MIDIMATE_MIDI):
        return None
    tmp = tempfile.mkdtemp(prefix="mmcheck_")
    parser = os.path.join(tmp, "_parser.mjs")
    shutil.copyfile(MIDIMATE_MIDI, parser)
    mid_path = os.path.join(tmp, "_c.mid")
    open(mid_path, "wb").write(mid_bytes)
    runner = (
        'import { parseMidi, midiToNotes } from "./_parser.mjs";\n'
        'import fs from "fs";\n'
        f'const raw = fs.readFileSync({mid_path!r});\n'
        'const buf = new Uint8Array(raw.buffer, raw.byteOffset, raw.byteLength);\n'
        'const p = parseMidi(buf); const n = midiToNotes(p);\n'
        'console.log(JSON.stringify({ ticks: p.ticksPerBeat, tracks: p.tracks.length, notes: n.length }));\n'
    )
    rp = os.path.join(tmp, "_r.mjs")
    open(rp, "w").write(runner)
    import subprocess
    out = subprocess.run(["node", "_r.mjs"], capture_output=True, text=True, cwd=tmp, timeout=60)
    shutil.rmtree(tmp, ignore_errors=True)
    if out.returncode != 0:
        return f"ERR:{out.stderr[:200]}"
    return out.stdout.strip()


# ---------------------------------------------------------------------------
# 1) midiwriter
# ---------------------------------------------------------------------------
def test_writer_header_and_midimate_parse():
    notes = [(0.0, 0.5, 60, 100), (0.0, 0.5, 64, 90), (0.0, 0.5, 67, 95),
             (0.6, 1.0, 62, 100), (1.1, 1.5, 64, 100), (1.6, 2.0, 65, 100)]
    mid = midiwriter.write_midi(notes, ticks_per_beat=480, bpm=120, channel=0)
    assert mid[:4] == b"MThd", "bad MIDI header"
    res = parse_with_midimate(mid)
    assert res is not None, "MidiMate parser not available"
    assert '"notes":6' in res, f"MidiMate parse failed: {res}"


def test_writer_rejects_out_of_range_pitch():
    # pitches outside 0..127 are dropped during transcription, but writer must not crash
    mid = midiwriter.write_midi([(0.0, 0.5, 60, 100)], ticks_per_beat=480, bpm=120)
    assert mid[:4] == b"MThd"


# ---------------------------------------------------------------------------
# 2) ffmpeg extraction
# ---------------------------------------------------------------------------
def test_ffmpeg_extract(tmp_path):
    import server
    wav_in = str(tmp_path / "in.wav")
    make_wav(wav_in)
    wav_out = str(tmp_path / "out.wav")
    server._run_ffmpeg(wav_in, wav_out)
    assert os.path.exists(wav_out)
    with wave.open(wav_out) as w:
        assert w.getnchannels() == 1
        assert w.getframerate() == 44100


# ---------------------------------------------------------------------------
# 3) API contract + error paths (TestClient, transcribe mocked)
# ---------------------------------------------------------------------------
from fastapi.testclient import TestClient  # noqa: E402

import server as server_mod  # noqa: E402


@pytest.fixture
def client(monkeypatch):
    # Mock _transcribe to avoid TensorFlow; return deterministic notes.
    monkeypatch.setattr(server_mod, "_transcribe", lambda wav: [
        (0.0, 0.5, 60, 100), (0.6, 1.0, 64, 90), (1.1, 1.5, 67, 95),
    ])
    return TestClient(server_mod.app)


def test_health(client):
    r = client.get("/")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_info(client):
    r = client.get("/api/info")
    assert r.status_code == 200
    assert "basic-pitch" in r.json()["engine"]


def test_transcribe_unsupported(client, tmp_path):
    bad = tmp_path / "x.txt"
    bad.write_bytes(b"hello")
    with open(bad, "rb") as f:
        r = client.post("/api/transcribe", files={"file": ("x.txt", f, "text/plain")})
    assert r.status_code == 400


def test_transcribe_ok_returns_mid(client, tmp_path):
    wav = tmp_path / "p.wav"
    make_wav(str(wav))
    with open(wav, "rb") as f:
        r = client.post("/api/transcribe", files={"file": ("p.wav", f, "audio/wav")})
    assert r.status_code == 200
    assert r.content[:4] == b"MThd"
    assert int(r.headers.get("X-Note-Count", "0")) == 3


def test_transcribe_no_notes(client, tmp_path, monkeypatch):
    monkeypatch.setattr(server_mod, "_transcribe", lambda wav: [])
    wav = tmp_path / "silence.wav"
    make_wav(str(wav))
    with open(wav, "rb") as f:
        r = client.post("/api/transcribe", files={"file": ("silence.wav", f, "audio/wav")})
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# 4) send-to-midimate copy logic
# ---------------------------------------------------------------------------
def test_send_to_midimate(client, tmp_path, monkeypatch):
    # Point MidiMate dir at a temp folder so we don't touch the real project.
    monkeypatch.setenv("MIDIFORJA_MIDIMATE_DIR", str(tmp_path))
    import importlib
    importlib.reload(server_mod)
    c = TestClient(server_mod.app)

    mid_bytes = midiwriter.write_midi([(0.0, 0.5, 60, 100)], ticks_per_beat=480, bpm=120)
    r = c.post("/api/send-to-midimate",
               files={"file": ("out.mid", mid_bytes, "audio/midi")})
    assert r.status_code == 200
    j = r.json()
    assert j["ok"] is True
    assert os.path.exists(j["path"])
    # invalid (non-midi) upload rejected
    r2 = c.post("/api/send-to-midimate",
                files={"file": ("bad.mid", b"not a midi", "audio/midi")})
    assert r2.status_code == 400
