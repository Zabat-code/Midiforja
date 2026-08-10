"""
Midiforja backend - audio/video -> MIDI transcription server.

Pipeline:
  1. Receive uploaded audio/video file.
  2. Extract mono 44.1kHz WAV with ffmpeg.
  3. Run Spotify Basic Pitch (offline, Apache-2.0) to get note events.
  4. Write a Standard MIDI File (.mid) with midiwriter.
  5. Return the .mid as a download (+ stash a copy for the deep-link).

Basic Pitch is instrument-agnostic and polyphonic but works best on one
instrument at a time (we focus on piano first, as agreed).
"""

import os
import shutil
import tempfile
import uuid

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, JSONResponse

import midiwriter

FFMPEG = shutil.which("ffmpeg") or r"C:\Users\Winuser\AppData\Local\Microsoft\WinGet\Links\ffmpeg.exe"

MAX_UPLOAD_BYTES = 200 * 1024 * 1024  # 200 MB cap
ALLOWED_EXT = {".mp3", ".wav", ".ogg", ".flac", ".m4a", ".aac",
               ".mp4", ".webm", ".mov", ".avi", ".mkv", ".wma"}

HERE = os.path.dirname(os.path.abspath(__file__))
FILES_DIR = os.path.join(HERE, "files")            # stashed transcripts (deep-link source)
INBOX_DIR = os.path.join(HERE, "midimate_inbox")   # copies dropped into MidiMate

# Config from env (override defaults as you like).
MIDIMATE_DIR = os.environ.get("MIDIFORJA_MIDIMATE_DIR", r"F:\ia.proyectos\MidiMate")
MIDIMATE_URL = os.environ.get("MIDIFORJA_MIDIMATE_URL", "http://localhost:5173")

os.makedirs(FILES_DIR, exist_ok=True)
os.makedirs(INBOX_DIR, exist_ok=True)

app = FastAPI(title="Midiforja", version="0.2.0")

ALLOWED_ORIGINS = [
    "http://localhost:5173", "http://127.0.0.1:5173",
    "http://localhost:5174", "http://127.0.0.1:5174",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _run_ffmpeg(in_path: str, out_wav: str) -> None:
    if not FFMPEG or not os.path.exists(FFMPEG):
        raise RuntimeError("ffmpeg not found. Install ffmpeg and put it on PATH.")
    import subprocess
    proc = subprocess.run(
        [FFMPEG, "-y", "-i", in_path, "-ar", "44100", "-ac", "1", "-f", "wav", out_wav],
        capture_output=True, text=True,
    )
    if proc.returncode != 0 or not os.path.exists(out_wav):
        err = proc.stderr.strip().splitlines()[-1] if proc.stderr.strip() else "unknown ffmpeg error"
        raise RuntimeError(f"ffmpeg failed: {err}")


def _transcribe(wav_path: str):
    """Run Basic Pitch -> list of (start_sec, end_sec, pitch, velocity)."""
    from basic_pitch.inference import predict

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
    return {"status": "ok", "name": "Midiforja", "ffmpeg": bool(FFMPEG),
            "midimate_url": MIDIMATE_URL}


@app.get("/api/info")
def info():
    return {
        "engine": "basic-pitch (Spotify, Apache-2.0)",
        "focus": "piano (single-instrument best quality)",
        "max_upload_mb": MAX_UPLOAD_BYTES // (1024 * 1024),
        "allowed_ext": sorted(ALLOWED_EXT),
        "midimate_url": MIDIMATE_URL,
    }


@app.post("/api/transcribe")
async def transcribe(file: UploadFile = File(...)):
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(400, f"Tipo de archivo no soportado: {ext or '(ninguno)'}")

    tmp_dir = tempfile.mkdtemp(prefix="midiforja_")
    try:
        raw_path = os.path.join(tmp_dir, f"input{uuid.uuid4().hex}{ext}")
        wav_path = os.path.join(tmp_dir, "audio.wav")
        size = 0
        with open(raw_path, "wb") as f:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(413, "Archivo demasiado grande (máx 200 MB).")
                f.write(chunk)

        try:
            _run_ffmpeg(raw_path, wav_path)
        except RuntimeError as e:
            raise HTTPException(422, str(e))

        try:
            notes = _transcribe(wav_path)
        except Exception as e:
            raise HTTPException(500, f"Error en la transcripción: {e}")

        if not notes:
            raise HTTPException(
                422,
                "No se detectaron notas. Prueba con una grabación más clara de un solo "
                "instrumento (piano) y menos ruido de fondo.",
            )

        midi_bytes = midiwriter.write_midi(notes, ticks_per_beat=480, bpm=120, channel=0)
        fid = uuid.uuid4().hex
        stash = os.path.join(FILES_DIR, f"{fid}.mid")
        with open(stash, "wb") as f:
            f.write(midi_bytes)

        return Response(
            content=midi_bytes,
            media_type="audio/midi",
            headers={
                "Content-Disposition": 'attachment; filename="midiforja_output.mid"',
                "X-Note-Count": str(len(notes)),
                "X-Midi-Id": fid,
            },
        )
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@app.post("/api/send-to-midimate")
async def send_to_midimate(file: UploadFile = File(...)):
    """Copy a transcribed .mid into MidiMate's folder so the user can drop it in.

    Does NOT modify MidiMate code; just places the file where the user expects it.
    """
    if not MIDIMATE_DIR or not os.path.isdir(MIDIMATE_DIR):
        raise HTTPException(400, f"Carpeta de MidiMate no encontrada: {MIDIMATE_DIR}")
    data = await file.read()
    if not data.startswith(b"MThd"):
        raise HTTPException(400, "El archivo no es un MIDI válido.")
    name = (file.filename or "midiforja_output.mid").split("/")[-1]
    if not name.lower().endswith(".mid"):
        name += ".mid"
    dest_dir = os.path.join(MIDIMATE_DIR, "midiforja_inbox")
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, name)
    with open(dest, "wb") as f:
        f.write(data)
    return JSONResponse({
        "ok": True,
        "path": dest,
        "midimate_url": MIDIMATE_URL,
        "note": "Abre MidiMate y suelta el archivo que quedó en midiforja_inbox.",
    })


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")
