"""
musicxml2midi.py - Convert MusicXML (from Audiveris OMR) to a Standard MIDI File.

Self-contained: parses the MusicXML DOM with xml.etree and emits note events
(start_sec, end_sec, pitch, velocity) compatible with midiwriter. No heavy deps.

Timing model:
  * <attributes><divisions>N</divisions> = ticks per quarter note.
  * <note><duration>D</duration> = D ticks.
  * Tempo from <sound tempo="BPM"> or default 120 BPM.
  * Position is tracked per (staff, voice) cursor; <chord/> notes share a start.
"""

import xml.etree.ElementTree as ET

try:
    from . import midiwriter  # imported as package module (e.g. from server)
except ImportError:
    import midiwriter  # imported directly as a script


_STEP_OFFSET = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def _step_to_pitch(step: str, octave: int, alter: int = 0) -> int:
    return (octave + 1) * 12 + _STEP_OFFSET.get(step, 0) + int(alter or 0)


def _strip_ns(tag: str) -> str:
    return tag.split("}", 1)[-1] if "}" in tag else tag


def musicxml_to_notes(xml_text: str):
    """Return list of (start_sec, end_sec, pitch, velocity)."""
    root = ET.fromstring(xml_text)
    # find the actual score root if wrapped
    score = root
    if _strip_ns(root.tag) != "score-partwise":
        for el in root.iter():
            if _strip_ns(el.tag) == "score-partwise":
                score = el
                break

    divisions = 480  # default ticks per quarter
    tempo = 120.0     # default BPM
    secs_per_tick = (60.0 / tempo) / divisions

    notes = []
    # cursor per (staff, voice)
    cursors = {}

    for part in score.iter():
        if _strip_ns(part.tag) != "part":
            continue
        for measure in part:
            if _strip_ns(measure.tag) != "measure":
                continue
            for elem in measure:
                tag = _strip_ns(elem.tag)
                if tag == "attributes":
                    for a in elem.iter():
                        if _strip_ns(a.tag) == "divisions":
                            try:
                                divisions = int(a.text)
                            except (TypeError, ValueError):
                                pass
                elif tag == "sound":
                    tp = elem.get("tempo")
                    if tp:
                        try:
                            tempo = float(tp)
                            secs_per_tick = (60.0 / tempo) / divisions
                        except ValueError:
                            pass
                elif tag == "note":
                    is_chord = False
                    is_rest = False
                    step = None
                    octave = None
                    alter = 0
                    duration = 0
                    voice = "1"
                    staff = "1"
                    velocity = 80
                    for child in elem:
                        ct = _strip_ns(child.tag)
                        if ct == "chord":
                            is_chord = True
                        elif ct == "rest":
                            is_rest = True
                        elif ct == "pitch":
                            for p in child:
                                pt = _strip_ns(p.tag)
                                if pt == "step":
                                    step = p.text
                                elif pt == "octave":
                                    octave = int(p.text)
                                elif pt == "alter":
                                    alter = int(float(p.text))
                        elif ct == "duration":
                            try:
                                duration = int(child.text or 0)
                            except ValueError:
                                duration = 0
                        elif ct == "voice":
                            voice = (child.text or "1").strip()
                        elif ct == "staff":
                            staff = (child.text or "1").strip()
                        elif ct == "dynamics":
                            # crude: use first <other-dynamics> or <f/p> -> velocity
                            txt = (child.text or "").strip().lower()
                            velocity = {"pp": 40, "p": 55, "mp": 70, "mf": 85,
                                        "f": 100, "ff": 115}.get(txt, velocity)
                    if is_rest or step is None or octave is None:
                        # advance cursor by duration even on rest
                        key = (staff, voice)
                        cursors[key] = cursors.get(key, 0) + duration
                        continue
                    key = (staff, voice)
                    start_tick = cursors.get(key, 0)
                    if not is_chord:
                        cursors[key] = start_tick + duration
                    pitch = _step_to_pitch(step, octave, alter)
                    start_sec = start_tick * secs_per_tick
                    end_sec = (start_tick + duration) * secs_per_tick
                    notes.append((start_sec, end_sec, pitch, int(max(1, min(127, velocity)))))
    return notes


def musicxml_to_midi(xml_text: str, ticks_per_beat: int = 480, bpm: int = 120, channel: int = 0) -> bytes:
    notes = musicxml_to_notes(xml_text)
    return midiwriter.write_midi(notes, ticks_per_beat=ticks_per_beat, bpm=bpm, channel=channel)
