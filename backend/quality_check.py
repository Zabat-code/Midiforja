"""
quality_check.py - Post-transcription quality & rhythm tools for Midiforja.

Implements (all deps light / already available: numpy, librosa, mir_eval):
  * detect_beat_grid   -> a metrical beat grid (seconds) + estimated BPM.
  * detect_audio_onsets-> note-ish onsets from the audio (seconds).
  * quantize_notes     -> snap MIDI note onsets/offsets to a beat grid.
  * onset_similarity   -> fidelity metric between two onset sets (time/rhythm).

The fidelity metric answers the goal: "compare after creating the MIDI that the
difference in time and rhythm is similar to the original".
"""

import numpy as np
import librosa

try:
    import mir_eval
except Exception:  # pragma: no cover - mir_eval is optional
    mir_eval = None

DEFAULT_TOLERANCE = 0.05  # seconds


def _load(wav_path, sr=44100):
    return librosa.load(wav_path, sr=sr, mono=True)


def detect_beat_grid(wav_path, sr=44100, start_bpm=120.0):
    """Detect a metrical beat grid (in seconds) plus the estimated BPM.

    Returns (beat_times ndarray float, tempo float).
    """
    y, sr = _load(wav_path, sr=sr)
    if y.size == 0:
        return np.array([], dtype=float), float(start_bpm)
    tempo, beats = librosa.beat.beat_track(y=y, sr=sr, start_bpm=float(start_bpm))
    beat_times = librosa.frames_to_time(beats, sr=sr)
    if isinstance(tempo, np.ndarray):  # some librosa versions return arrays
        tempo = float(tempo[0]) if tempo.size else float(start_bpm)
    return np.asarray(beat_times, dtype=float), float(tempo)


def detect_audio_onsets(wav_path, sr=44100, hop_length=512, backtrack=3):
    """Return onset times (seconds) detected in the audio."""
    y, sr = _load(wav_path, sr=sr)
    if y.size == 0:
        return np.array([], dtype=float)
    frames = librosa.onset.onset_detect(y=y, sr=sr, hop_length=hop_length,
                                        backtrack=backtrack)
    return librosa.frames_to_time(frames, sr=sr, hop_length=hop_length)


def _nearest(t, grid):
    if grid is None or len(grid) == 0:
        return float(t)
    idx = int(np.searchsorted(grid, t))
    if idx >= len(grid):
        return float(grid[-1])
    if idx == 0:
        return float(grid[0])
    a, b = grid[idx - 1], grid[idx]
    return float(a if (t - a) <= (b - t) else b)


def quantize_notes(notes, grid, quantize_onsets=True, quantize_offsets=False,
                   strength=1.0):
    """Return a new notes list with onsets (and optionally offsets) snapped to
    the nearest beat-grid time. `strength` (0..1) blends original<->grid.

    notes: list of (start_sec, end_sec, pitch, velocity).
    """
    out = []
    grid = None if grid is None else np.asarray(sorted(grid), dtype=float)
    for (start, end, pitch, vel) in notes:
        s = float(start)
        e = float(end)
        if quantize_onsets and grid is not None and len(grid):
            ns = _nearest(s, grid)
            s = s + (ns - s) * float(strength)
        if quantize_offsets and grid is not None and len(grid):
            ne = _nearest(e, grid)
            e = e + (ne - e) * float(strength)
        if e <= s:
            e = s + 0.1
        out.append((s, e, int(pitch), int(vel)))
    return out


def onset_similarity(ref_onsets, hyp_onsets, tolerance=DEFAULT_TOLERANCE):
    """Fidelity of `hyp_onsets` (seconds) vs `ref_onsets` (seconds).

    Uses mir_eval.onset.f_measure when available, with a naive threshold
    fallback otherwise.

    Returns dict with keys:
      f_measure, precision, recall, median_deviation_ms.
    """
    def _sec(v):
        try:
            return float(v[0]) if isinstance(v, (tuple, list)) else float(v)
        except Exception:
            return float(v)

    ref = np.asarray(sorted(_sec(o) for o in ref_onsets), dtype=float)
    hyp = np.asarray(sorted(_sec(o) for o in hyp_onsets), dtype=float)

    med_dev = None
    if ref.size and hyp.size:
        devs = []
        for h in hyp:
            d = np.abs(ref - h)
            if d.size:
                devs.append(float(d.min()))
        if devs:
            med_dev = float(np.median(devs)) * 1000.0  # -> ms

    if mir_eval is not None and ref.size and hyp.size:
        ref_bool = np.ones(len(ref), dtype=bool)
        hyp_bool = np.ones(len(hyp), dtype=bool)
        try:
            precision, recall, f = mir_eval.onset.f_measure(
                ref, ref_bool, hyp, hyp_bool, window=float(tolerance))
            return {"f_measure": float(f), "precision": float(precision),
                    "recall": float(recall), "median_deviation_ms": med_dev}
        except Exception:
            pass

    if ref.size and hyp.size:
        matches = int(sum(1 for h in hyp if bool(np.any(np.abs(ref - h) <= tolerance))))
        recall = matches / len(ref)
        precision = matches / len(hyp) if len(hyp) else 0.0
        total = precision + recall
        f = 2 * precision * recall / total if total else 0.0
        return {"f_measure": float(f), "precision": float(precision),
                "recall": float(recall), "median_deviation_ms": med_dev}

    return {"f_measure": 0.0, "precision": 0.0, "recall": 0.0,
            "median_deviation_ms": med_dev}


def summarize(q):
    """Human-friendly quality summary string from an onset_similarity dict."""
    if q.get("f_measure") is None:
        return "--"
    pct = round(max(0.0, min(1.0, q["f_measure"])) * 100)
    dev = q.get("median_deviation_ms")
    if dev is None:
        return f"{pct}% rhythm match"
    return f"{pct}% rhythm match (median deviation {dev:.0f} ms)"
