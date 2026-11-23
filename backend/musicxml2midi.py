"""
musicxml2midi.py - Convert MusicXML (from Audiveris OMR) to a Standard MIDI File.

Self-contained: parses the MusicXML DOM with xml.etree and emits note events
(start_sec, end_sec, pitch, velocity) compatible with midiwriter. No heavy deps.

Timing model:
  * <attributes><divisions>N</divisions> = ticks per quarter note.
  * <note><duration>D</duration> = D ticks (in the divisions active at that point).
  * Tempo from <sound tempo="BPM"> (often nested inside <direction>) or 120 BPM.
  * Internally the cursor is kept in QUARTER NOTES, so changing <divisions>
    mid-score never changes the musical duration of what came before.
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


def _score_root(xml_text: str):
    root = ET.fromstring(xml_text)
    if _strip_ns(root.tag) != "score-partwise":
        for el in root.iter():
            if _strip_ns(el.tag) == "score-partwise":
                return el
    return root


def musicxml_tempo(xml_text: str, default: float = 120.0) -> float:
    """Devuelve el primer tempo (BPM) declarado en el MusicXML."""
    for el in _score_root(xml_text).iter():
        if _strip_ns(el.tag) == "sound":
            tempo = el.get("tempo")
            if tempo:
                try:
                    value = float(tempo)
                    if value > 0:
                        return value
                except ValueError:
                    pass
    return default


class _TempoMap:
    """Convierte posiciones en quarter notes a segundos con cambios de tempo."""

    def __init__(self, default_bpm: float = 120.0):
        self.changes = [(0.0, float(default_bpm))]
        self.default = float(default_bpm)

    def add(self, beat: float, bpm: float) -> None:
        if bpm > 0:
            self.changes.append((max(0.0, float(beat)), float(bpm)))
            self.changes.sort(key=lambda x: x[0])

    def to_seconds(self, beat: float) -> float:
        seconds = 0.0
        prev_beat = 0.0
        bpm = self.default
        for change_beat, change_bpm in self.changes:
            if change_beat > beat:
                break
            seconds += (change_beat - prev_beat) * 60.0 / bpm
            prev_beat = change_beat
            bpm = change_bpm
        seconds += (beat - prev_beat) * 60.0 / bpm
        return seconds


def musicxml_to_notes(xml_text: str):
    """Return list of (start_sec, end_sec, pitch, velocity)."""
    score = _score_root(xml_text)
    tempo_map = _TempoMap(musicxml_tempo(xml_text))
    divisions = 480  # ticks per quarter note
    notes = []
    cursors = {}     # (staff, voice) -> posición en quarter notes
    last_starts = {}  # (staff, voice) -> inicio de la última nota (para <chord/>)

    for part in score.iter():
        if _strip_ns(part.tag) != "part":
            continue
        for measure in part:
            if _strip_ns(measure.tag) != "measure":
                continue
            part_beats = min(cursors.values()) if cursors else 0.0
            for elem in measure.iter():
                tag = _strip_ns(elem.tag)

                if tag == "attributes":
                    for a in elem.iter():
                        if _strip_ns(a.tag) == "divisions":
                            try:
                                value = int(a.text)
                                if value > 0:
                                    divisions = value
                            except (TypeError, ValueError):
                                pass

                elif tag == "sound":
                    tempo = elem.get("tempo")
                    if tempo:
                        try:
                            tempo_map.add(part_beats, float(tempo))
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
                    for child in elem.iter():
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
                                    try:
                                        octave = int(p.text)
                                    except (TypeError, ValueError):
                                        pass
                                elif pt == "alter":
                                    try:
                                        alter = int(float(p.text))
                                    except (TypeError, ValueError):
                                        pass
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
                            txt = (child.text or "").strip().lower()
                            velocity = {"pp": 40, "p": 55, "mp": 70, "mf": 85,
                                        "f": 100, "ff": 115}.get(txt, velocity)
                            for d in child:
                                dt = _strip_ns(d.tag)
                                if dt in ("pp", "p", "mp", "mf", "f", "ff"):
                                    velocity = {"pp": 40, "p": 55, "mp": 70, "mf": 85,
                                                "f": 100, "ff": 115}[dt]

                    beats = duration / float(divisions) if divisions else 0.0
                    key = (staff, voice)
                    if is_chord:
                        # Las notas de un acorde comparten el ataque de la nota anterior.
                        start_beat = last_starts.get(key, cursors.get(key, 0.0))
                    else:
                        start_beat = cursors.get(key, 0.0)
                        cursors[key] = start_beat + beats
                        last_starts[key] = start_beat
                    if is_rest or step is None or octave is None:
                        continue
                    pitch = _step_to_pitch(step, octave, alter)
                    notes.append((
                        round(tempo_map.to_seconds(start_beat), 4),
                        round(tempo_map.to_seconds(start_beat + beats), 4),
                        pitch,
                        int(max(1, min(127, velocity))),
                    ))
    notes.sort(key=lambda n: (n[0], n[2]))
    return notes


def musicxml_to_midi(xml_text: str, ticks_per_beat: int = 480, bpm: int = None,
                     channel: int = 0) -> bytes:
    notes = musicxml_to_notes(xml_text)
    if bpm is None:
        bpm = int(round(musicxml_tempo(xml_text)))
    return midiwriter.write_midi(notes, ticks_per_beat=ticks_per_beat, bpm=bpm, channel=channel)
