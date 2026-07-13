# MyWispr — Implementation Plan (v1)

This plan is the build guide for v1. `REQUIREMENTS.md` defines *what* to build and is the source of truth on any conflict; this file pins down the design decisions the requirements leave open, and sequences the work into verifiable milestones. `audit-findings.md` contains background rationale; nothing there overrides this file.

Builder ground rules:

- Do not add features listed as out of scope in `REQUIREMENTS.md`, even as "easy wins".
- Keep each milestone independently runnable from source (`python src/main.py` or the smoke-test scripts). Never let the project sit in a state where nothing can be demonstrated.
- The existing `test_record_transcribe.py` is the reference for the working record→transcribe pattern (sounddevice float32 → int16 WAV → pywhispercpp). Preserve that pattern; note its model path is the developer machine's MacWhisper turbo model and must not be hardcoded anywhere in `src/`.
- macOS-specific behavior (TCC, System Events, pynput capture) cannot be unit-tested; everything else (postprocess, db, settings, cleanup, model discovery) must have plain `pytest` unit tests.

---

## Resolved design decisions

These were open questions in the requirements. They are now decided; implement as written rather than re-deciding.

### D1. Threading and concurrency model

Three thread contexts exist and must never block each other:

- **Main thread**: owned by `rumps` (AppKit event loop). All menu/icon manipulation happens here.
- **pynput listener thread**: created by `pynput.keyboard.Listener`. Callbacks must be near-instant: they only record timestamps and flip state, never do I/O.
- **One worker thread**: processes the pipeline (stop recording → write WAV → transcribe → postprocess → save to SQLite → clipboard → paste). Jobs arrive via a `queue.Queue`; the worker is a single long-lived daemon thread so transcriptions serialize naturally and the whisper model stays loaded.

Coordination pattern:

- A single `AppState` object (enum field: `IDLE`, `RECORDING`, `PROCESSING`, `PERMISSION_NEEDED`, `MODEL_NEEDED`, plus a message string) guarded by a `threading.Lock`. The pynput thread and worker thread write to it; nothing outside `main.py` touches rumps.
- **Portability rule**: all `rumps` usage (including dialogs and alerts for settings/search flows) stays in `main.py`, and all `osascript` usage stays in `paste.py`. No macOS-specific imports or subprocess calls anywhere else — this keeps a future Windows port confined to those two files.
- A `rumps.Timer` at 0.25s interval on the main thread reads `AppState` and syncs the menu bar title/icon. Do **not** update rumps UI directly from the pynput or worker threads — this is the crash-prone path.
- The recording icon "animation" is just the timer alternating between two glyphs while state is `RECORDING`; no extra machinery.
- The whisper `Model` is loaded lazily on the worker thread at the first transcription (and re-loaded if the model path setting changes). While loading, state shows `PROCESSING`. Loading at first use rather than launch keeps startup instant and avoids loading a model the user may immediately swap in settings.
- `sounddevice.InputStream` runs with a callback appending chunks to a list (same as the smoke test). Start/stop is controlled from the pynput callbacks via the recorder module; the stream callback thread is managed by PortAudio and needs no handling from us beyond the callback being allocation-light.

### D2. Settings UX within rumps

All settings interactions use `rumps` menus and `rumps.Window` text dialogs. No custom windows, no WebKit.

- **Hotkey**: a Settings → Hotkey submenu listing preset choices, each a checkable menu item: Right Option (default), Left Option, Right Command, Right Ctrl, Fn-unfriendly keys excluded; plus F13–F19 as a nested group; plus "Custom…" which opens a `rumps.Window` accepting a pynput key name (e.g. `f13`, `cmd_r`) with validation and an error alert on unknown names. No "press a key to capture" mode in v1 — presets cover the realistic cases and capture-mode is fiddly to get right.
- **Interaction mode**: Settings → Mode submenu, two checkable items (Hold-down / Double-tap).
- **Language**: Settings → Language submenu: Auto-detect (default) plus a curated list (English, Spanish, French, German, Italian, Portuguese, Japanese, Korean, Chinese, Tagalog) and "Other…" accepting a Whisper language code via `rumps.Window`.
- **Disfluency list**: "Edit disfluency list…" opens a `rumps.Window` pre-filled with the current list as comma-separated text; parse on save, trim whitespace, reject empty entries silently.
- **Model path**: Settings → Model submenu shows the currently active model (resolved via discovery) as a disabled info item, plus "Choose model file…" (a `rumps.Window` accepting an absolute path, validated to exist and end in `.bin`) and "Use automatic discovery" to clear the override.
- **Audio retention / recent-count**: numeric text fields via `rumps.Window` with integer validation.
- **Search transcripts**: menu item opens a `rumps.Window` for the keyword; results (up to 20, newest first) are shown in a `rumps.alert` as `[YYYY-MM-DD HH:MM] first 80 chars…`, with the alert's default button "Copy newest match" copying the most recent match's full text. Full-featured browsing is post-v1; the SQLite file is always there for power users. *(Results presentation superseded by M8: results become a clickable submenu with per-result copy.)*

