"""SQLite helpers and schema bootstrap."""

from __future__ import annotations

import sqlite3
from importlib import resources
from pathlib import Path

from tape import SCHEMA_VERSION


def tape_path_for(video: Path) -> Path:
    return video.with_suffix(video.suffix + ".tape")


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    sql = resources.files("tape").joinpath("schema/v0.sql").read_text(encoding="utf-8")
    conn.executescript(sql)
    conn.execute(
        "INSERT INTO meta(key, value) VALUES(?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        ("tape_version", SCHEMA_VERSION),
    )
    conn.commit()


def require_media(conn: sqlite3.Connection) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM media WHERE id = 1").fetchone()
    if row is None:
        raise SystemExit("El .tape no tiene media. Corré primero: tape index VIDEO")
    return row
