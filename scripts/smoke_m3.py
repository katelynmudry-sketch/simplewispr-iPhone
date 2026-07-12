#!/usr/bin/env python3
"""M3 headless hotkey harness — prints state transitions without rumps.

Hold-down mode:  hold Right Option → prints START; release → prints STOP.
Double-tap mode: two quick taps → prints START; two more → prints STOP.

Usage:
  python scripts/smoke_m3.py [hold|double_tap]

D5 note: if events never fire after the listener starts, pynput is not
receiving input — likely a missing TCC grant (Input Monitoring or Accessibility).
"""

import sys
import os
import time
import threading

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from hotkey import HotkeyListener

MODE = sys.argv[1] if len(sys.argv) > 1 else "hold"
KEY = "alt_r"

recording = False
event_count = 0
lock = threading.Lock()


def on_start():
    global recording, event_count
    with lock:
        recording = True
        event_count += 1
        print(f"[{time.strftime('%H:%M:%S')}] START (event #{event_count})", flush=True)


def on_stop():
    global recording, event_count
    with lock:
        recording = False
        event_count += 1
        print(f"[{time.strftime('%H:%M:%S')}] STOP  (event #{event_count})", flush=True)


def main():
    print(f"Mode: {MODE}  Key: {KEY}")
    print("Listener starting — if no events arrive within 5s of pressing the key,")
    print("pynput is blocked (missing TCC grant). Press Ctrl-C to exit.\n")

    listener = HotkeyListener(
        key_name=KEY,
        mode=MODE,
        on_start=on_start,
        on_stop=on_stop,
    )
    listener.start()
    print("Listener running. Try the hotkey now.")

    try:
        while True:
            time.sleep(0.1)
    except KeyboardInterrupt:
        listener.stop()
        print(f"\nDone. Total events: {event_count}")


if __name__ == "__main__":
    main()
