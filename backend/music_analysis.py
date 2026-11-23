"""
music_analysis.py - Análisis musical y "pack de estudio" de Midiforja.

Convierte una lista de notas (start_s, end_s, pitch, velocity) en un JSON
reutilizable: resumen, notas normalizadas, acordes, tonalidad, ritmo y
dificultad. Funciona con notas obtenidas de audio, MusicXML o un .mid.
"""

from __future__ import annotations

import json
import math
import uuid
from collections import Counter
from datetime import datetime, timezone

from midi_reader import read_midi

SCHEMA = "midiforja.study-pack/v1"
VERSION = 1

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
FLAT_NAMES = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]

# Krumhansl-Schmuckler profiles (major, natural minor).
_MAJOR_PROFILE = [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]
_MINOR_PROFILE = [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17]

_CHORD_TEMPLATES = [
    ("maj7", {0, 4, 7, 11}),
    ("min7", {0, 3, 7, 10}),
    ("dom7", {0, 4, 7, 10}),
    ("m7b5", {0, 3, 6, 10}),
    ("dim7", {0, 3, 6, 9}),
    ("maj6", {0, 4, 7, 9}),
    ("min6", {0, 3, 7, 9}),
    ("major", {0, 4, 7}),
    ("minor", {0, 3, 7}),
    ("dim", {0, 3, 6}),
    ("aug", {0, 4, 8}),
    ("sus2", {0, 2, 7}),
    ("sus4", {0, 5, 7}),
    ("add9", {0, 2, 4, 7}),
    ("5", {0, 7}),
]


def note_name(pitch: int) -> str:
    return f"{NOTE_NAMES[int(pitch) % 12]}{int(pitch) // 12 - 1}"


def estimate_bpm(notes) -> float | None:
    """Estima BPM a partir de los intervalos entre ataques (onsets)."""
    onsets = sorted({round(float(n[0]), 3) for n in notes})
    iois = []
    for a, b in zip(onsets, onsets[1:]):
        d = b - a
        if 0.08 <= d <= 4.0:
            iois.append(d)
    if len(iois) < 3:
        return None

    histogram: Counter[int] = Counter()
    for d in iois:
        while d > 1.2:
            d /= 2.0
        while d < 0.3:
            d *= 2.0
        if not 0.3 <= d <= 1.2:
            continue
        center = int(round(d * 100))
        for offset in (-2, -1, 0, 1, 2):
            histogram[center + offset] += 2 if offset == 0 else 1
    if not histogram:
        return None
    best = histogram.most_common(1)[0][0]
    return round(60.0 / (best / 100.0), 1)


def _pearson(a, b) -> float:
    n = len(a)
    ma, mb = sum(a) / n, sum(b) / n
    va = sum((x - ma) ** 2 for x in a)
    vb = sum((x - mb) ** 2 for x in b)
    if va <= 0 or vb <= 0:
        return 0.0
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / math.sqrt(va * vb)


def detect_key(notes):
    """Detecta tonalidad (25 perfiles: 12 tonos x mayor/menor)."""
    counts = [0.0] * 12
    for start, end, pitch, velocity in notes:
        dur = max(0.0, float(end) - float(start))
        weight = 1.0 + min(1.0, dur) + (float(velocity) / 127.0)
        counts[int(pitch) % 12] += weight
    if sum(counts) <= 0:
        counts = [1.0] * 12

    best = None
    for mode, profile in (("major", _MAJOR_PROFILE), ("minor", _MINOR_PROFILE)):
        for tonic in range(12):
            rotated = profile[-tonic:] + profile[:-tonic]
            corr = _pearson(counts, rotated)
            if best is None or corr > best["correlation"]:
                best = {
                    "key": NOTE_NAMES[tonic],
                    "key_flat": FLAT_NAMES[tonic],
                    "mode": mode,
                    "correlation": round(corr, 4),
                    "confidence": round(max(0.0, min(1.0, (corr + 1.0) / 2.0)), 3),
                }
    ranked = sorted(
        ({"pitch_class": NOTE_NAMES[i], "weight": round(v, 2)} for i, v in enumerate(counts)),
        key=lambda x: x["weight"], reverse=True,
    )
    best["pitch_classes"] = ranked[:5]
    best["scale"] = _scale_pitches(best["key"], best["mode"])
    return best


