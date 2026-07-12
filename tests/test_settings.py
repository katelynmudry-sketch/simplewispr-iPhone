"""Tests for settings.py round-trip."""

import json
import pytest
from pathlib import Path


def test_defaults_returned_when_no_file(tmp_path, monkeypatch):
    monkeypatch.setattr("settings.SETTINGS_PATH", tmp_path / "settings.json")
    import settings
    cfg = settings.load()
    assert cfg["hotkey"] == "alt_r"
    assert cfg["interaction_mode"] == "hold"
    assert cfg["audio_retention_days"] == 30
    assert cfg["audio_cleanup_enabled"] is True
    assert isinstance(cfg["disfluency_list"], list)
    assert "um" in cfg["disfluency_list"]


def test_round_trip(tmp_path, monkeypatch):
    p = tmp_path / "settings.json"
    monkeypatch.setattr("settings.SETTINGS_PATH", p)
    monkeypatch.setattr("settings.APP_SUPPORT", tmp_path)
    import settings
    cfg = settings.load()
    cfg["hotkey"] = "f13"
    cfg["audio_retention_days"] = 7
    settings.save(cfg)

    reloaded = settings.load()
    assert reloaded["hotkey"] == "f13"
    assert reloaded["audio_retention_days"] == 7


def test_missing_keys_filled_from_defaults(tmp_path, monkeypatch):
    p = tmp_path / "settings.json"
    p.write_text(json.dumps({"hotkey": "f14"}))
    monkeypatch.setattr("settings.SETTINGS_PATH", p)
    monkeypatch.setattr("settings.APP_SUPPORT", tmp_path)
    import settings
    cfg = settings.load()
    assert cfg["hotkey"] == "f14"
    assert "audio_retention_days" in cfg  # default filled in


def test_corrupted_file_returns_defaults(tmp_path, monkeypatch):
    p = tmp_path / "settings.json"
    p.write_text("not json {{{")
    monkeypatch.setattr("settings.SETTINGS_PATH", p)
    monkeypatch.setattr("settings.APP_SUPPORT", tmp_path)
    import settings
    cfg = settings.load()
    assert cfg["hotkey"] == "alt_r"


def test_set_key(tmp_path, monkeypatch):
    monkeypatch.setattr("settings.SETTINGS_PATH", tmp_path / "s.json")
    monkeypatch.setattr("settings.APP_SUPPORT", tmp_path)
    import settings
    settings.set_key("hotkey", "cmd_r")
    assert settings.get("hotkey") == "cmd_r"


def test_m9_defaults_present(tmp_path, monkeypatch):
    monkeypatch.setattr("settings.SETTINGS_PATH", tmp_path / "settings.json")
    import settings
    cfg = settings.load()
    assert cfg["search_range_days"] == 30
    assert cfg["search_start_date"] == ""
    assert cfg["search_results_limit"] == 40
    assert cfg["vocabulary_list"] == []


def test_vocabulary_list_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr("settings.SETTINGS_PATH", tmp_path / "s.json")
    monkeypatch.setattr("settings.APP_SUPPORT", tmp_path)
    import settings
    settings.set_key("vocabulary_list", ["MyWispr", "Dropbox", "Wispr"])
    result = settings.get("vocabulary_list")
    assert result == ["MyWispr", "Dropbox", "Wispr"]


def test_search_start_date_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr("settings.SETTINGS_PATH", tmp_path / "s.json")
    monkeypatch.setattr("settings.APP_SUPPORT", tmp_path)
    import settings
    settings.set_key("search_start_date", "2026-06-01")
    assert settings.get("search_start_date") == "2026-06-01"
    settings.set_key("search_start_date", "")
    assert settings.get("search_start_date") == ""
