"""Schema bootstrap works without ffmpeg."""

from pathlib import Path

from tape.db import connect, init_db


def test_init_db(tmp_path: Path) -> None:
    db = tmp_path / "demo.mp4.tape"
    conn = connect(db)
    init_db(conn)
    version = conn.execute(
        "SELECT value FROM meta WHERE key = 'tape_version'"
    ).fetchone()["value"]
    assert version == "0"
    tables = {
        r["name"]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert {"meta", "media", "timeline_bins", "segments", "byte_index"} <= tables
    conn.close()
