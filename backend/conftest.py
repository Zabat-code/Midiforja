"""Configuración común de pytest para el backend de Midiforja."""
import os
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

os.environ.setdefault("MIDIFORJA_RATE_LIMIT_MAX", "10000")


@pytest.fixture(autouse=True)
def isolated_storage(tmp_path, monkeypatch):
    """Cada test usa una base SQLite y un directorio de .mid propios."""
    import server
    import study_db

    files_dir = tmp_path / "files"
    files_dir.mkdir(exist_ok=True)
    monkeypatch.setattr(server, "FILES_DIR", str(files_dir))
    monkeypatch.setattr(study_db, "db", study_db.StudyDB(str(tmp_path / "midiforja.db")))
    yield
