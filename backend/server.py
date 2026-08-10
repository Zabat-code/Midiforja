"""
Midiforja backend - audio/video -> MIDI transcription server.

Pipeline:
  1. Receive uploaded audio/video file.
  2. Extract mono 44.1kHz WAV with ffmpeg.
  3. Run Spotify Basic Pitch (offline, Apache-2.0) to get note events.
  4. Write a Standard MIDI File (.mid) with midiwriter.
  5. Return the .mid as a download.

Basic Pitch is instrument-agnostic and polyphonic but works best on one
instrument at a time (we focus on piano first, as agreed).
"""

import os
import shutil
import tempfile
import uuid

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

import midiwriter

FFMPEG = shutil.which("ffmpeg") or r"C:\Users\Winuser\AppData\Local\Microsoft\WinGet\Links\ffmpeg.exe"

MAX_UPLOAD_BYTES = 200 * 1024 * 1024  # 200 MB cap
ALLOWED_EXT = {".mp3", ".wav", ".ogg", ".flac", ".m4a", ".aac",
               ".mp4", ".webm", ".mov", ".avi", ".mkv", ".wma"}

app = FastAPI(title="Midiforja", version="0.1.0")

# Frontend dev server origins (Vite). Add production origin as needed.
ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:5174",
    "http://127.0.0.1:5174",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _run_ffmpeg(in_path: str, out_wav: str) -> None:
    """Extract a mono 44.1kHz WAV. Raises on failure."""
    if not FFMPEG or not os.path.exists(FFMPEG):
        raise RuntimeError(
            "ffmpeg not found. Install ffmpeg and ensure it is on PATH."
        )
    cmd = [
        FFMPEG, "-y", "-i", in_path,
        "-ar", "44100", "-ac", "1", "-f", "wav", out_wav,
    ]
    import subprocess
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0 or not os.path.exists(out_wav):
        raise RuntimeError("ffmpeg failed to extract audio:\n" + proc.stderr[:2000])


def _transcribe(wav_path: str):
    """Run Basic Pitch and return list of (start, end, pitch, velocity)."""
    from basic_pitch.inference import predict

    # predict() returns (model_output, midi_data, note_events).
    # note_events: list of (start_sec, end_sec, pitch_midi, amplitude_0_1, [pitch_bends])
    _, _, note_events = predict(wav_path)

    if not note_events:
        return []

    out = []
    for row in note_events:
        start_sec = float(row[0])
        end_sec = float(row[1])
        pitch = int(round(float(row[2])))
        amplitude = float(row[3])  # 0..1
        vel_int = int(max(1, min(127, round(amplitude * 127))))
        if pitch < 0 or pitch > 127:
            continue
        if end_sec <= start_sec:
            end_sec = start_sec + 0.1
        out.append((start_sec, end_sec, pitch, vel_int))
    return out


@app.get("/")
def health():
    return {"status": "ok", "name": "Midiforja", "ffmpeg": bool(FFMPEG)}


@app.get("/api/info")
def info():
    return {
        "engine": "basic-pitch (Spotify, Apache-2.0)",
        "focus": "piano (single-instrument best quality)",
        "max_upload_mb": MAX_UPLOAD_BYTES // (1024 * 1024),
        "allowed_ext": sorted(ALLOWED_EXT),
    }


@app.post("/api/transcribe")
async def transcribe(file: UploadFile = File(...)):
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(400, f"Unsupported file type: {ext or '(none)'}")

    tmp_dir = tempfile.mkdtemp(prefix="midiforja_")
    try:
        raw_path = os.path.join(tmp_dir, f"input{uuid.uuid4().hex}{ext}")
        wav_path = os.path.join(tmp_dir, "audio.wav")
        mid_path = os.path.join(tmp_dir, "output.mid")

        # Save upload (streamed, with size cap).
        size = 0
        with open(raw_path, "wb") as f:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(413, "File too large")
                f.write(chunk)

        _run_ffmpeg(raw_path, wav_path)
        notes = _transcribe(wav_path)

        if not notes:
            raise HTTPException(
                422,
                "No notes detected. Try a clearer single-instrument (piano) "
                "recording with minimal background noise.",
            )

        midi_bytes = midiwriter.write_midi(notes, ticks_per_beat=480, bpm=120, channel=0)

        return Response(
            content=midi_bytes,
            media_type="audio/midi",
            headers={
                "Content-Disposition": 'attachment; filename="midiforja_output.mid"',
                "X-Note-Count": str(len(notes)),
            },
        )
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")
