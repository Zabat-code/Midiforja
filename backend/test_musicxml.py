"""Tests de musicxml2midi: divisions, tempo anidado y MIDI resultante."""
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import midi_reader
import musicxml2midi

SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<score-partwise version="4.0">
  <part-list><score-part id="P1"><part-name>Music</part-name></score-part></part-list>
  <part id="P1">
    <measure number="1">
      <attributes><divisions>480</divisions></attributes>
      <sound tempo="120"/>
      <note><pitch><step>C</step><octave>4</octave></pitch><duration>480</duration><voice>1</voice><staff>1</staff></note>
      <note><chord/><pitch><step>E</step><octave>4</octave></pitch><duration>480</duration><voice>1</voice><staff>1</staff></note>
      <note><chord/><pitch><step>G</step><octave>4</octave></pitch><duration>480</duration><voice>1</voice><staff>1</staff></note>
      <note><pitch><step>D</step><octave>4</octave></pitch><duration>480</duration><voice>1</voice><staff>1</staff></note>
    </measure>
    <measure number="2">
      <note><pitch><step>E</step><octave>4</octave></pitch><duration>480</duration><voice>1</voice><staff>1</staff></note>
      <note><pitch><step>F</step><octave>4</octave></pitch><duration>480</duration><voice>1</voice><staff>1</staff></note>
    </measure>
  </part>
</score-partwise>
"""

NESTED_TEMPO = """<score-partwise><part id="P1"><measure number="1">
<attributes><divisions>1</divisions></attributes>
<direction><direction-type><words>x</words></direction-type><sound tempo="60"/></direction>
<note><pitch><step>C</step><octave>4</octave></pitch><duration>1</duration></note>
</measure></part></score-partwise>"""


def test_sample_notes_and_chord():
    notes = musicxml2midi.musicxml_to_notes(SAMPLE)
    assert len(notes) == 6
    assert [round(n[0], 3) for n in notes[:3]] == [0.0, 0.0, 0.0]
    assert sorted(n[2] for n in notes[:3]) == [60, 64, 67]
    # 480 ticks con divisions=480 = 1 quarter note @120bpm = 0.5 s
    assert [round(n[1], 3) for n in notes[:3]] == [0.5, 0.5, 0.5]


def test_nested_sound_tempo_and_divisions():
    assert musicxml2midi.musicxml_tempo(NESTED_TEMPO) == 60.0
    notes = musicxml2midi.musicxml_to_notes(NESTED_TEMPO)
    assert len(notes) == 1
    # divisions=1, tempo=60 -> 1 segundo exacto
    assert notes[0][0] == 0.0
    assert round(notes[0][1], 3) == 1.0


def test_midi_uses_detected_tempo():
    mid = musicxml2midi.musicxml_to_midi(NESTED_TEMPO)
    assert mid[:4] == b"MThd"
    parsed = midi_reader.parse_midi(mid)
    assert parsed["tempo_changes"][0][1] == 1_000_000  # 60 BPM
