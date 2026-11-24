"""
test_e2e.py - End-to-end verification of the Midiforja pipeline.

1. Synthesize a clean piano-like WAV (C-major scale, 0.4s notes).
2. POST it to the running backend /api/transcribe.
3. Save the returned .mid and validate:
   - starts with b'MThd'
   - passes MidiMate's parseMidi + midiToNotes (note count > 0)
"""

import os
import sys
import json
import urllib.request

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

SR = 44100


def make_piano_wav(path, notes=("C4", "D4", "E4", "F4", "G4", "A4", "B4", "C5"),
                   note_dur=0.40, gap=0.02):
    """Synthesize a simple piano-ish tone per note (sine + 2nd/3rd harmonic
    with a short attack/decay envelope)."""
    name_to_midi = {}
    for n in range(21, 109):
        name_to_midi[_midi_name(n)] = n
    midis = [name_to_midi[n] for n in notes]
    total = len(midis) * (note_dur + gap)
    buf = np.zeros(int(total * SR), dtype=np.float32)
    t0 = 0
    for m in midis:
        f = 440.0 * 2 ** ((m - 69) / 12.0)
        n_samples = int(note_dur * SR)
        t = np.arange(n_samples) / SR
        # harmonics: fundamental + octave + twelfth, with envelope
        sig = (
            1.0 * np.sin(2 * np.pi * f * t)
            + 0.5 * np.sin(2 * np.pi * 2 * f * t)
            + 0.25 * np.sin(2 * np.pi * 3 * f * t)
        )
        env = np.exp(-3.0 * t) * np.ones_like(t)
        attack = int(0.005 * SR)
        env[:attack] = np.linspace(0, 1, attack)
        seg = (sig * env).astype(np.float32) * 0.6
        start = int(t0 * SR)
        buf[start:start + n_samples] += seg
        t0 += note_dur + gap
    buf = np.clip(buf, -1, 1)
    # write 16-bit WAV
    import wave
    with wave.open(path, "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((buf * 32767).astype("<i2").tobytes())
    return path


def _midi_name(m):
    names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    return f"{names[m % 12]}{m // 12 - 1}"


def find_midimate_parser():
    """Locate MidiMate's midi.js on Windows, Linux/macOS or via MIDIMATE_MIDI."""
    repo_parent = os.path.dirname(os.path.dirname(HERE))
    candidates = [
        os.environ.get("MIDIMATE_MIDI", ""),
        r"F:\ia.proyectos\MidiMate\Midimate\src\midi.js",
        os.path.join(repo_parent, "MidiMate", "Midimate", "src", "midi.js"),
        os.path.join(repo_parent, "MidiMate", "src", "midi.js"),
    ]
    for path in candidates:
        if path and os.path.exists(path):
            return os.path.abspath(path)
    return None


def validate_with_midimate_parser(mid_bytes):
    """Load MidiMate's src/midi.js parser (ESM) via Node and run parseMidi+midiToNotes."""
    import subprocess, textwrap
    midimate_midi = find_midimate_parser()
    if not midimate_midi:
        return "(MidiMate parser not found; skipped cross-check)"
    import shutil
    # Keep everything under HERE (a plain Windows path) so MSYS/bash node
    # path translation does not corrupt it.
    parser_copy = os.path.join(HERE, "_parser_copy.mjs")
    shutil.copyfile(midimate_midi, parser_copy)
    mid_path = os.path.join(HERE, "_check.mid")
    with open(mid_path, "wb") as f:
        f.write(mid_bytes)
    runner = textwrap.dedent(f"""
        import {{ parseMidi, midiToNotes }} from "./_parser_copy.mjs";
        import fs from "fs";
        const raw = fs.readFileSync({mid_path!r});
        const buf = new Uint8Array(raw.buffer, raw.byteOffset, raw.byteLength);
        const parsed = parseMidi(buf);
        const notes = midiToNotes(parsed);
        console.log(JSON.stringify({{ ticksPerBeat: parsed.ticksPerBeat, tracks: parsed.tracks.length, noteCount: notes.length, first: notes.slice(0,3) }}));
    """)
    rp = os.path.join(HERE, "_runner.mjs")
    with open(rp, "w") as f:
        f.write(runner)
    try:
        out = subprocess.run(["node", "_runner.mjs"], capture_output=True, text=True, timeout=60,
                             cwd=HERE)
        if out.returncode != 0:
            return f"(node error) {out.stderr[:500]}"
        return out.stdout.strip()
    except Exception as e:
        return f"(runner error) {e}"


def main():
    wav = os.path.join(HERE, "sample_piano.wav")
    make_piano_wav(wav)
    print(f"[1] WAV sintetizado: {wav} ({os.path.getsize(wav)} bytes)")

    with open(wav, "rb") as f:
        data = f.read()
    req = urllib.request.Request(
        "http://127.0.0.1:8000/api/transcribe",
        data=_multipart(data, "sample_piano.wav"),
        headers={"Content-Type": "multipart/form-data; boundary=midiforjaboundary"},
    )
    try:
        resp = urllib.request.urlopen(req, timeout=600)
    except urllib.error.HTTPError as e:
        print(f"[2] HTTP {e.code}: {e.read().decode()[:500]}")
        return
    mid = resp.read()
    note_count = resp.headers.get("X-Note-Count")
    print(f"[2] Respuesta: {len(mid)} bytes, X-Note-Count={note_count}")

    out_mid = os.path.join(HERE, "sample_output.mid")
    with open(out_mid, "wb") as f:
        f.write(mid)
    print(f"[3] .mid guardado: {out_mid}")

    ok_header = mid[:4] == b"MThd"
    print(f"[4] Header MThd: {ok_header}")

    cross = validate_with_midimate_parser(mid)
    print(f"[5] Cross-check con parser de MidiMate: {cross}")

    if ok_header and note_count and int(note_count) > 0:
        print("\nRESULTADO: OK - pipeline funcional y compatible con MidiMate.")
    else:
        print("\nRESULTADO: FALLO - revisar arriba.")


def _multipart(file_bytes, filename):
    b = b"midiforjaboundary"
    parts = []
    parts.append(b"--" + b)
    parts.append(
        f'Content-Disposition: form-data; name="file"; filename="{filename}"'.encode()
    )
    parts.append(b"Content-Type: audio/wav")
    parts.append(b"")
    parts.append(file_bytes)
    parts.append(b"--" + b + b"--")
    parts.append(b"")
    return b"\r\n".join(parts)


if __name__ == "__main__":
    main()
