"""Settings load/save with defaults. Persisted as JSON."""

import json
import os
from pathlib import Path
from typing import Any

APP_SUPPORT = Path.home() / "Library" / "Application Support" / "MyWispr"
SETTINGS_PATH = APP_SUPPORT / "settings.json"

DEFAULTS: dict[str, Any] = {
    "hotkey": "alt_r",
    "interaction_mode": "hold",  # "hold" or "double_tap"
    "language": "auto",
    "model_path": None,  # None = use discovery
    "disfluency_list": ["um", "uh", "like", "you know", "so", "actually",
                        "basically", "literally", "I mean", "right"],
    "audio_retention_days": 30,
    "recent_transcripts_count": 10,
    "audio_cleanup_enabled": True,
    "search_range_days": 30,
    "search_start_date": "",
    "search_results_limit": 40,
    "vocabulary_list": [],
}


def load() -> dict[str, Any]:
    if SETTINGS_PATH.exists():
        try:
            with open(SETTINGS_PATH) as f:
                stored = json.load(f)
            # Merge with defaults so new keys always present
            merged = dict(DEFAULTS)
            merged.update(stored)
            return merged
        except (json.JSONDecodeError, OSError):
            pass
    return dict(DEFAULTS)


def save(settings: dict[str, Any]) -> None:
    APP_SUPPORT.mkdir(parents=True, exist_ok=True)
    with open(SETTINGS_PATH, "w") as f:
        json.dump(settings, f, indent=2)


def get(key: str) -> Any:
    return load().get(key, DEFAULTS.get(key))


def set_key(key: str, value: Any) -> None:
    settings = load()
    settings[key] = value
    save(settings)
