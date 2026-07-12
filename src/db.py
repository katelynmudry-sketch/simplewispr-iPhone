"""SQLite transcript storage."""

import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

APP_SUPPORT = Path.home() / "Library" / "Application Support" / "MyWispr"
DB_PATH = APP_SUPPORT / "transcripts.db"

CREATE_SQL = """
CREATE TABLE IF NOT EXISTS transcripts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   TEXT NOT NULL,
    duration_sec REAL,
    language    TEXT,
    audio_file  TEXT,
    raw_text    TEXT NOT NULL,
    cleaned_text TEXT NOT NULL
)
"""


def _connect() -> sqlite3.Connection:
    APP_SUPPORT.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init() -> None:
    with _connect() as conn:
        conn.execute(CREATE_SQL)


def insert(
    raw_text: str,
    cleaned_text: str,
    duration_sec: Optional[float] = None,
    language: Optional[str] = None,
    audio_file: Optional[str] = None,
) -> int:
    ts = datetime.now().isoformat(timespec="seconds")
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO transcripts (timestamp, duration_sec, language, audio_file, raw_text, cleaned_text)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (ts, duration_sec, language, audio_file, raw_text, cleaned_text),
        )
        return cur.lastrowid


def recent(n: int = 10) -> list[sqlite3.Row]:
    with _connect() as conn:
        return conn.execute(
            "SELECT * FROM transcripts ORDER BY id DESC LIMIT ?", (n,)
        ).fetchall()


def search_window(start_date: str, range_days: int) -> tuple[str, str]:
    """Return (from_date, to_date) as ISO date strings for the search window.

    Empty/None start_date means today. Both boundary dates are inclusive.
    """
    end = date.fromisoformat(start_date) if start_date else date.today()
    start = end - timedelta(days=range_days)
    return start.isoformat(), end.isoformat()


def search(
    keyword: str,
    limit: int = 20,
    start_date: str = "",
    range_days: int = 30,
) -> list[sqlite3.Row]:
    from_date, to_date = search_window(start_date, range_days)
    pattern = f"%{keyword}%"
    with _connect() as conn:
        return conn.execute(
            "SELECT * FROM transcripts"
            " WHERE (raw_text LIKE ? OR cleaned_text LIKE ?)"
            " AND timestamp BETWEEN ? AND ?"
            " ORDER BY id DESC LIMIT ?",
            (pattern, pattern, f"{from_date}T00:00:00", f"{to_date}T23:59:59", limit),
        ).fetchall()


def search_count(
    keyword: str,
    start_date: str = "",
    range_days: int = 30,
) -> int:
    """Return total matching transcript count (ignoring limit) for the given window."""
    from_date, to_date = search_window(start_date, range_days)
    pattern = f"%{keyword}%"
    with _connect() as conn:
        return conn.execute(
            "SELECT COUNT(*) FROM transcripts"
            " WHERE (raw_text LIKE ? OR cleaned_text LIKE ?)"
            " AND timestamp BETWEEN ? AND ?",
            (pattern, pattern, f"{from_date}T00:00:00", f"{to_date}T23:59:59"),
        ).fetchone()[0]


def null_audio_file(audio_path: str) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE transcripts SET audio_file = NULL WHERE audio_file = ?",
            (audio_path,),
        )
