"""
test_quality.py - Validate the quality/rhythm tools and optional vocal removal.

Runs three quick checks:
  [1] detect_beat_grid + quantize_notes on the sample piano WAV
  [2] onset_similarity fidelity metric (audio onsets vs MIDI onsets)
  [3] vocal_separation gracefully reports when Demucs/torch is missing

Requires: librosa, numpy, mir_eval (already in the venv). No tensorflow / torch needed.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import quality_check
import vocal_separation

SAMPLE = os.path.join(HERE, "sample_piano.wav")


def main():
    print("== [1] Beat grid + quantization ==")
    grid, tempo = quality_check.detect_beat_grid(SAMPLE)
    print(f"  grid beats={len(grid)} tempo={tempo:.1f} bpm")
    assert len(grid) > 0, "no beat grid detected"

    # fake notes on a scale, quantize to the grid, verify they snap to grid values
    fake = [(i * 0.419, i * 0.419 + 0.3, 60 + i, 80) for i in range(len(grid) - 2)]
    quant = quality_check.quantize_notes(fake, grid)
    assert all(any(abs(on - g) < 1e-6 for g in grid) for on, _, _, _ in quant), \
        "quantized onsets not on the grid"
    print(f"  quantization OK ({len(quant)} notes on grid)")

    print("== [2] Onset fidelity (rhythm match) ==")
    audio_onsets = quality_check.detect_audio_onsets(SAMPLE)
    midi_onsets = [(0.0, 0.4, 60, 80), (0.42, 0.8, 62, 80), (0.84, 1.2, 64, 80)]
    sim = quality_check.onset_similarity(audio_onsets, [o[0] for o in midi_onsets])
    print("  fidelity:", sim, "->", quality_check.summarize(sim))
    assert "f_measure" in sim

    print("== [3] Vocal removal (missing-demucs fallback) ==")
    missing = False
    try:
        vocal_separation.remove_vocals(SAMPLE, os.path.join(HERE, "_nomatter.wav"))
    except RuntimeError as e:
        missing = "Demucs/PyTorch" in str(e)
        print(f"  raise as expected when Demucs absent: {missing}")
    assert missing or _has_demucs(), "should raise (or have demucs installed)"
    if missing:
        print("\nRESULTADO quality: OK")
    else:
        print("\nRESULTADO quality: Demucs presente; no se probó el fallback.")


def _has_demucs():
    try:
        import torch  # noqa
        import demucs  # noqa
        return True
    except Exception:
        return False


if __name__ == "__main__":
    main()
