# Changelog

All notable changes to MyWispr will be documented here. Format loosely follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased] — v1.0 candidate

Feature-complete on the developer machine. Pending: first real install on a second machine (M10) before tagging v1.0.

### Added

- Push-to-talk transcription via hold-down or double-tap hotkey (configurable)
- Local audio recording to timestamped `.wav` files
- Transcription via `pywhispercpp` (whisper.cpp Python bindings) — fully local, no cloud dependency
- Six-step model discovery: prefers turbo over base, MyWispr-owned over MacWhisper-shared, falls through to model-needed state
- In-app model download (Whisper base ~142 MB, turbo ~1.6 GB) with background progress indicator
- Auto-paste via `osascript` / System Events; clipboard always written first so paste failure never loses text
- SQLite transcript history (`~/Library/Application Support/MyWispr/transcripts.db`)
- Transcript search with date-range filtering and configurable result limit
- Disfluency removal: Tier 1 (always strip `um`/`uh`) and Tier 2 (delimiter-bounded fillers); user-editable list
- Custom vocabulary fed to Whisper as `initial_prompt` to bias transcription toward user-specified terms
- Menu bar app with five states: idle, recording, processing, permission-needed, model-needed
- Recent transcripts submenu (configurable count, default 20); click any item to copy
- Settings via `rumps` dialogs: hotkey, interaction mode, language, model path, disfluency list, vocabulary, audio retention, result counts
- Automated audio cleanup at app launch and daily via launchd (default: delete WAVs older than 30 days; transcripts never deleted)
- Hand-rolled `.app` bundle with Mach-O trampoline (`scripts/trampoline.c`); `build-app.sh` compiles from source if binary absent
- Ad-hoc codesigned bundle (`com.mywispr.app`) with correct TCC attribution for Microphone, Accessibility, and Automation → System Events
- `scripts/setup.sh` for venv creation, dependency install, and launchd plist installation
- 76 pytest unit tests covering db, settings, postprocess, cleanup, transcriber, and vocabulary

### Fixed

- pynput `TISCopyCurrentKeyboardInputSource` crash on macOS 15 (main-queue patch in `main.py`)
- Dialogs appearing behind other windows for LSUIElement apps on macOS 14/15 (`NSFloatingWindowLevel` wrapper)
- UI-sync timer freezing during modal sessions (NSTimer added to `NSRunLoopCommonModes`)
- Replaced Automator Application wrapper (caused persistent gear icon and ⓧ quit button) with hand-rolled Mach-O bundle
- `LSRequiresNativeExecution` added to prevent Rosetta selecting x86_64 on Apple Silicon, which mismatched the arm64 venv
