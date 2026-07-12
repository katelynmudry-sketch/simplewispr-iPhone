"""Audio file cleanup: delete WAVs older than retention threshold."""

import os
import time
from pathlib import Path

import db
import settings as settings_mod

AUDIO_DIR = Path.home() / "Library" / "Application Support" / "MyWispr" / "audio"


def run_cleanup(audio_dir: Path = AUDIO_DIR) -> list[str]:
    """Delete WAV files older than retention setting. Returns list of deleted paths."""
    cfg = settings_mod.load()
    if not cfg.get("audio_cleanup_enabled", True):
        return []

    retention_days = cfg.get("audio_retention_days", 30)
    cutoff = time.time() - retention_days * 86400

    deleted = []
    if not audio_dir.exists():
        return []

    for wav in audio_dir.glob("*.wav"):
        try:
            if wav.stat().st_mtime < cutoff:
                db.null_audio_file(str(wav))
                wav.unlink()
                deleted.append(str(wav))
        except OSError:
            pass

    return deleted
