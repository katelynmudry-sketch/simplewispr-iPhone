#!/usr/bin/env python3
"""M1 acceptance smoke test: record → transcribe → print raw/cleaned → verify SQLite row."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import db
import settings as settings_mod
import postprocess
from recorder import Recorder
from transcriber import discover, Transcriber

def main():
    db.init()

    # Discover model
    cfg = settings_mod.load()
    model_path = discover(cfg.get("model_path"))
    if not model_path:
        print("ERROR: No whisper model found. Run the app to download one, or set model_path in settings.")
        sys.exit(1)
    print(f"Model: {model_path}")

    # Record
    rec = Recorder()
    print("\nPress Enter to START recording...")
    input()
    rec.start()
    print("Recording... press Enter to STOP.")
    input()
    wav_path = rec.stop()
    if not wav_path:
        print("Recording too short (< 0.3s), discarded.")
        sys.exit(1)
    print(f"WAV saved: {wav_path}")

    # Transcribe
    print("Transcribing...")
    t = Transcriber()
    t.load(model_path)
    lang = cfg.get("language", "auto")
    raw, detected = t.transcribe(wav_path, lang)
    cleaned = postprocess.clean(raw, cfg.get("disfluency_list"))

    print(f"\nRaw:     {raw!r}")
    print(f"Cleaned: {cleaned!r}")

    # Save to DB
    row_id = db.insert(
        raw_text=raw,
        cleaned_text=cleaned,
        language=detected,
        audio_file=wav_path,
    )
    print(f"\nSQLite row id: {row_id}")

    # Verify
    rows = db.recent(1)
    print(f"DB query result: id={rows[0]['id']} raw={rows[0]['raw_text']!r}")
    print("\nM1 PASS")


if __name__ == "__main__":
    main()
