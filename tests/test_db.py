"""Tests for db.py."""

import sqlite3
from datetime import date, timedelta

import pytest


@pytest.fixture(autouse=True)
def patch_db(tmp_path, monkeypatch):
    db_file = tmp_path / "transcripts.db"
    monkeypatch.setattr("db.DB_PATH", db_file)
    monkeypatch.setattr("db.APP_SUPPORT", tmp_path)
    import db
    db.init()
    return db_file


def test_insert_and_recent():
    import db
    row_id = db.insert(raw_text="Hello world", cleaned_text="Hello world", duration_sec=1.5)
    assert row_id is not None
    rows = db.recent(10)
    assert len(rows) == 1
    assert rows[0]["raw_text"] == "Hello world"
    assert rows[0]["duration_sec"] == pytest.approx(1.5)


def test_recent_order_newest_first():
    import db
    db.insert(raw_text="First", cleaned_text="First")
    db.insert(raw_text="Second", cleaned_text="Second")
    rows = db.recent(10)
    assert rows[0]["raw_text"] == "Second"
    assert rows[1]["raw_text"] == "First"


def test_recent_limit():
    import db
    for i in range(15):
        db.insert(raw_text=f"T{i}", cleaned_text=f"T{i}")
    rows = db.recent(5)
    assert len(rows) == 5


def test_search_finds_match():
    import db
    db.insert(raw_text="I love Python programming", cleaned_text="I love Python programming")
    db.insert(raw_text="Unrelated text", cleaned_text="Unrelated text")
    results = db.search("Python")
    assert len(results) == 1
    assert "Python" in results[0]["raw_text"]


def test_search_no_match():
    import db
    db.insert(raw_text="Hello world", cleaned_text="Hello world")
    results = db.search("zzznomatch")
    assert results == []


def test_search_matches_cleaned():
    import db
    db.insert(raw_text="um hello", cleaned_text="hello")
    results = db.search("hello")
    assert len(results) == 1


def test_null_audio_file(tmp_path):
    import db
    audio_path = str(tmp_path / "test.wav")
    row_id = db.insert(raw_text="Test", cleaned_text="Test", audio_file=audio_path)
    db.null_audio_file(audio_path)
    rows = db.recent(1)
    assert rows[0]["audio_file"] is None


def test_insert_all_fields():
    import db
    row_id = db.insert(
        raw_text="raw",
        cleaned_text="cleaned",
        duration_sec=2.0,
        language="en",
        audio_file="/tmp/audio.wav",
    )
    rows = db.recent(1)
    r = rows[0]
    assert r["language"] == "en"
    assert r["audio_file"] == "/tmp/audio.wav"
    assert r["duration_sec"] == pytest.approx(2.0)


# --- search_window boundary math ---

def test_search_window_empty_start_is_today():
    import db
    from_date, to_date = db.search_window("", 30)
    today = date.today().isoformat()
    expected_from = (date.today() - timedelta(days=30)).isoformat()
    assert to_date == today
    assert from_date == expected_from


def test_search_window_explicit_start():
    import db
    from_date, to_date = db.search_window("2026-07-01", 7)
    assert to_date == "2026-07-01"
    assert from_date == "2026-06-24"


def test_search_window_zero_range():
    import db
    from_date, to_date = db.search_window("2026-07-10", 0)
    assert from_date == "2026-07-10"
    assert to_date == "2026-07-10"


def test_search_window_crosses_month_boundary():
    import db
    from_date, to_date = db.search_window("2026-03-05", 10)
    assert to_date == "2026-03-05"
    assert from_date == "2026-02-23"


# --- search() date filtering ---

def test_search_with_date_range_includes_recent():
    import db
    db.insert(raw_text="in range today", cleaned_text="in range today")
    results = db.search("in range", limit=10, start_date="", range_days=30)
    assert len(results) == 1


def test_search_excludes_record_outside_window(patch_db):
    import db
    conn = sqlite3.connect(str(patch_db))
    conn.execute(
        "INSERT INTO transcripts (timestamp, raw_text, cleaned_text) VALUES (?, ?, ?)",
        ("2020-01-01T00:00:00", "ancient text", "ancient text"),
    )
    conn.commit()
    conn.close()
    # Default 30-day window from today should not find a 2020 record
    results = db.search("ancient", limit=10, start_date="", range_days=30)
    assert results == []


def test_search_includes_record_when_window_covers_it(patch_db):
    import db
    conn = sqlite3.connect(str(patch_db))
    conn.execute(
        "INSERT INTO transcripts (timestamp, raw_text, cleaned_text) VALUES (?, ?, ?)",
        ("2020-01-01T12:00:00", "ancient text", "ancient text"),
    )
    conn.commit()
    conn.close()
    results = db.search("ancient", limit=10, start_date="2020-01-01", range_days=1)
    assert len(results) == 1


def test_search_boundary_inclusive_start_day(patch_db):
    import db
    conn = sqlite3.connect(str(patch_db))
    conn.execute(
        "INSERT INTO transcripts (timestamp, raw_text, cleaned_text) VALUES (?, ?, ?)",
        ("2026-06-10T00:00:01", "boundary start", "boundary start"),
    )
    conn.commit()
    conn.close()
    # Window from 2026-06-10 to 2026-07-10 should include the record on the start day
    results = db.search("boundary", limit=10, start_date="2026-07-10", range_days=30)
    assert len(results) == 1


def test_search_boundary_inclusive_end_day(patch_db):
    import db
    conn = sqlite3.connect(str(patch_db))
    conn.execute(
        "INSERT INTO transcripts (timestamp, raw_text, cleaned_text) VALUES (?, ?, ?)",
        ("2026-07-10T23:59:58", "boundary end", "boundary end"),
    )
    conn.commit()
    conn.close()
    results = db.search("boundary", limit=10, start_date="2026-07-10", range_days=30)
    assert len(results) == 1


def test_search_respects_limit_param():
    import db
    for i in range(10):
        db.insert(raw_text=f"keyword item {i}", cleaned_text=f"keyword item {i}")
    results = db.search("keyword", limit=3, start_date="", range_days=365)
    assert len(results) == 3


def test_search_count_matches_total():
    import db
    for i in range(10):
        db.insert(raw_text=f"countword item {i}", cleaned_text=f"countword item {i}")
    count = db.search_count("countword", start_date="", range_days=365)
    assert count == 10


def test_search_count_respects_date_window(patch_db):
    import db
    conn = sqlite3.connect(str(patch_db))
    conn.execute(
        "INSERT INTO transcripts (timestamp, raw_text, cleaned_text) VALUES (?, ?, ?)",
        ("2020-01-01T00:00:00", "old countword", "old countword"),
    )
    conn.commit()
    conn.close()
    db.insert(raw_text="recent countword", cleaned_text="recent countword")
    # Default 30-day window should count only the recent one
    assert db.search_count("countword", start_date="", range_days=30) == 1
    # Wide window should count both
    assert db.search_count("countword", start_date="", range_days=365 * 10) == 2
