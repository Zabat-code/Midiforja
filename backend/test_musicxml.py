"""Unit test for musicxml2midi: parse a small MusicXML and verify notes + .mid validity."""
import os, sys, subprocess, tempfile, shutil, textwrap

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import musicxml2midi

SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 4.0 Partwise//EN" "http://www.musicxml.org/dtds/partwise.dtd">
<score-partwise version="4.0">
  <part-list><score-part id="P1"><part-name>Music</part-name></score-part></part-list>
  <part id="P1">
    <measure number="1">
      <attributes><divisions>480</divisions><time><beats>4</beats><beat-type>4</beat-type></time></attributes>
      <sound tempo="120"/>
      <note><pitch><step>C</step><octave>4</octave></pitch><duration>480</duration><voice>1</voice><staff>1</staff></note>
      <note><chord/><pitch><step>E</step><octave>4</octave></pitch><duration>480</duration><voice>1</voice><staff>1</staff></note>
      <note><chord/><pitch><step>G</step><octave>4</octave></pitch><duration>480</duration><voice>1</voice><staff>1</staff></note>
      <note><pitch><step>D</step><octave>4</octave></pitch><duration>480</duration><voice>1</voice><staff>1</staff></note>
    </measure>
    <measure number="2">
      <note><pitch><step>E</step><octave>4</octave><alter>0</alter></pitch><duration>480</duration><voice>1</voice><staff>1</staff></note>
      <note><pitch><step>F</step><octave>4</octave></pitch><duration>480</duration><voice>1</voice><staff>1</staff></note>
    </measure>
  </part>
</score-partwise>
"""

def main():
    notes = musicxml2midi.musicxml_to_notes(SAMPLE)
    # Expect 7 notes; first three are a C4/E4/G4 chord starting at 0.
    assert len(notes) == 7, f"expected 7 notes, got {len(notes)}: {notes}"
    # chord notes share start_sec=0
    starts = [round(n[0], 3) for n in notes[:3]]
    assert starts == [0.0, 0.0, 0.0], f"chord start mismatch: {starts}"
    pitches = sorted(n[2] for n in notes[:3])
    assert pitches == [60, 64, 67], f"chord pitches: {pitches}"
    # durations: 480 divisions @ 120bpm -> 1s per note
    ends = [round(n[1], 3) for n in notes[:3]]
    assert ends == [1.0, 1.0, 1.0], f"chord end: {ends}"
    print("[1] notes parsed OK:", notes[:3], "...total", len(notes))

    mid = musicxml2midi.musicxml_to_midi(SAMPLE)
    assert mid[:4] == b"MThd"
    # cross-check with MidiMate parser
    MIDIMATE = r"F:\ia.proyectos\MidiMate\src\midi.js"
    if os.path.exists(MIDIMATE):
        tmp = tempfile.mkdtemp(prefix="mx_")
        shutil.copyfile(MIDIMATE, os.path.join(tmp, "_p.mjs"))
        mp = os.path.join(tmp, "_c.mid"); open(mp, "wb").write(mid)
        runner = textwrap.dedent(f"""
            import {{ parseMidi, midiToNotes }} from "./_p.mjs";
            import fs from "fs";
            const raw = fs.readFileSync({mp!r});
            const buf = new Uint8Array(raw.buffer, raw.byteOffset, raw.byteLength);
            const p = parseMidi(buf); const n = midiToNotes(p);
            console.log(JSON.stringify({{ ticks: p.ticksPerBeat, tracks: p.tracks.length, notes: n.length }}));
        """)
        rp = os.path.join(tmp, "_r.mjs"); open(rp, "w").write(runner)
        out = subprocess.run(["node", "_r.mjs"], capture_output=True, text=True, cwd=tmp, timeout=60)
        shutil.rmtree(tmp, ignore_errors=True)
        print("[2] MidiMate parse:", out.stdout.strip() or out.stderr[:200])
        assert '"notes":7' in out.stdout, "MidiMate did not read 7 notes"
    print("\nRESULTADO: musicxml2midi OK")

if __name__ == "__main__":
    main()
