"""MyWispr — menu bar push-to-talk transcription app."""

import queue
import subprocess
import sys
import threading
from datetime import date
from enum import Enum, auto
from pathlib import Path
from typing import Optional

import rumps
from AppKit import (
    NSAlert, NSApplication, NSAttributedString, NSBezierPath, NSColor, NSFont,
    NSFontAttributeName, NSForegroundColorAttributeName, NSFloatingWindowLevel,
    NSImage, NSScreen,
)
from Foundation import NSRunLoop, NSRunLoopCommonModes

import cleanup
import db
import paste
import postprocess
import recorder as recorder_mod
import settings as settings_mod
import transcriber as transcriber_mod
from hotkey import HotkeyListener


# ------------------------------------------------------------------
# 8a helpers — dialog activation + icon
# ------------------------------------------------------------------

def _make_mw_icon() -> NSImage:
    """Programmatic 128×128 MW icon (no asset file required)."""
    size = 128.0
    image = NSImage.alloc().initWithSize_((size, size))
    image.lockFocus()
    NSColor.colorWithSRGBRed_green_blue_alpha_(0.15, 0.15, 0.15, 1.0).set()
    NSBezierPath.fillRect_((0.0, 0.0, size, size))
    label = NSAttributedString.alloc().initWithString_attributes_(
        "MW",
        {
            NSFontAttributeName: NSFont.boldSystemFontOfSize_(52),
            NSForegroundColorAttributeName: NSColor.whiteColor(),
        },
    )
    label.drawAtPoint_((14.0, 36.0))
    image.unlockFocus()
    return image


def _alert(title="", message="", ok="OK", cancel=None, other=None):
    """Show an NSAlert that floats above all normal windows.

    Replicates rumps.alert's return convention: 1 = ok clicked, 0 = cancel clicked.
    Uses NSFloatingWindowLevel so the panel appears in front even when MyWispr is
    not the active application (activateIgnoringOtherApps_ alone is unreliable on
    macOS 14+ for LSUIElement apps).
    """
    NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
    # Use the same legacy API as rumps so return values stay compatible
    # (NSAlertDefaultReturn=1 for ok, NSAlertAlternateReturn=0 for cancel)
    alert = NSAlert.alertWithMessageText_defaultButton_alternateButton_otherButton_informativeTextWithFormat_(
        title or "", ok, cancel, other, (message or "").replace("%", "%%")
    )
    alert.setAlertStyle_(0)
    alert.window().setLevel_(NSFloatingWindowLevel)
    return alert.runModal()


def _window(w):
    """Run a rumps.Window, floating it above all normal windows."""
    NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
    # w._alert is the NSAlert created in rumps.Window.__init__ — set its level
    # before runModal so it floats above other apps' windows
    w._alert.window().setLevel_(NSFloatingWindowLevel)
    return w.run()


class State(Enum):
    IDLE = auto()
    RECORDING = auto()
    PROCESSING = auto()
    PERMISSION_NEEDED = auto()
    MODEL_NEEDED = auto()


TICK = 0.25


class AppState:
    def __init__(self):
        self._lock = threading.Lock()
        self.state = State.IDLE
        self.message: str = ""
        self.missing_permissions: list[str] = []

    def set(self, state: State, message: str = "") -> None:
        with self._lock:
            self.state = state
            self.message = message

    def get(self) -> tuple[State, str]:
        with self._lock:
            return self.state, self.message


