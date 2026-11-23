"""
study_db.py - Base de datos local de packs de estudio de Midiforja.

SQLite sin dependencias externas. Cada análisis se guarda como JSON (para poder
reconstruirlo por completo) junto con metadatos indexables y, cuando esté
disponible, los bytes del .mid original.
"""

from __future__ import annotations

import json
import os
import sqlite3
from typing import Any, Dict, List, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DB_PATH = os.path.join(HERE, "data", "midiforja.db")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS analyses (
    id              TEXT PRIMARY KEY,
    created_at      TEXT NOT NULL,
    source_name     TEXT,
    source_kind     TEXT,
    source_ext      TEXT,
    note_count      INTEGER NOT NULL DEFAULT 0,
    duration_sec    REAL NOT NULL DEFAULT 0,
    bpm             REAL,
    key_name        TEXT,
    key_mode        TEXT,
    difficulty      INTEGER,
    chord_names     TEXT,
    study_json      TEXT NOT NULL,
    midi_blob       BLOB,
    midi_name       TEXT
);
CREATE INDEX IF NOT EXISTS idx_analyses_created ON analyses(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_analyses_kind ON analyses(source_kind);
CREATE INDEX IF NOT EXISTS idx_analyses_key ON analyses(key_name);
CREATE INDEX IF NOT EXISTS idx_analyses_difficulty ON analyses(difficulty);
"""


def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    return {k: row[k] for k in row.keys()}


class StudyDB:
    def __init__(self, path: Optional[str] = None):
        self.path = path or os.environ.get("MIDIFORJA_DB_PATH") or DEFAULT_DB_PATH
        self.initialize()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=15)
        conn.row_factory = sqlite3.Row
        return conn

    def initialize(self) -> None:
        directory = os.path.dirname(os.path.abspath(self.path))
        if directory:
            os.makedirs(directory, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    def save(self, pack: Dict[str, Any], midi_bytes: Optional[bytes] = None,
             midi_name: Optional[str] = None) -> str:
        analysis = pack.get("analysis", {})
        key = analysis.get("key", {})
        chords = [c.get("chord", "") for c in analysis.get("chords", [])]
        values = (
            pack["id"],
            pack.get("created_at"),
            pack.get("source", {}).get("filename"),
            pack.get("source", {}).get("kind"),
            pack.get("source", {}).get("ext"),
            int(pack.get("summary", {}).get("note_count", 0)),
            float(pack.get("summary", {}).get("duration_sec", 0.0) or 0.0),
            pack.get("summary", {}).get("bpm"),
            key.get("key"),
            key.get("mode"),
            analysis.get("difficulty", {}).get("score"),
            ", ".join(dict.fromkeys(c for c in chords if c)),
            json.dumps(pack, ensure_ascii=False),
            midi_bytes,
            midi_name,
        )
        with self._connect() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO analyses
                   (id, created_at, source_name, source_kind, source_ext,
                    note_count, duration_sec, bpm, key_name, key_mode,
                    difficulty, chord_names, study_json, midi_blob, midi_name)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                values,
            )
        return pack["id"]

    def get(self, analysis_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT study_json FROM analyses WHERE id = ?", (analysis_id,)
            ).fetchone()
        return json.loads(row["study_json"]) if row else None

    def get_midi(self, analysis_id: str) -> Optional[bytes]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT midi_blob FROM analyses WHERE id = ?", (analysis_id,)
            ).fetchone()
        return bytes(row["midi_blob"]) if row and row["midi_blob"] else None

    def get_midi_name(self, analysis_id: str) -> Optional[str]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT midi_name FROM analyses WHERE id = ?", (analysis_id,)
            ).fetchone()
        return row["midi_name"] if row else None

    def list(self, limit: int = 50, offset: int = 0, *, search: str = "",
             key: str = "", kind: str = "",
             min_difficulty: int = 0, max_difficulty: int = 100) -> List[Dict[str, Any]]:
        where = ["difficulty BETWEEN ? AND ?"]
        params: List[Any] = [min_difficulty, max_difficulty]
        if search:
            where.append("(source_name LIKE ? OR chord_names LIKE ? OR key_name LIKE ?)")
            like = f"%{search}%"
            params.extend([like, like, like])
        if key:
            where.append("key_name = ?")
            params.append(key)
        if kind:
            where.append("source_kind = ?")
            params.append(kind)
        sql = (
            "SELECT id, created_at, source_name, source_kind, source_ext, note_count, "
            "duration_sec, bpm, key_name, key_mode, difficulty, chord_names "
            "FROM analyses WHERE " + " AND ".join(where) +
            " ORDER BY created_at DESC, rowid DESC LIMIT ? OFFSET ?"
        )
        params.extend([max(1, min(int(limit), 200)), max(0, int(offset))])
        with self._connect() as conn:
            return [_row_to_dict(r) for r in conn.execute(sql, params).fetchall()]

    def delete(self, analysis_id: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM analyses WHERE id = ?", (analysis_id,))
        return cur.rowcount > 0

    def stats(self) -> Dict[str, Any]:
        with self._connect() as conn:
            total = conn.execute("SELECT COUNT(*) FROM analyses").fetchone()[0]
            by_kind = {
                r[0] or "unknown": r[1]
                for r in conn.execute(
                    "SELECT source_kind, COUNT(*) FROM analyses GROUP BY source_kind"
                )
            }
            by_key = {
                r[0] or "unknown": r[1]
                for r in conn.execute(
                    "SELECT key_name, COUNT(*) FROM analyses GROUP BY key_name ORDER BY COUNT(*) DESC"
                )
            }
            by_difficulty = {
                str(r[0]): r[1]
                for r in conn.execute(
                    "SELECT difficulty, COUNT(*) FROM analyses GROUP BY difficulty ORDER BY difficulty"
                )
            }
            recent = [
                _row_to_dict(r) for r in conn.execute(
                    "SELECT id, created_at, source_name, key_name, difficulty "
                    "FROM analyses ORDER BY created_at DESC LIMIT 5"
                )
            ]
        return {
            "total": total,
            "by_kind": by_kind,
            "by_key": by_key,
            "by_difficulty": by_difficulty,
            "recent": recent,
            "db_path": self.path,
        }


# Shared instance used by the FastAPI app. The path can be overridden
# per-test by constructing StudyDB(temp_path) directly.
db = StudyDB()