def _scale_pitches(key: str, mode: str):
    tonic = NOTE_NAMES.index(key)
    steps = [0, 2, 4, 5, 7, 9, 11] if mode == "major" else [0, 2, 3, 5, 7, 8, 10]
    return sorted((tonic + s) % 12 for s in steps)


def classify_chord(pitches):
    """Devuelve (root_pc, nombre, calidad) para un conjunto de pitches MIDI."""
    pcs = sorted({int(p) % 12 for p in pitches})
    if not pcs:
        return None, "?", "unknown"
    if len(pcs) == 1:
        return pcs[0], NOTE_NAMES[pcs[0]], "single"
    for quality, template in _CHORD_TEMPLATES:
        for root in pcs:
            intervals = {(pc - root) % 12 for pc in pcs}
            if intervals == template:
                suffix = {
                    "major": "", "minor": "m", "dim": "dim", "aug": "aug",
                    "sus2": "sus2", "sus4": "sus4", "add9": "add9",
                    "maj7": "maj7", "min7": "m7", "dom7": "7",
                    "m7b5": "m7b5", "dim7": "dim7", "maj6": "6",
                    "min6": "m6", "5": "5",
                }[quality]
                return root, FLAT_NAMES[root] + suffix, quality
    intervals = sorted(((pc - pcs[0]) % 12) for pc in pcs)
    return pcs[0], f"[{','.join(str(i) for i in intervals)}]", "cluster"


def find_chords(notes, tolerance: float = 0.06):
    """Agrupa notas con ataque simultáneo y las nombra como acordes."""
    ordered = sorted(notes, key=lambda n: (float(n[0]), int(n[2])))
    groups = []
    for note in ordered:
        start = float(note[0])
        if groups and start - groups[-1][0] <= tolerance:
            groups[-1][1].append(note)
        else:
            groups.append((start, [note]))

    chords = []
    for start, group in groups:
        pitches = sorted({int(n[2]) for n in group})
        if len(pitches) < 2:
            continue
        root, name, quality = classify_chord(pitches)
        end = max(float(n[1]) for n in group)
        chords.append({
            "start_sec": round(start, 3),
            "end_sec": round(end, 3),
            "duration_sec": round(max(0.0, end - start), 3),
            "pitches": pitches,
            "note_names": [note_name(p) for p in pitches],
            "root": NOTE_NAMES[root] if root is not None else None,
            "bass": note_name(min(pitches)),
            "chord": name,
            "quality": quality,
        })
    return chords


