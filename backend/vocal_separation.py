"""
vocal_separation.py - Optional vocal removal (source separation) for Midiforja.

Uses Demucs (Meta, MIT-licensed) if installed to split the mix into stems and
rebuild an instrumental track WITHOUT the vocals, so Basic Pitch won't transcribe
the singing voice.

Because Demucs drags in PyTorch (~2 GB), it is OPTIONAL: if it is not installed,
raise a clear RuntimeError so the caller can fall back to the original mix.
"""

import os
import shutil
import subprocess
import sys
import tempfile

# Stem name to drop. `--two-stems vocals` produces vocals.wav + no_vocals.wav.
STEM_TO_REMOVE = "vocals"
DEFAULT_MODEL = "htdemucs"


def _torch_and_demucs_available():
    try:
        import torch  # noqa: F401
        import demucs  # noqa: F401
        return True
    except Exception:
        return False


def _demucs_command():
    exe = shutil.which("demucs")
    if exe:
        return [exe]
    return [sys.executable, "-m", "demucs"]


def remove_vocals(wav_path, out_wav, model=DEFAULT_MODEL, timeout=900):
    """Produce an instrumental (no-vocals) WAV at `out_wav`.

    Returns the path to the instrumental WAV. Raises RuntimeError if Demucs /
    torch is missing or processing fails / times out.
    """
    if not _torch_and_demucs_available():
        raise RuntimeError(
            "Demucs/PyTorch no está instalado (se necesita para 'Eliminar la "
            "voz'). Instala con: pip install demucs  (arrastra ~2 GB de PyTorch)."
        )

    work = tempfile.mkdtemp(prefix="voc_")
    outdir = os.path.join(work, "out")
    os.makedirs(outdir, exist_ok=True)
    cmd = _demucs_command() + [
        "--two-stems", STEM_TO_REMOVE,
        "-n", model,
        "-o", outdir,
        wav_path,
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise RuntimeError(
            f"Demucs tardó más de {timeout}s separando la voz y se canceló."
        )
    if res.returncode != 0:
        raise RuntimeError("Demucs falló:\n" + (res.stderr or res.stdout)[-800:])

    # Locate the instrumental stem (no_vocals.wav) under outdir/<model>/<name>/
    stem = None
    all_wavs = []
    for base, _dirs, files in os.walk(outdir):
        for fn in files:
            if fn.lower().endswith(".wav"):
                all_wavs.append(os.path.join(base, fn))
    # Prefer the explicit no_vocals stem.
    stem = next((w for w in all_wavs if "no_vocals" in os.path.basename(w).lower()), None)
    if stem is None:
        # Fallback: any wav that is NOT the vocals stem.
        stem = next((w for w in all_wavs if "vocals" not in os.path.basename(w).lower()), None)
    if not stem or not os.path.exists(stem):
        shutil.rmtree(work, ignore_errors=True)
        raise RuntimeError("Demucs no produjo el stem instrumental.")

    # Copy the instrumental stem into the requested output path.
    os.makedirs(os.path.dirname(out_wav) or ".", exist_ok=True)
    shutil.copyfile(stem, out_wav)
    shutil.rmtree(work, ignore_errors=True)
    return out_wav
