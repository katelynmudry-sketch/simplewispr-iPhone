"""Clipboard copy + auto-paste via osascript."""

import subprocess
import pyperclip


def copy_to_clipboard(text: str) -> None:
    pyperclip.copy(text)


def paste_at_cursor() -> bool:
    """Simulate Cmd+V via System Events. Returns True on success."""
    script = (
        'tell application "System Events" to keystroke "v" using command down'
    )
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False
