"""
test_writer.py - Validate midiwriter output against MidiMate's parser.

Does NOT need basic-pitch / tensorflow. Uses hardcoded notes so we can
verify the .mid binary format is accepted by MidiMate's src/midi.js.
"""

import os
import sys
import subprocess
import tempfile
import textwrap

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import midiwriter

# A C-major chord + a scale fragment, in seconds, pitch (MIDI), velocity.
NOTES = [
    (0.0, 0.5, 60, 100),  # C4
    (0.0, 0.5, 64, 90),   # E4
    (0.0, 0.5, 67, 95),   # G4
    (0.6, 1.0, 62, 100),  # D4
    (1.1, 1.5, 64, 100),  # E4
    (1.6, 2.0, 65, 100),  # F4
]


def validate_with_midimate_parser(mid_bytes):
    midimate_midi = r"F:\ia.proyectos\MidiMate\src\midi.js"
    if not os.path.exists(midimate_midi):
        return "(MidiMate parser not found; skipped)"
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
        console.log(JSON.stringify({{ ticksPerBeat: parsed.ticksPerBeat, tracks: parsed.tracks.length, noteCount: notes.length }}));
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
    mid = midiwriter.write_midi(NOTES, ticks_per_beat=480, bpm=120, channel=0)
    out_path = os.path.join(HERE, "writer_test_output.mid")
    with open(out_path, "wb") as f:
        f.write(mid)

    header_ok = mid[:4] == b"MThd"
    print(f"[1] .mid escrito: {out_path} ({len(mid)} bytes)")
    print(f"[2] Header MThd: {header_ok}")

    cross = validate_with_midimate_parser(mid)
    print(f"[3] Parser MidiMate: {cross}")

    # quick manual tick sanity: at 120bpm, 480 tpb -> ticks/sec = 960
    # first note on-tick should be 0, first off ~ 0.5*960 = 480
    if header_ok and "noteCount" in cross:
        print("\nRESULTADO writer: OK (formato aceptado por MidiMate).")
    else:
        print("\nRESULTADO writer: REVISAR arriba.")


if __name__ == "__main__":
    main()