class MyWisprApp(rumps.App):
    def __init__(self):
        super().__init__("MyWispr", title="MW", quit_button=None)

        # 8a: replace Python-rocket icon so alerts show MW, not the venv Python icon
        try:
            NSApplication.sharedApplication().setApplicationIconImage_(_make_mw_icon())
        except Exception as e:
            print(f"[init] icon: {e}", flush=True)

        self._app_state = AppState()
        self._job_queue: queue.Queue = queue.Queue()
        # Worker thread posts (title, message) tuples; timer shows them on main thread
        self._alert_queue: queue.SimpleQueue = queue.SimpleQueue()
        self._recorder = recorder_mod.Recorder()
        self._transcriber = transcriber_mod.Transcriber()
        self._hotkey_listener: Optional[HotkeyListener] = None
        self._model_path: Optional[str] = None
        self._recent: list[dict] = []
        self._last_state: Optional[State] = None
        self._menu_dirty = False
        self._tick_flip = False
        # 8b: persists the last search-results submenu between menu rebuilds
        self._search_results_menu: Optional[rumps.MenuItem] = None

        db.init()
        self._build_menu(State.IDLE)
        self._last_state = State.IDLE

        threading.Thread(target=self._worker, daemon=True).start()
        # rumps tracks timers weakly; keep a strong reference or it gets GC'd
        self._timer = rumps.Timer(self._tick, TICK)
        self._timer.start()
        # 8c: also schedule in NSRunLoopCommonModes so the timer fires during
        # modal sessions (rumps adds it to NSDefaultRunLoopMode only)
        try:
            NSRunLoop.currentRunLoop().addTimer_forMode_(
                self._timer._nstimer, NSRunLoopCommonModes
            )
        except Exception as e:
            print(f"[init] common-modes timer: {e}", flush=True)
        self._last_screen_count = len(NSScreen.screens())
        self._job_queue.put(("preflight", None))

    # ------------------------------------------------------------------
    # Timer — main thread only
    # ------------------------------------------------------------------

    def _tick(self, _timer):
        # Show any alert queued by the worker thread
        try:
            title, msg = self._alert_queue.get_nowait()
            _alert(title, msg)
        except queue.Empty:
            pass

        state, message = self._app_state.get()
        self._tick_flip = not self._tick_flip

        screen_count = len(NSScreen.screens())
        if screen_count != self._last_screen_count:
            self._last_screen_count = screen_count
            self._refresh_status_item()

        if state == State.IDLE:
            self.title = "MW"
        elif state == State.RECORDING:
            self.title = "MW ■" if self._tick_flip else "MW □"
        elif state == State.PROCESSING:
            self.title = f"MW {message}" if message else "MW …"
        elif state == State.PERMISSION_NEEDED:
            self.title = "MW ⚠"
        elif state == State.MODEL_NEEDED:
            self.title = "MW ↓"

        # State change is itself a dirty signal; data changes set the flag directly
        if state != self._last_state:
            self._menu_dirty = True
            self._last_state = state

        if self._menu_dirty:
            self._build_menu(state)
            self._menu_dirty = False

    def _refresh_status_item(self):
        """Force NSStatusItem to re-render after a display configuration change."""
        try:
            nsapp = NSApplication.sharedApplication().delegate()
            si = nsapp.nsstatusitem
            si.setLength_(0)
            si.setLength_(-1)
        except Exception as e:
            print(f"[tick] screen-change refresh: {e}", flush=True)

    def _mark_menu_dirty(self):
        """Thread-safe: request menu rebuild on next timer tick."""
        self._menu_dirty = True

    def _post_alert(self, title: str, message: str):
        """Thread-safe: show alert on next timer tick (main thread)."""
        self._alert_queue.put((title, message))

    # ------------------------------------------------------------------
    # Menu construction — main thread only
    # ------------------------------------------------------------------

    def _build_menu(self, state: State):
        self.menu.clear()

        if state == State.PERMISSION_NEEDED:
            missing = self._app_state.missing_permissions
            label = "⚠ Missing: " + ", ".join(missing) + " — click for instructions"
            self.menu.add(rumps.MenuItem(label, callback=lambda _, m=missing: self._show_permission_help(m)))
            self.menu.add(rumps.separator)

        elif state == State.MODEL_NEEDED:
            self.menu.add(rumps.MenuItem(
                "Download base model (~142 MB)",
                callback=lambda _: self._job_queue.put(("download_model", "base")),
            ))
            self.menu.add(rumps.MenuItem(
                "Download turbo model (~1.6 GB, better quality)",
                callback=lambda _: self._job_queue.put(("download_model", "turbo")),
            ))
            self.menu.add(rumps.MenuItem(
                "Choose existing model file…",
                callback=self._choose_model_file,
            ))
            self.menu.add(rumps.separator)

        # Recent transcripts submenu
        n = settings_mod.get("recent_transcripts_count") or 10
        self._recent = [dict(r) for r in db.recent(n)]
        recent_menu = rumps.MenuItem("Recent Transcripts")
        if self._recent:
            for i, row in enumerate(self._recent, 1):
                ts = (row["timestamp"] or "")[:16]
                preview = (row["cleaned_text"] or row["raw_text"] or "")[:60]
                rid = row["id"]
                recent_menu.add(rumps.MenuItem(
                    f"{i}. {ts}  {preview}",
                    callback=lambda _, r=rid: self._copy_recent(r),
                ))
        else:
            placeholder = rumps.MenuItem("(no transcripts yet)")
            placeholder.set_callback(None)
            recent_menu.add(placeholder)
        self.menu.add(recent_menu)

        self.menu.add(rumps.separator)
        self.menu.add(rumps.MenuItem("Search Transcripts…", callback=self._search))
        if self._search_results_menu is not None:
            self.menu.add(self._search_results_menu)
        self.menu.add(rumps.separator)
        self.menu.add(self._build_settings_menu())
        self.menu.add(rumps.separator)
        self.menu.add(rumps.MenuItem("About MyWispr", callback=self._about))
        self.menu.add(rumps.MenuItem("Quit", callback=self._quit))

    def _build_settings_menu(self) -> rumps.MenuItem:
        cfg = settings_mod.load()
        s = rumps.MenuItem("Settings")

        # Hotkey
        hotkey_menu = rumps.MenuItem("Hotkey")
        current_key = cfg.get("hotkey", "alt_r")
        presets = [
            ("Right Option (default)", "alt_r"),
            ("Left Option", "alt"),
            ("Right Command", "cmd_r"),
            ("Right Ctrl", "ctrl_r"),
            ("F13", "f13"), ("F14", "f14"), ("F15", "f15"),
            ("F16", "f16"), ("F17", "f17"), ("F18", "f18"), ("F19", "f19"),
        ]
        for label, key_name in presets:
            item = rumps.MenuItem(label, callback=lambda _, k=key_name: self._set_hotkey(k))
            if key_name == current_key:
                item.state = 1
            hotkey_menu.add(item)
        hotkey_menu.add(rumps.MenuItem("Custom…", callback=self._custom_hotkey))
        s.add(hotkey_menu)

        # Mode
        mode_menu = rumps.MenuItem("Mode")
        current_mode = cfg.get("interaction_mode", "hold")
        for label, mode in [("Hold-down", "hold"), ("Double-tap", "double_tap")]:
            item = rumps.MenuItem(label, callback=lambda _, m=mode: self._set_mode(m))
            if mode == current_mode:
                item.state = 1
            mode_menu.add(item)
        s.add(mode_menu)

        s.add(rumps.separator)

        # Language
        lang_menu = rumps.MenuItem("Language")
        current_lang = cfg.get("language", "auto")
        langs = [
            ("Auto-detect", "auto"), ("English", "en"), ("Spanish", "es"),
            ("French", "fr"), ("German", "de"), ("Italian", "it"),
            ("Portuguese", "pt"), ("Japanese", "ja"), ("Korean", "ko"),
            ("Chinese", "zh"), ("Tagalog", "tl"),
        ]
        for label, code in langs:
            item = rumps.MenuItem(label, callback=lambda _, c=code: self._set_language(c))
            if code == current_lang:
                item.state = 1
            lang_menu.add(item)
        lang_menu.add(rumps.MenuItem("Other…", callback=self._custom_language))
        s.add(lang_menu)

        # Model
        model_menu = rumps.MenuItem("Model")
        active_name = Path(self._model_path).name if self._model_path else "(none found)"
        info = rumps.MenuItem(f"Active: {active_name}")
        info.set_callback(None)
        model_menu.add(info)
        model_menu.add(rumps.MenuItem("Choose model file…", callback=self._choose_model_file))
        model_menu.add(rumps.MenuItem("Use automatic discovery", callback=self._use_auto_model))
        s.add(model_menu)

        s.add(rumps.MenuItem("Edit disfluency list…", callback=self._edit_disfluency))
        s.add(rumps.MenuItem("Edit vocabulary…", callback=self._edit_vocabulary))

        s.add(rumps.separator)

        s.add(rumps.MenuItem("Audio retention…", callback=self._edit_retention))
        s.add(rumps.MenuItem("Recent transcript count…", callback=self._edit_recent_count))

        # Search submenu with inline current values (stale-state guard)
        search_menu = rumps.MenuItem("Search options")
        start_date = cfg.get("search_start_date") or ""
        range_days = cfg.get("search_range_days") or 30
        limit = cfg.get("search_results_limit") or 40
        start_label = start_date if start_date else "(today)"
        search_menu.add(rumps.MenuItem(
            f"Start date: {start_label}",
            callback=self._edit_search_start_date,
        ))
        search_menu.add(rumps.MenuItem(
            f"Range: {range_days} days",
            callback=self._edit_search_range_days,
        ))
        search_menu.add(rumps.MenuItem(
            f"Results limit: {limit}",
            callback=self._edit_search_results_limit,
        ))
        s.add(search_menu)
        return s

    # ------------------------------------------------------------------
    # Worker thread
    # ------------------------------------------------------------------

    def _worker(self):
        while True:
            job, payload = self._job_queue.get()
            try:
                if job == "preflight":
                    self._do_preflight()
                elif job == "transcribe":
                    self._do_transcribe(payload)
                elif job == "download_model":
                    self._do_download_model(payload)
                elif job == "cleanup":
                    cleanup.run_cleanup()
            except Exception as e:
                print(f"[worker] {job} error: {e}", flush=True)

    def _do_preflight(self):
        missing = _check_permissions()
        if missing:
            self._app_state.missing_permissions = missing
            self._app_state.set(State.PERMISSION_NEEDED)
            return

        cfg = settings_mod.load()
        model_path = transcriber_mod.discover(cfg.get("model_path"))
        if not model_path:
            self._app_state.set(State.MODEL_NEEDED)
            return

        self._model_path = model_path
        self._app_state.set(State.PROCESSING, "⏳ Loading…")
        self._transcriber.load(model_path)
        self._app_state.set(State.IDLE)
        self._mark_menu_dirty()
        self._start_hotkey()
        self._job_queue.put(("cleanup", None))

    def _do_transcribe(self, wav_path: str):
        self._app_state.set(State.PROCESSING)
        try:
            cfg = settings_mod.load()
            lang = cfg.get("language", "auto")
            initial_prompt = transcriber_mod.build_initial_prompt(cfg.get("vocabulary_list") or [])
            raw, detected_lang = self._transcriber.transcribe(wav_path, lang, initial_prompt=initial_prompt)
            cleaned = postprocess.clean(raw, cfg.get("disfluency_list"))
            db.insert(
                raw_text=raw,
                cleaned_text=cleaned,
                language=detected_lang,
                audio_file=wav_path,
            )
            paste.copy_to_clipboard(cleaned)
            ok = paste.paste_at_cursor()
            if not ok:
                print("[paste] failed — text is on clipboard", flush=True)
            self._mark_menu_dirty()
        except Exception as e:
            print(f"[transcribe] error: {e}", flush=True)
            self._post_alert("Transcription failed", f"{e}\n\nThe recording is kept at:\n{wav_path}")
        finally:
            self._app_state.set(State.IDLE)

    def _do_download_model(self, model_key: str):
        self._app_state.set(State.PROCESSING, "⬇ 0%")

        def progress(pct):
            self._app_state.set(State.PROCESSING, f"⬇ {int(pct * 100)}%")

        try:
            path = transcriber_mod.download_model(model_key, progress_cb=progress)
            self._model_path = path
            self._app_state.set(State.PROCESSING, "⏳ Loading…")
            self._transcriber.load(path)
            self._app_state.set(State.IDLE)
            self._mark_menu_dirty()
            self._start_hotkey()
            self._post_alert("MyWispr", "Model downloaded and ready.")
        except Exception as e:
            self._app_state.set(State.MODEL_NEEDED)
            self._post_alert("Download failed", str(e))

    # ------------------------------------------------------------------
    # Hotkey
    # ------------------------------------------------------------------

    def _start_hotkey(self):
        if self._hotkey_listener:
            self._hotkey_listener.stop()
        cfg = settings_mod.load()
        self._hotkey_listener = HotkeyListener(
            key_name=cfg.get("hotkey", "alt_r"),
            mode=cfg.get("interaction_mode", "hold"),
            on_start=self._hotkey_start,
            on_stop=self._hotkey_stop,
        )
        self._hotkey_listener.start()

    def _hotkey_start(self):
        state, _ = self._app_state.get()
        if state != State.IDLE:
            return
        self._app_state.set(State.RECORDING)
        self._recorder.start()

    def _hotkey_stop(self):
        state, _ = self._app_state.get()
        if state != State.RECORDING:
            return
        wav_path = self._recorder.stop()
        if wav_path:
            self._job_queue.put(("transcribe", wav_path))
        else:
            self._app_state.set(State.IDLE)

    # ------------------------------------------------------------------
    # Settings callbacks — menu callbacks run on main thread
    # ------------------------------------------------------------------

    def _set_hotkey(self, key_name: str):
        settings_mod.set_key("hotkey", key_name)
        self._start_hotkey()
        self._mark_menu_dirty()

    def _set_mode(self, mode: str):
        settings_mod.set_key("interaction_mode", mode)
        self._start_hotkey()
        self._mark_menu_dirty()

    def _set_language(self, code: str):
        settings_mod.set_key("language", code)
        self._mark_menu_dirty()

    def _custom_hotkey(self, _):
        w = rumps.Window(
            "Enter a pynput key name (e.g. f13, alt_r, cmd_r):",
            "Custom Hotkey",
            default_text=settings_mod.get("hotkey") or "alt_r",
            ok="Set",
            cancel="Cancel",
            dimensions=(300, 40),
        )
        resp = _window(w)
        if resp.clicked:
            name = resp.text.strip()
            from hotkey import resolve_key
            try:
                resolve_key(name)
                settings_mod.set_key("hotkey", name)
                self._start_hotkey()
                self._mark_menu_dirty()
            except ValueError as e:
                _alert("Invalid key", str(e))

    def _custom_language(self, _):
        w = rumps.Window(
            "Enter a Whisper language code (e.g. nl, sv, ar):",
            "Custom Language",
            ok="Set",
            cancel="Cancel",
            dimensions=(300, 40),
        )
        resp = _window(w)
        if resp.clicked:
            code = resp.text.strip().lower()
            if code:
                settings_mod.set_key("language", code)
                self._mark_menu_dirty()

    def _choose_model_file(self, _):
        w = rumps.Window(
            "Enter absolute path to a compatible whisper.cpp .bin model file:",
            "Choose Model File",
            default_text=settings_mod.get("model_path") or "",
            ok="Set",
            cancel="Cancel",
            dimensions=(500, 40),
        )
        resp = _window(w)
        if resp.clicked:
            path = resp.text.strip()
            p = Path(path)
            if not p.exists():
                _alert("File not found", path)
                return
            if not path.endswith(".bin"):
                _alert("Invalid file", "Model file must end in .bin")
                return
            settings_mod.set_key("model_path", path)
            self._job_queue.put(("preflight", None))

    def _use_auto_model(self, _):
        settings_mod.set_key("model_path", None)
        self._job_queue.put(("preflight", None))

    def _edit_disfluency(self, _):
        current = settings_mod.get("disfluency_list") or []
        w = rumps.Window(
            "Edit disfluency list (comma-separated):",
            "Disfluency List",
            default_text=", ".join(current),
            ok="Save",
            cancel="Cancel",
            dimensions=(400, 40),
        )
        resp = _window(w)
        if resp.clicked:
            entries = [e.strip() for e in resp.text.split(",") if e.strip()]
            settings_mod.set_key("disfluency_list", entries)

    def _edit_retention(self, _):
        current = settings_mod.get("audio_retention_days")
        w = rumps.Window(
            "Delete WAV files older than N days (0 = disable cleanup):",
            "Audio Retention",
            default_text=str(current),
            ok="Save",
            cancel="Cancel",
            dimensions=(300, 40),
        )
        resp = _window(w)
        if resp.clicked:
            try:
                days = int(resp.text.strip())
                settings_mod.set_key("audio_retention_days", max(0, days))
                settings_mod.set_key("audio_cleanup_enabled", days > 0)
            except ValueError:
                _alert("Invalid value", "Please enter a whole number.")

    def _edit_recent_count(self, _):
        current = settings_mod.get("recent_transcripts_count")
        w = rumps.Window(
            "Number of recent transcripts to show in menu:",
            "Recent Transcripts Count",
            default_text=str(current),
            ok="Save",
            cancel="Cancel",
            dimensions=(300, 40),
        )
        resp = _window(w)
        if resp.clicked:
            try:
                n = int(resp.text.strip())
                settings_mod.set_key("recent_transcripts_count", max(1, n))
                self._mark_menu_dirty()
            except ValueError:
                _alert("Invalid value", "Please enter a whole number.")

    def _edit_search_start_date(self, _):
        current = settings_mod.get("search_start_date") or ""
        w = rumps.Window(
            "Search end-anchor date (YYYY-MM-DD), or empty for today:",
            "Search Start Date",
            default_text=current,
            ok="Save",
            cancel="Cancel",
            dimensions=(300, 40),
        )
        resp = _window(w)
        if resp.clicked:
            val = resp.text.strip()
            if val:
                try:
                    date.fromisoformat(val)
                except ValueError:
                    _alert("Invalid date", "Enter a date as YYYY-MM-DD, or leave blank for today.")
                    return
            settings_mod.set_key("search_start_date", val)
            self._mark_menu_dirty()

    def _edit_search_range_days(self, _):
        current = settings_mod.get("search_range_days") or 30
        w = rumps.Window(
            "Number of days to look back from the start date:",
            "Search Range",
            default_text=str(current),
            ok="Save",
            cancel="Cancel",
            dimensions=(300, 40),
        )
        resp = _window(w)
        if resp.clicked:
            try:
                days = int(resp.text.strip())
                settings_mod.set_key("search_range_days", max(1, days))
                self._mark_menu_dirty()
            except ValueError:
                _alert("Invalid value", "Please enter a whole number.")

    def _edit_search_results_limit(self, _):
        current = settings_mod.get("search_results_limit") or 40
        w = rumps.Window(
            "Maximum number of search results to show:",
            "Search Results Limit",
            default_text=str(current),
            ok="Save",
            cancel="Cancel",
            dimensions=(300, 40),
        )
        resp = _window(w)
        if resp.clicked:
            try:
                limit = int(resp.text.strip())
                settings_mod.set_key("search_results_limit", max(1, limit))
                self._mark_menu_dirty()
            except ValueError:
                _alert("Invalid value", "Please enter a whole number.")

    def _edit_vocabulary(self, _):
        current = settings_mod.get("vocabulary_list") or []
        w = rumps.Window(
            "Terms Whisper should recognize (comma-separated):",
            "Custom Vocabulary",
            default_text=", ".join(current),
            ok="Save",
            cancel="Cancel",
            dimensions=(400, 40),
        )
        resp = _window(w)
        if resp.clicked:
            entries = [e.strip() for e in resp.text.split(",") if e.strip()]
            settings_mod.set_key("vocabulary_list", entries)

    def _search(self, _):
        cfg = settings_mod.load()
        start_date = cfg.get("search_start_date") or ""
        range_days = cfg.get("search_range_days") or 30
        limit = cfg.get("search_results_limit") or 40
        from_date, to_date = db.search_window(start_date, range_days)
        w = rumps.Window(
            f"Search transcripts ({from_date} → {to_date}):",
            "Search Transcripts",
            ok="Search",
            cancel="Cancel",
            dimensions=(320, 40),
        )
        resp = _window(w)
        if not resp.clicked:
            return
        keyword = resp.text.strip()
        if not keyword:
            return
        rows = db.search(keyword, limit=limit, start_date=start_date, range_days=range_days)
        if not rows:
            _alert("No results", f'No transcripts matching "{keyword}" in {from_date} → {to_date}.')
            return
        # Only query the true total when the limit was hit (avoids extra DB call otherwise)
        if len(rows) == limit:
            total = db.search_count(keyword, start_date=start_date, range_days=range_days)
        else:
            total = len(rows)
        submenu = rumps.MenuItem("Search Results")
        for i, row in enumerate(rows, 1):
            ts = (row["timestamp"] or "")[:16]
            body = row["cleaned_text"] or row["raw_text"] or ""
            preview = body[:60]
            label = f"{i}. [{ts}] {preview}" + ("…" if len(body) > 60 else "")
            submenu.add(rumps.MenuItem(
                label,
                callback=lambda _, t=body: paste.copy_to_clipboard(t),
            ))
        self._search_results_menu = submenu
        self._mark_menu_dirty()
        if total > limit:
            _alert(
                f"{limit} of {total} result(s) shown",
                f'Only the first {limit} are in the menu.\n'
                f'Increase "Results limit" in Settings → Search to see more.\n'
                f'Click "Search Results" to browse and copy.',
                ok="OK",
            )
        else:
            _alert(
                f"{total} result(s) found",
                'Click "Search Results" in the MyWispr menu to browse and copy.',
                ok="OK",
            )

    def _copy_recent(self, row_id: int):
        for row in self._recent:
            if row["id"] == row_id:
                paste.copy_to_clipboard(row["cleaned_text"] or row["raw_text"] or "")
                return

    _PERMISSION_PANES = {
        "Accessibility": "Privacy_Accessibility",
        "Microphone": "Privacy_Microphone",
    }

    def _show_permission_help(self, missing: list[str]):
        names = " and ".join(missing)
        # Open the pane for the first missing permission; if both are missing,
        # Accessibility comes first in _check_permissions and the alert names both.
        pane = self._PERMISSION_PANES.get(missing[0] if missing else "Accessibility",
                                          "Privacy_Accessibility")
        response = _alert(
            f"MyWispr needs {names} access",
            f"1. Click 'Open System Settings'.\n"
            f"2. Find MyWispr in the list and turn it ON.\n"
            f"3. Quit MyWispr and relaunch it.",
            ok="Open System Settings",
            cancel="Close",
        )
        if response:
            subprocess.run(
                ["open", f"x-apple.systempreferences:com.apple.preference.security?{pane}"],
                check=False,
            )

    def _about(self, _):
        _alert(
            title="MyWispr",
            message="Local push-to-talk voice transcription.\n\nPowered by whisper.cpp.",
        )

    def _quit(self, _):
        if self._hotkey_listener:
            self._hotkey_listener.stop()
        rumps.quit_application()


