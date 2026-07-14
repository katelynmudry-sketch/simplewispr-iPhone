# MyWispr

A macOS menu-bar push-to-talk transcription tool inspired by [WisprFlow](https://wisprflow.ai). Hold a hotkey, speak, release — your words appear at the cursor. Fully local, no cloud dependency, no NVIDIA GPU required.

## How it works

Hold (or double-tap) the hotkey → speak → release → transcript is auto-pasted at the cursor. If auto-paste fails (password field, secure input), the text lands on your clipboard. Recent transcripts are always available from the menu bar.

All audio and transcripts are stored locally. Transcription uses [whisper.cpp](https://github.com/ggerganov/whisper.cpp) via `pywhispercpp`.

## Status

v1 feature-complete. Core app, .app bundle, dialog UX, search, and custom vocabulary are all shipped and working on the developer machine. Next up: validating the install experience on a second machine (M10 — Gatekeeper friction, Intel compatibility, INSTALL.md end-to-end with a non-technical user).

**iOS companion — actively in progress, on-device testing pending.** A separate iPhone app (custom keyboard extension, not a port — see `ios/README.md`) builds successfully both via Xcode and via CI ([`build-ios-ipa.yml` run history](../../actions/workflows/build-ios-ipa.yml), producing a sideload-ready unsigned `.ipa`). It has not yet been verified end-to-end on a physical device — installing the keyboard, granting permissions, and confirming dictation + cleanup actually insert text correctly all remain to be checked. See `ios/README.md`'s status note for the checklist.

## For end users

See [INSTALL.md](INSTALL.md) — step-by-step from a fresh machine to a working first transcription, including model download and permissions.

---

## For contributors

### Architecture overview

```
src/
├── main.py          # rumps menu bar app, state machine, UI-sync timer
├── hotkey.py        # pynput hold-down / double-tap hotkey capture
├── recorder.py      # sounddevice audio recording → .wav
├── transcriber.py   # pywhispercpp wrapper, model discovery
├── postprocess.py   # disfluency removal (pure Python, regex-based)
├── paste.py         # pyperclip clipboard + osascript auto-paste
├── db.py            # SQLite transcript storage and search
├── settings.py      # JSON settings load/save with defaults
└── cleanup.py       # audio file retention / WAV deletion logic

scripts/
├── setup.sh         # creates venv, installs deps, installs launchd plist
├── build-app.sh     # generates /Applications/MyWispr.app bundle
├── run.sh           # app entrypoint (exec'd by the .app trampoline)
└── trampoline.c     # Mach-O bundle executable source (arm64+x86_64)

launchd/
└── com.mywispr.cleanup.plist   # daily audio cleanup job

tests/               # pytest unit tests (db, settings, postprocess, cleanup)
```

### Threading model (important)

There are exactly three thread contexts. Violating this causes crashes.

- **Main thread** — owned by `rumps` / AppKit. All menu and icon updates happen here via a 0.25 s `rumps.Timer`. Never touch `rumps` from another thread.
- **pynput listener thread** — fires on key events. Callbacks must be near-instant: record a timestamp, flip a flag, done. No I/O.
- **Worker thread** — single long-lived daemon thread that serializes the pipeline: stop recording → write WAV → transcribe → postprocess → save to SQLite → clipboard → paste.

All shared state lives in an `AppState` object guarded by a `threading.Lock` in `main.py`. The UI-sync timer reads it and updates the menu bar; the worker writes to it. Nothing else touches `rumps`.

### App bundle and TCC

`/Applications/MyWispr.app` is a hand-rolled minimal bundle — not py2app. The executable is a precompiled Mach-O trampoline (`scripts/trampoline`, universal arm64+x86_64) that `execv`s `/bin/bash run.sh`. This chain matters for macOS TCC:

- LaunchServices requires a Mach-O bundle executable (bare bash scripts are silently ignored on macOS 15)
- `LSRequiresNativeExecution` in `Info.plist` forces arm64 on Apple Silicon (prevents Rosetta selecting x86_64, which would mismatch the arm64 venv)
- The `exec` chain (trampoline → bash → `exec python`) keeps the LaunchServices-tracked PID intact through to the NSApplication

**Do not replace the trampoline with a bash script.** See `CLAUDE.md` for the full rationale.

### macOS permissions

Three TCC grants, all attributed to `MyWispr.app`:

| Permission | How granted |
|---|---|
| Microphone | System prompt at first launch |
| Accessibility | Manual: System Settings → Privacy & Security → Accessibility |
| Automation → System Events | System prompt on first paste (cannot be pre-granted) |

Accessibility alone is sufficient for pynput global key capture (validated M3 + M7; no Input Monitoring grant needed).

### Model discovery order

`transcriber.py` tries these paths in order, stopping at the first `.bin` that exists:

1. User-configured model path (settings override)
2. `~/Library/Application Support/MyWispr/models/ggml-model-whisper-turbo.bin`
3. `~/Library/Application Support/MacWhisper/models/ggml-model-whisper-turbo.bin`
4. `~/Library/Application Support/MyWispr/models/ggml-model-whisper-base.bin`
5. `~/Library/Application Support/MacWhisper/models/ggml-model-whisper-base.bin`
6. Model-needed state (in-app download offered)

MacWhisper paths are checked as an optimization — the app must not require MacWhisper to be installed.

### Dev workflow

The app runs source from the install root, not the dev tree:

```
~/Library/Application Support/MyWispr/app/
```

To see changes, copy the edited file to the install root and restart the app:

```bash
cp src/main.py "$HOME/Library/Application Support/MyWispr/app/src/main.py"
# then quit and relaunch MyWispr from Applications
```

No cache clearing or bundle rebuild needed for source-only changes. Rebuild the bundle only when changing `scripts/` or `Info.plist`.

### Running tests

```bash
source venv/bin/activate
pytest tests/
```

Tests cover: settings round-trip, db insert/query/search/date-boundary math, disfluency removal (20+ input→expected pairs), cleanup with faked mtimes, vocabulary prompt composition. macOS-specific behavior (TCC, osascript, pynput) is not unit-tested.

### Key non-obvious decisions

- **pynput on macOS 15**: `TISCopyCurrentKeyboardInputSource` requires the main queue but pynput calls it from its listener thread → SIGTRAP. Fixed by `_patch_pynput_keycode_context()` in `main.py`, called before `MyWisprApp().run()`. Do not remove.
- **Dialog activation**: `activateIgnoringOtherApps_` is unreliable for `LSUIElement` apps on macOS 14/15. All alerts use `_alert()` / `_window()` wrappers that also set `NSFloatingWindowLevel` on the panel.
- **UI timer during modal sessions**: the `rumps.Timer` NSTimer is added to `NSRunLoopCommonModes` after start so it keeps firing while an alert or window is open. The private attribute is `_nstimer`.
- **Paste order**: save to SQLite → clipboard → paste. A paste failure never loses the transcript.
- **Portability boundary**: all `rumps` usage stays in `main.py`; all `osascript`/subprocess calls stay in `paste.py`. A future port only touches those two files.

### Key files for reference

- `REQUIREMENTS.md` — what to build and why; source of truth on any conflict
- `IMPLEMENTATION_PLAN.md` — resolved design decisions and milestone history; explains the reasoning behind non-obvious choices
- `CLAUDE.md` — project instructions for AI-assisted development; mirrors the key decisions above

> **Note on planning documents:** `IMPLEMENTATION_PLAN.md`, `REQUIREMENTS.md`, and `CLAUDE.md` are published intentionally as a transparent build record. They document how this project was designed and built — including the AI-assisted development process — in the hope that others building similar tools find the decisions and tradeoffs useful. They are not polished end-user documentation.

### Out of scope for v1

VAD, system notifications, speaker diarization, multi-format export, onboarding wizard, cloud transcription, py2app packaging. See `REQUIREMENTS.md` for the full list.
