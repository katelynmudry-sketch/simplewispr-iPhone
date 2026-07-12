"""Hotkey capture: hold-down and double-tap modes via pynput."""

import time
import threading
from typing import Callable, Optional

from pynput import keyboard

DOUBLE_TAP_WINDOW = 0.4  # seconds

PRESET_KEYS = {
    "alt_r": keyboard.Key.alt_r,
    "alt": keyboard.Key.alt,
    "cmd_r": keyboard.Key.cmd_r,
    "ctrl_r": keyboard.Key.ctrl_r,
    "f13": keyboard.Key.f13,
    "f14": keyboard.Key.f14,
    "f15": keyboard.Key.f15,
    "f16": keyboard.Key.f16,
    "f17": keyboard.Key.f17,
    "f18": keyboard.Key.f18,
    "f19": keyboard.Key.f19,
}


def resolve_key(name: str):
    """Resolve a key name string to a pynput Key or KeyCode."""
    if name in PRESET_KEYS:
        return PRESET_KEYS[name]
    try:
        return keyboard.Key[name]
    except KeyError:
        pass
    try:
        return keyboard.KeyCode.from_char(name)
    except Exception:
        raise ValueError(f"Unknown key name: {name!r}")


class HotkeyListener:
    def __init__(
        self,
        key_name: str,
        mode: str,
        on_start: Callable[[], None],
        on_stop: Callable[[], None],
    ):
        self._key = resolve_key(key_name)
        self._mode = mode  # "hold" or "double_tap"
        self._on_start = on_start
        self._on_stop = on_stop
        self._listener: Optional[keyboard.Listener] = None
        self._recording = False
        self._last_press: float = 0.0
        self._lock = threading.Lock()

    def start(self) -> None:
        self._listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release,
        )
        self._listener.start()

    def stop(self) -> None:
        if self._listener:
            self._listener.stop()
            self._listener = None

    def _matches(self, key) -> bool:
        return key == self._key

    def _on_press(self, key) -> None:
        if not self._matches(key):
            return
        if self._mode == "hold":
            with self._lock:
                if not self._recording:
                    self._recording = True
                    self._on_start()
        elif self._mode == "double_tap":
            now = time.monotonic()
            with self._lock:
                if now - self._last_press <= DOUBLE_TAP_WINDOW:
                    # Second tap
                    if not self._recording:
                        self._recording = True
                        self._on_start()
                    else:
                        self._recording = False
                        self._on_stop()
                    self._last_press = 0.0
                else:
                    self._last_press = now

    def _on_release(self, key) -> None:
        if self._mode != "hold":
            return
        if not self._matches(key):
            return
        with self._lock:
            if self._recording:
                self._recording = False
                self._on_stop()