Every settings change is written to `settings.json` immediately and takes effect without restart, except the hotkey/mode, which take effect by tearing down and recreating the pynput listener (do this on change; it is cheap).

### D3. Model acquisition flow

- Download source: the official whisper.cpp ggml conversions on Hugging Face — `https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.bin` (~142 MB) for base, `https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3-turbo.bin` (~1.6 GB) for turbo. Verify the URLs resolve at implementation time; if HF has restructured, the repo is `ggerganov/whisper.cpp`.
- Files are saved under `~/Library/Application Support/MyWispr/models/` with the filenames the discovery order expects (`ggml-model-whisper-base.bin`, `ggml-model-whisper-turbo.bin`). Note the requirements' filenames differ from Hugging Face's — rename on save, do not change the discovery paths.
- In the model-needed state, the menu offers: "Download base model (~142 MB)", "Download turbo model (~1.6 GB, better quality)", and "Choose existing model file…".
- Download runs on a background thread with `urllib.request` streaming to `<name>.bin.part`, atomically renamed on completion. Progress is surfaced through `AppState.message` and rendered by the UI timer as menu bar title text (e.g. `MyWispr ⬇ 43%`). On failure, delete the `.part` file, show a `rumps.alert` with the error, return to model-needed state.
- After a successful download or file selection, re-run discovery and transition to idle. No checksum verification in v1 (HF doesn't publish stable digests for these files); size sanity check (> 50 MB) guards against HTML error pages saved as `.bin`.

### D4. Disfluency removal rules

Two tiers, applied to `raw_text` to produce `cleaned_text` (both always stored; pasting uses `cleaned_text`):

- **Tier 1 — always strip**: `um`, `uh` (and doubled forms like `um,` `Um…`), wherever they appear, case-insensitive, absorbing an adjacent comma. These are never legitimate words.
- **Tier 2 — strip only when delimiter-bounded**: every other default-list word (`like`, `you know`, `so`, `actually`, `basically`, `literally`, `I mean`, `right`) is removed only when it is bounded on **both** sides by a delimiter — sentence start/end, comma, period, question mark, ellipsis, or another Tier 2 filler being removed. Whisper reliably inserts commas around spoken fillers, which is what makes this workable. Examples: `So, I think` → `I think`; `it was, like, huge` → `it was huge`; but `I like pizza` and `turn right here` are untouched.
- User-added words go to Tier 2. The user cannot demote `um`/`uh` to Tier 2, but removing them from the list disables stripping them entirely.
- After removal: collapse doubled spaces and doubled commas, fix space-before-punctuation, and re-capitalize a sentence whose original first word was removed.
- This module is pure-Python, regex-based, and must ship with a `pytest` table of at least 20 input→expected pairs including the preservation cases above. When in doubt between stripping and preserving, preserve — the raw text is always in the DB.

### D5. Permissions note discovered during planning

`pynput` global key capture on modern macOS requires its own TCC grant — **Input Monitoring** (and in some configurations Accessibility). This is a third grant beyond the Microphone + Accessibility pair in the requirements, attributed to the same Automator `MyWispr.app` identity. Treat it as an open risk to be validated in Milestone 3: if hotkey capture works under the Accessibility grant alone, fine; if not, add Input Monitoring to the permission preflight, the permission-needed menu state, and the install instructions. Do not silently swallow pynput failures — a listener that starts but never receives events is the symptom of a missing grant.

**D5 resolved (M3, 2026-07-09):** Tested under Terminal with Accessibility already granted. Both hold-down and double-tap modes fired correctly with no additional TCC prompt — Accessibility grant alone is sufficient for pynput on this machine (macOS 24.6, Apple Silicon). No Input Monitoring grant needed.

**D5 re-validated under MyWispr.app identity (M6, 2026-07-09):** Hotkey captured correctly under the Automator wrapper with Accessibility granted to MyWispr.app — no Input Monitoring grant needed. TCC attribution confirmed correct: prompts show "MyWispr.app" (not Python or bash). Three grants required in total: Microphone (prompted at first launch), Accessibility (added manually in System Settings), and Automation → System Events (prompted automatically on first paste via osascript). All three attributed to MyWispr.app.

### D6. Wrapper: hand-rolled .app bundle replaces Automator (decided before M7, 2026-07-09)

The Automator Application wrapper validated in M6 displays a permanent gear/progress menu bar item ("0% completed — Run Shell Script") while the app runs, and its ⓧ button terminates the app — unacceptable sharp edge for non-technical users. M7 replaces it with a hand-rolled minimal bundle:

- `MyWispr.app/Contents/MacOS/MyWispr` is a short bash script that execs `run.sh` (bash indirection preserved — never invoke Python directly).
- `Contents/Info.plist`: `LSUIElement` true, stable `CFBundleIdentifier` (e.g. `com.mywispr.app`), `CFBundleName` MyWispr, `CFBundleExecutable` MyWispr.
- `Contents/MacOS/MyWispr` is a pre-compiled Mach-O trampoline (`scripts/trampoline`, universal arm64+x86_64) that `execv`s `/bin/bash run.sh`. LaunchServices requires a Mach-O main executable; a bare bash script is silently ignored on macOS 15. `LSRequiresNativeExecution` in Info.plist forces native arch selection (prevents Rosetta choosing x86_64 on Apple Silicon, which would mismatch the arm64 venv packages). The trampoline `exec`s bash so TCC attribution flows to `MyWispr.app`; run.sh in turn `exec`s python so the LaunchServices-tracked PID chains through to the NSApplication (satisfying RunningBoard's check-in requirement). Source: `scripts/trampoline.c`.
- Generated reproducibly by `scripts/build-app.sh`; ad-hoc codesigned (`codesign -s -`) as the final build step.
- The bundle is a new TCC identity: the three M6 grants must be re-granted and the D5 hotkey check re-run once under it; record the result below.
- Install root for the runnable copy is `~/Library/Application Support/MyWispr/app/` (outside `~/Documents`, per the M5-verification launchd TCC constraint).
- pynput macOS 15 fix: `TISCopyCurrentKeyboardInputSource` now requires the main queue; pynput calls it from its listener thread → SIGTRAP. Fixed by `_patch_pynput_keycode_context()` in `main.py`: pre-fetches keyboard layout on the main thread and replaces `pynput.keyboard._darwin.keycode_context` with a cached version before the listener starts.

**D6 validated (M7, 2026-07-10):** TCC re-validated under `com.mywispr.app` with the Mach-O trampoline bundle. All three grants correctly attributed to MyWispr.app: Microphone prompt named "MyWispr.app" ✓, Accessibility manually re-added ✓, Automation → System Events prompted on first paste ✓. D5 re-confirmed: both hold-down and double-tap captured correctly, no Input Monitoring grant needed. `coalitionName: com.mywispr.app` confirmed in crash report; `translated: false` confirms arm64 native execution.

---

## Milestones

Build in this order. Each milestone has an acceptance check; do not start the next milestone until the check passes. Milestones 1–5 need no Automator wrapper — run from a Terminal with its own Mic/Accessibility grants for development.

### M1 — Project skeleton + core modules extracted

Create the `src/` layout from `REQUIREMENTS.md` §Project Structure, a `requirements.txt`, and a venv. Extract `recorder.py`, `transcriber.py`, `settings.py`, `postprocess.py`, `db.py` from the smoke-test pattern with the responsibilities the structure implies. `settings.py` loads/saves the JSON with defaults for every key in the settings table. `db.py` creates the schema on first use. Include `pytest` tests for settings round-trip, db insert/query/search, and the full D4 disfluency table.

**Accept when**: `pytest` green; a temporary CLI script records → transcribes → prints raw and cleaned text → row visible in SQLite (`sqlite3 … 'select * from transcripts'`).

### M2 — Model discovery + model-needed handling (logic only)

Implement the six-step discovery order from `REQUIREMENTS.md` §3 in `transcriber.py` (or a `models.py` if cleaner), returning either a resolved path or a model-needed result. Implement the D3 download function as a callable with a progress callback (UI comes in M4). Unit-test discovery with temp directories standing in for the real paths.

**Accept when**: discovery unit tests cover all six branches; on the dev machine, discovery resolves to the MacWhisper turbo model with no user config; download function fetches the base model to the MyWispr path (one manual run, then keep the file — it's the shared-install default).

### M3 — Hotkey capture

Implement `hotkey.py` with pynput: hold-down mode first (key-down starts, key-up stops, ignore auto-repeat), then double-tap mode (two presses within 400 ms toggles; make the window a module constant). Configurable key from settings, with the preset-name→pynput-key mapping from D2. Wire into a headless test harness (no rumps yet) that prints state transitions.

**Accept when**: from Terminal, holding Right Option records and releasing triggers transcribe→print; double-tap mode toggles correctly; a deliberate rapid tap in hold mode doesn't produce a zero-length recording (minimum duration ~0.3 s, discard below it). Also resolve the D5 question here and record the answer in this file.

### M4 — Menu bar shell + full pipeline

`main.py`: rumps app with the D1 state machine, UI-sync timer, all five states, recent-transcripts submenu (rebuilt from the DB after each transcription), search flow (D2), settings flows (D2), model-needed menu with the D3 download actions, and launch preflight (permissions probe + model discovery before enabling the hotkey). The worker thread executes the strict order: save to SQLite → clipboard (`pyperclip`) → paste via `osascript` System Events keystroke, with paste failure logged and non-fatal.

**Accept when**: launched from Terminal, the complete loop works end-to-end into TextEdit; killing Accessibility for Terminal makes the app show permission-needed instead of failing silently; renaming the models folder makes it show model-needed with working download.

### M5 — Cleanup

`cleanup.py`: delete WAVs older than the retention setting, NULL the `audio_file` column for affected rows, honor the disable flag. Run at app launch on the worker thread. Add the `launchd/com.mywispr.cleanup.plist` invoking cleanup via the same `run.sh` entry with a `--cleanup-only` flag (so the launchd job shares the app's TCC identity per the wrapper pattern). Unit-test with temp files at faked mtimes.

**Accept when**: unit tests green; manually planted old WAV is removed at launch and its DB row shows `audio_file IS NULL`.

### M6 — Automator wrapper, run.sh, TCC validation

Write `scripts/run.sh` (activates the venv, execs `python src/main.py "$@"`) and `automator/build-app.md` documenting the wrapper build per the lessons-learned pattern: Automator Application → Run Shell Script (`/bin/bash`) → script box contains exactly `bash /path/to/MyWispr/scripts/run.sh`. The Automator app must call the `.sh`, never Python directly — otherwise TCC attributes prompts to Python instead of MyWispr. Reset/avoid stale Terminal-era grants when testing so the validation is genuinely against the `MyWispr.app` identity.

**Accept when**: fresh `MyWispr.app` launch prompts as "MyWispr would like to…" for Microphone; after granting Mic + Accessibility (+ Input Monitoring if M3 found it necessary) to `MyWispr.app`, the full loop works launched from the app with Terminal closed; launchd cleanup plist loads and runs via `open -W`.

### M7 — Shared-install path

Document (in a new `INSTALL.md`) the friend/family install: copy the files to the install root (`~/Library/Application Support/MyWispr/app/`), create the venv (scripted — add `scripts/setup.sh` that creates the venv and pip-installs `requirements.txt`), generate the bundle with `scripts/build-app.sh` (per D6 — the Automator wrapper is superseded), grant the three TCC permissions, first launch downloads the base model via the in-app flow. Update the launchd plist to the production path. Test the whole thing as a dry run in a fresh directory with no MacWhisper paths available (temporarily rename the MacWhisper models dir, and restore it afterward).

**Accept when**: starting from a clean copy with no MyWispr app-support dir and MacWhisper models hidden, a user following only the written steps reaches a working paste-into-TextEdit within one sitting, with the base model acquired through the in-app download. Also: the cleanup plist, installed at the production path (`~/Library/Application Support/MyWispr/app/scripts/run.sh`), loads and a `launchctl start com.mywispr.cleanup` run completes successfully with `[cleanup] deleted N file(s).` in the log and no TCC errors. (The M6 cleanup test failed because the dev plist pointed into `~/Documents`; this gate confirms the path fix works.)

**M7 accepted (2026-07-10):** All gate items passed. Three additional fixes were required beyond the original D6 plan — see D6 section above for details (LSRequiresNativeExecution, exec python chain, pynput macOS 15 patch). 56/56 tests green. App ships as `/Applications/MyWispr.app` with Mach-O trampoline, ad-hoc signed, com.mywispr.app identity.

### M8 — Dialog UX fixes (post-v1, added 2026-07-10)

Two defects found in daily use after M7 acceptance. Both are pure `src/` changes — no bundle rebuild, no re-signing, no TCC re-grants; quit and relaunch the app after syncing to the install root.

**8a. Dialogs appear behind other windows; Dock bounces with a Python rocket icon.** MyWispr is an LSUIElement app and is almost never the active application, so `rumps.alert`/`rumps.Window` panels open behind the frontmost app and macOS bounces the Dock icon for attention. The icon is the Python rocket because the running process's `NSBundle.mainBundle` is the venv's Python.app, not our bundle. Fix:

- Add wrapper functions for alerts and windows that call `NSApplication.sharedApplication().activateIgnoringOtherApps_(True)` immediately before showing; route every `rumps.alert` and `rumps.Window(...).run()` call site through them so no site can forget activation.
- At startup, set `NSApplication.sharedApplication().setApplicationIconImage_(...)` from the MW icon asset so any Dock appearance and alert icons show MW instead of the rocket.
- All AppKit usage stays in `main.py` per the D1 portability rule.

**8b. Search results are read-only except "Copy newest match".** Replace the results `rumps.alert` with a "Search Results" submenu reusing the recent-transcripts pattern: one item per result titled `[YYYY-MM-DD HH:MM] first-60-chars…`, clicking an item copies that transcript's full text (`cleaned_text` falling back to `raw_text`, same as `_copy_recent`). Clear/replace the submenu on each new search. Keep the "No results" alert (through the 8a wrapper). Optional stretch: a "Copy multiple…" item at the bottom opening a `rumps.Window` that accepts comma-separated result numbers and copies them joined by newlines — per-result click-to-copy is the requirement; multi-select is not.

**8c. Recording indicator frozen while a dialog is open.** Recording via hotkey works while a `rumps.alert`/`rumps.Window` is up (pynput and the worker are on their own threads), but the menu bar icon doesn't blink or change state until the dialog closes. Cause: the D1 UI-sync `rumps.Timer` is an NSTimer scheduled in the default run loop mode only, and AppKit modal sessions spin the run loop in `NSModalPanelRunLoopMode`, so the timer stops firing for the duration of the dialog. Fix: after starting the UI-sync timer, re-add its underlying NSTimer to the run loop for `NSRunLoopCommonModes` (via `NSRunLoop.currentRunLoop().addTimer_forMode_`), which includes the modal-panel mode. The rumps `Timer` wraps the NSTimer in a private attribute — read the installed rumps source for the attribute name rather than guessing. Stays in `main.py` per D1.

**Accept when**: with TextEdit frontmost, Search Transcripts opens its dialog on top immediately, with no Dock bounce and no rocket icon anywhere in the flow; a search yields a submenu where clicking any individual result copies that result's full text (verified by pasting into TextEdit); with a dialog left open, holding the hotkey shows the blinking recording indicator in the menu bar and the state returns to idle after transcription; the recent-transcripts submenu and all settings dialogs still work; 56/56 tests still green (plus new tests only if db/search logic changed).

**M8 accepted (2026-07-10):** All gate items passed — code verification by the verifier (56/56 tests, wrappers routed at all call sites, rumps private attrs `_nstimer`/`Window._alert` confirmed against installed source, bundle untouched so TCC grants intact, D1 compliance) and interactive checks confirmed by the user. Implementation notes: `_alert` uses `NSFloatingWindowLevel` in addition to activation (activation alone unreliable for LSUIElement apps on macOS 14+); worker-thread alerts now queue through `_alert_queue` drained by the UI timer (removed a latent D1 violation). Two minor non-blocking findings deferred to follow-up: (1) search results with identical titles silently collapse to one menu item (rumps menus are title-keyed) — fix by prefixing an index; (2) queued alerts can nest during modal sessions — cosmetic, rare, accepted for v1.

### M9 — Search improvements + custom vocabulary (scoped 2026-07-10)

Scope decided by the user 2026-07-10: 9b + 9c + 9d below. 9a (search-result discoverability: the "N result(s) found" alert telling the user to open the menu) is **closed as accepted-as-is** — one-time learning cost; every alternative within the no-WebKit constraint is worse. First real install on a second machine is M10.

**9b. Date-range filtering on search.** Two new settings, both in a Settings → Search submenu (entered via `rumps.Window` like other numeric/text settings — the point is date entry happens rarely in Settings, never per-search):

- `search_range_days` (int, default 30) — lookback window.
- `search_start_date` (ISO `YYYY-MM-DD` or empty, default empty = today) — the end anchor of the window; the search covers `[start_date − range_days, start_date]`. Empty/cleared always means "today", so the normal mode is simply "last N days ending now". Validate the format; reject with an error alert on bad input.

Stale-state guard (required, not optional): a persistent start date silently excludes recent results once forgotten, so (a) the search dialog's prompt text must always display the active window, e.g. `Search transcripts (2026-06-01 → 2026-07-01):`, and (b) the Settings → Search menu items show current values inline (e.g. "Start date: (today)"). `db.search()` gains optional `start_date`/`range_days` parameters adding a `WHERE timestamp BETWEEN ? AND ?` clause — unit-test the boundary math (inclusive ends, empty-start = today) since this is pure logic.

**9c. Search results cap.** Add a `search_results_limit` setting (int, default 40), independent of `recent_transcripts_count`; `_search()` uses it as the `db.search()` limit.

**9d. Custom vocabulary.** From REQUIREMENTS.md post-v1: an editable list of names/terms Whisper frequently mishears (e.g. "MyWispr"), fed to transcription as whisper.cpp's `initial_prompt` so the model is biased toward those spellings. UX mirrors the disfluency-list flow: "Edit vocabulary…" opens a `rumps.Window` pre-filled with the current comma-separated list; stored in settings as a list; empty list = no prompt passed. Compose the prompt as a natural phrase (e.g. `Glossary: MyWispr, Dropbox, …`) rather than bare comma-joined tokens — check pywhispercpp's parameter name (`initial_prompt`) against the installed version. Note the prompt biases only the first ~224 tokens of a segment's context; that's fine for short dictations. Unit-test the settings round-trip and prompt composition; the transcription effect itself is validated interactively.

**Accept when**: searching with a stale start date set shows the date window in the search prompt; a search for a term known to exist outside the window excludes it, and clearing the start date restores it; results respect `search_results_limit`; a word from the vocabulary list that Whisper previously misheard transcribes correctly in a live dictation (user-demonstrated); settings all persist across relaunch; full pytest suite green including new tests for `db.search()` date bounds and vocabulary settings/prompt composition.

**M9 accepted (2026-07-10):** Verifier confirmed 76/76 tests, install-root sync, D1 containment, boundary math (inclusive ends, empty start = today; timestamps stored `isoformat(timespec="seconds")` so the T-separated BETWEEN comparison is exact), `search_count` called only when the limit is hit, and `initial_prompt` present in the installed pywhispercpp params schema. Interactive gate items user-confirmed. Builder additions beyond spec, accepted: `db.search_window()` helper and the "X of Y result(s) shown" total via `db.search_count()`. Known 9d limitation recorded in memory: `initial_prompt` is a soft bias and cannot override phonetically identical common words; post-processing substitution pairs noted as a future option. Minor non-blocking robustness note: a hand-corrupted `search_start_date` in settings.json (bypassing dialog validation) would raise in `_search`; fold a fallback-to-today try/except into any future search work.

### M10 — First real install on a second machine (placeholder, opens after M9)

The unvalidated distribution assumptions: pywhispercpp wheels on Intel, Gatekeeper friction with the ad-hoc signature on a machine that didn't build it (expect right-click → Open once), INSTALL.md followed by a non-technical user end-to-end. Findings here reprioritize everything after; scope when opened.

---

## Risks to watch

- **pynput TCC (D5)** — validate early in M3, not at packaging time.
- **Right Option as a bare modifier**: pynput reports it as `Key.alt_r` on key-down/up, but some keyboard layouts use Right Option for character composition. Acceptable for v1 (user can rebind); don't try to suppress the key event.
- **Secure input fields** (password boxes, some terminals) block synthetic Cmd+V. Expected; clipboard fallback is the designed recovery. Log it, don't fight it.
- **Intel Macs**: `pywhispercpp` wheels and turbo-model speed differ. Base model on Intel is the realistic shared-install path; don't benchmark-tune on the M-series dev machine and assume it transfers.
- **rumps thread-safety**: any crash in menu updates almost certainly means UI touched off the main thread — route through `AppState` + timer (D1), never "fix" it with ad-hoc `performSelector` calls.