def analyze_rhythm(notes, bpm=None):
    durations = [max(0.0, float(n[1]) - float(n[0])) for n in notes]
    onsets = sorted(float(n[0]) for n in notes)
    total = max(0.0, max(float(n[1]) for n in notes) - min(onsets)) if notes else 0.0
    detected = bpm or estimate_bpm(notes)
    beat = 60.0 / detected if detected else 0.5

    iois = [b - a for a, b in zip(onsets, onsets[1:]) if b > a]
    median_ioi = sorted(iois)[len(iois) // 2] if iois else 0.0
    offbeat = 0
    if onsets and detected:
        for o in onsets:
            phase = (o - onsets[0]) % beat
            if min(phase, beat - phase) > beat * 0.15:
                offbeat += 1
    dur_counts = Counter(round(d, 2) for d in durations)
    return {
        "bpm": detected,
        "beat_sec": round(beat, 3),
        "duration_sec": round(total, 3),
        "notes_per_second": round(len(notes) / total, 2) if total else 0.0,
        "median_onset_interval_sec": round(median_ioi, 3),
        "syncopation_ratio": round(offbeat / len(onsets), 3) if onsets else 0.0,
        "velocity_mean": round(sum(float(n[3]) for n in notes) / len(notes), 1) if notes else 0.0,
        "duration_histogram": [
            {"seconds": d, "count": c} for d, c in dur_counts.most_common(8)
        ],
    }


def analyze_difficulty(notes, chords, rhythm, key_info):
    pitches = [int(n[2]) for n in notes]
    pitch_range = max(pitches) - min(pitches) if pitches else 0
    polyphony = max((len(c["pitches"]) for c in chords), default=1)
    nps = rhythm["notes_per_second"]
    bpm = rhythm.get("bpm") or 120
    scale = set(key_info.get("scale") or [])
    accidentals = sum(1 for p in pitches if p % 12 not in scale) / len(pitches) if pitches else 0.0

    score = (
        pitch_range * 0.55
        + polyphony * 6.0
        + nps * 7.0
        + max(0.0, bpm - 60) * 0.12
        + accidentals * 22.0
    )
    score = int(max(0, min(100, round(score))))
    if score < 25:
        level, label = 1, "beginner"
    elif score < 50:
        level, label = 2, "intermediate"
    elif score < 75:
        level, label = 3, "advanced"
    else:
        level, label = 4, "expert"
    return {
        "score": score,
        "level": level,
        "label": label,
        "pitch_range_semitones": pitch_range,
        "max_polyphony": polyphony,
        "accidental_ratio": round(accidentals, 3),
    }


def normalize_notes(notes):
    out = []
    for start, end, pitch, velocity in notes:
        s, e = float(start), float(end)
        out.append({
            "start_sec": round(s, 4),
            "end_sec": round(e, 4),
            "duration_sec": round(max(0.0, e - s), 4),
            "pitch": int(pitch),
            "note": note_name(pitch),
            "velocity": int(max(0, min(127, velocity))),
        })
    return out


def build_study_pack(notes, bpm=None, source=None, extra=None):
    """Construye el pack de estudio completo a partir de notas en segundos."""
    notes = list(notes or [])
    if not notes:
        raise ValueError("No hay notas para analizar.")

    source = source or {}
    key_info = detect_key(notes)
    chords = find_chords(notes)
    rhythm = analyze_rhythm(notes, bpm=bpm)
    difficulty = analyze_difficulty(notes, chords, rhythm, key_info)
    pitches = [int(n[2]) for n in notes]
    chord_counts = Counter(c["chord"] for c in chords)

    pack = {
        "schema": SCHEMA,
        "version": VERSION,
        "id": source.get("id") or uuid.uuid4().hex,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": {
            "filename": source.get("filename"),
            "kind": source.get("kind", "midi"),
            "ext": source.get("ext"),
            "original_note_count": source.get("note_count", len(notes)),
        },
        "summary": {
            "note_count": len(notes),
            "duration_sec": rhythm["duration_sec"],
            "bpm": rhythm["bpm"],
            "min_pitch": min(pitches),
            "max_pitch": max(pitches),
            "pitch_range_semitones": max(pitches) - min(pitches),
            "chord_count": len(chords),
            "unique_chords": len(chord_counts),
        },
        "notes": normalize_notes(notes),
        "analysis": {
            "key": key_info,
            "rhythm": rhythm,
            "chords": chords,
            "chord_progression": [c["chord"] for c in chords],
            "chord_frequency": [{"chord": k, "count": v} for k, v in chord_counts.most_common(12)],
            "difficulty": difficulty,
        },
    }
    if extra:
        pack["source"].update(extra)
    return pack


def pack_from_notes(notes, filename=None, kind="midi", bpm=None, ext=None):
    import os
    return build_study_pack(
        notes,
        bpm=bpm,
        source={
            "filename": filename,
            "kind": kind,
            "ext": ext or (os.path.splitext(filename or "")[1].lower() or None),
        },
    )


def pack_from_midi(data: bytes, filename=None, kind="midi", bpm_override=None):
    """Analiza bytes de un SMF y devuelve (pack, notas_en_segundos)."""
    import os
    notes, bpm = read_midi(data)
    pack = build_study_pack(
        notes,
        bpm=bpm_override or bpm,
        source={
            "filename": filename,
            "kind": kind,
            "ext": os.path.splitext(filename or "")[1].lower() or ".mid",
        },
    )
    return pack, notes


def pack_from_musicxml(xml_text: str, filename=None):
    """Analiza MusicXML usando el mismo conversor que el endpoint OMR."""
    import os
    from musicxml2midi import musicxml_to_notes, musicxml_tempo

    notes = musicxml_to_notes(xml_text)
    pack = build_study_pack(
        notes,
        bpm=musicxml_tempo(xml_text),
        source={
            "filename": filename,
            "kind": "sheet",
            "ext": os.path.splitext(filename or "")[1].lower() or ".xml",
        },
    )
    return pack, notes


def dump_pack(pack) -> str:
    return json.dumps(pack, ensure_ascii=False, indent=2)