# ------------------------------------------------------------------
# Permission checks — called from worker thread, no AppKit
# ------------------------------------------------------------------

def _check_permissions() -> list[str]:
    missing = []
    if not _check_accessibility():
        missing.append("Accessibility")
    if not _check_microphone():
        missing.append("Microphone")
    return missing


def _check_accessibility() -> bool:
    try:
        from ApplicationServices import AXIsProcessTrusted
        return bool(AXIsProcessTrusted())
    except Exception:
        return False


def _check_microphone() -> bool:
    import sounddevice as sd
    try:
        stream = sd.InputStream(samplerate=16000, channels=1, dtype="float32")
        stream.start()
        stream.stop()
        stream.close()
        return True
    except Exception:
        return False


# ------------------------------------------------------------------
# Entry point
# ------------------------------------------------------------------

def _patch_pynput_keycode_context():
    """macOS 15 requires TISCopyCurrentKeyboardInputSource on the main queue.
    pynput calls it from its listener thread → EXC_BREAKPOINT/SIGTRAP crash.
    Pre-fetch the keyboard layout here (main thread) and replace
    pynput.keyboard._darwin.keycode_context with a cached version so the
    listener thread never calls TIS directly.
    """
    import contextlib
    try:
        import pynput._util.darwin as _pd
        import pynput.keyboard._darwin as _kd
        with _pd.keycode_context() as ctx:
            cached = ctx

        @contextlib.contextmanager
        def _cached():
            yield cached

        _pd.keycode_context = _cached
        _kd.keycode_context = _cached
    except Exception:
        pass


def main():
    if "--cleanup-only" in sys.argv:
        db.init()
        deleted = cleanup.run_cleanup()
        print(f"[cleanup] deleted {len(deleted)} file(s)", flush=True)
        return
    _patch_pynput_keycode_context()
    db.init()
    MyWisprApp().run()


if __name__ == "__main__":
    main()
