"""Tests for cleanup.py — temp WAVs at faked mtimes."""

import os
import time

import pytest


@pytest.fixture(autouse=True)
def patch_db(tmp_path, monkeypatch):
    monkeypatch.setattr("db.DB_PATH", tmp_path / "transcripts.db")
    monkeypatch.setattr("db.APP_SUPPORT", tmp_path)
    import db
    db.init()


@pytest.fixture
def audio_dir(tmp_path):
    d = tmp_path / "audio"
    d.mkdir()
    return d


def _make_wav(audio_dir, name: str, age_days: float):
    """Create a fake WAV file with mtime age_days in the past."""
    p = audio_dir / name
    p.write_bytes(b"RIFF fake wav")
    old = time.time() - age_days * 86400
    os.utime(p, (old, old))
    return p


def _settings(monkeypatch, **overrides):
    import settings as settings_mod
    cfg = dict(settings_mod.DEFAULTS)
    cfg.update(overrides)
    monkeypatch.setattr("cleanup.settings_mod.load", lambda: cfg)


def test_old_wav_deleted(audio_dir, monkeypatch):
    import cleanup
    _settings(monkeypatch, audio_retention_days=30)
    old = _make_wav(audio_dir, "20260101-120000.wav", age_days=40)
    deleted = cleanup.run_cleanup(audio_dir)
    assert deleted == [str(old)]
    assert not old.exists()


def test_recent_wav_kept(audio_dir, monkeypatch):
    import cleanup
    _settings(monkeypatch, audio_retention_days=30)
    recent = _make_wav(audio_dir, "20260701-120000.wav", age_days=5)
    deleted = cleanup.run_cleanup(audio_dir)
    assert deleted == []
    assert recent.exists()


def test_mixed_ages(audio_dir, monkeypatch):
    import cleanup
    _settings(monkeypatch, audio_retention_days=30)
    old = _make_wav(audio_dir, "old.wav", age_days=31)
    new = _make_wav(audio_dir, "new.wav", age_days=29)
    deleted = cleanup.run_cleanup(audio_dir)
    assert deleted == [str(old)]
    assert not old.exists()
    assert new.exists()


def test_db_row_nulled_transcript_kept(audio_dir, monkeypatch):
    import cleanup
    import db
    _settings(monkeypatch, audio_retention_days=30)
    old = _make_wav(audio_dir, "old.wav", age_days=40)
    db.insert(raw_text="hello", cleaned_text="hello", audio_file=str(old))
    cleanup.run_cleanup(audio_dir)
    rows = db.recent(1)
    assert rows[0]["audio_file"] is None
    assert rows[0]["raw_text"] == "hello"


def test_disabled_deletes_nothing(audio_dir, monkeypatch):
    import cleanup
    _settings(monkeypatch, audio_cleanup_enabled=False)
    old = _make_wav(audio_dir, "old.wav", age_days=400)
    deleted = cleanup.run_cleanup(audio_dir)
    assert deleted == []
    assert old.exists()


def test_custom_retention(audio_dir, monkeypatch):
    import cleanup
    _settings(monkeypatch, audio_retention_days=7)
    old = _make_wav(audio_dir, "old.wav", age_days=8)
    new = _make_wav(audio_dir, "new.wav", age_days=6)
    deleted = cleanup.run_cleanup(audio_dir)
    assert deleted == [str(old)]
    assert new.exists()


def test_non_wav_files_untouched(audio_dir, monkeypatch):
    import cleanup
    _settings(monkeypatch, audio_retention_days=30)
    other = audio_dir / "notes.txt"
    other.write_text("keep me")
    old_ts = time.time() - 100 * 86400
    os.utime(other, (old_ts, old_ts))
    deleted = cleanup.run_cleanup(audio_dir)
    assert deleted == []
    assert other.exists()


def test_missing_audio_dir(tmp_path, monkeypatch):
    import cleanup
    _settings(monkeypatch, audio_retention_days=30)
    deleted = cleanup.run_cleanup(tmp_path / "does-not-exist")
    assert deleted == []


def test_empty_audio_dir(audio_dir, monkeypatch):
    import cleanup
    _settings(monkeypatch, audio_retention_days=30)
    assert cleanup.run_cleanup(audio_dir) == []
