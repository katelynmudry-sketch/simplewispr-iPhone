# MyWispr iOS (keyboard extension)

A companion iPhone app for MyWispr. It ships as a **custom keyboard** — the same
mechanism apps like Wispr Flow use on iOS — because iOS has no equivalent of the
Mac app's global hotkey + "paste at cursor in any app" behavior. A custom keyboard
sidesteps that: once enabled, you switch to it inside any app's text field, tap
the mic, speak, and the cleaned-up text is typed directly into that field.

## What this is (and isn't)

- **Transcription**: Apple's on-device `SFSpeechRecognizer` (`requiresOnDeviceRecognition
  = true`) — not `pywhispercpp`/whisper.cpp. A keyboard extension runs under a tight
  memory cap (historically ~30–80MB) that can't fit a bundled Whisper model; Apple's
  Speech framework runs as a system service instead, so it stays within budget. See the
  "Why not whisper.cpp" note below if you want the tradeoffs.
- **Cleanup**: deterministic disfluency stripping, ported line-for-line from
  `src/postprocess.py` into `Shared/DisfluencyCleaner.swift`. No LLM formatting pass —
  Apple's on-device Foundation Models framework requires an A17 Pro chip or later
  (iPhone 15 Pro+), so it isn't available on an iPhone 13. This can be added later on
  supported hardware; see `CLAUDE.md` for how that decision was scoped.
- **Trigger**: tap-to-toggle (tap to start, tap again to stop), not hold-to-talk. This
  is simpler to get right inside a keyboard extension's async permission/recognition
  flow. Hold-to-talk could be added later via touch-down/touch-up tracking on the mic
  button.
- **No transcript history yet.** The host app (`MyWispr/`) is just onboarding
  instructions plus an editable disfluency word list, shared with the extension via an
  App Group. A SQLite-backed history screen (mirroring the Mac app's) is a reasonable
  follow-up, not included in this v1.
- **No cloud dependency**, matching the Mac app's core principle — both speech
  recognition and cleanup run entirely on-device.

## Before you build: personalize the identifiers

Bundle IDs and App Group IDs are unique across *all* of Apple's developer accounts,
not just within one account — if two people both try to register `com.mywispr.ios`
under their own separate Apple IDs, the second one fails. If you're building your own
copy (rather than the original author's), first replace every `com.mywispr` in
`ios/project.yml` (the `bundleIdPrefix`, both `PRODUCT_BUNDLE_IDENTIFIER` values, and
the `group.com.mywispr.ios` App Group string in both targets) with something unique to
you, e.g. `com.yourname.mywispr`.

**Free Apple ID caveat**: App Groups (used here so the host app and keyboard extension
can share the disfluency word list) have historically required a paid Apple Developer
Program membership — Xcode's automatic signing tends to reject adding the App Groups
capability under a free "Personal Team." If you only have a free Apple ID and hit this,
sideloading via AltStore/SideStore (below) may still work since they provision
capabilities differently than Xcode's UI, but it isn't guaranteed — treat it as
something to verify on your first build, not a promise.

## Two ways to build this

- **You have a Mac**: use Xcode directly (steps below). This is also the only path to
  TestFlight, since uploading to App Store Connect requires a real Apple Developer
  account signed in on an actual Mac at some point.
- **You don't have a Mac**: use the GitHub Actions workflow
  (`.github/workflows/build-ios-ipa.yml`) plus AltStore or SideStore. This produces an
  **unsigned** `.ipa` in the cloud — no Apple credentials or secrets needed in CI at
  all, because AltStore/SideStore re-sign the app locally on your own computer using
  your own Apple ID at install time, not at build time. That also means every fork of
  this repo can run the workflow as-is.
  1. On GitHub, go to your fork's **Actions** tab → **Build unsigned iOS IPA** →
     **Run workflow**.
  2. When it finishes, download the `MyWispr-unsigned-ipa` artifact.
  3. Install [AltStore](https://altstore.io) or [SideStore](https://sidestore.io) on
     your iPhone (both have their own setup docs — SideStore doesn't need a companion
     computer running at all times, AltStore's classic flow needs AltServer running on
     a Windows/Mac machine occasionally to refresh signing).
  4. Use AltStore/SideStore to install the downloaded `.ipa` — it handles signing with
     your own Apple ID during that step.
  5. Same 7-day-expiry caveat as the free-account Xcode path applies unless you're
     signing with a paid Developer Program account through AltServer.
  - Known AltStore/SideStore constraint: free Apple IDs are historically limited to a
    handful of sideloaded apps active at once (Apple caps free-tier certificates), so
    this may compete with other sideloaded apps on the same phone.
  - This workflow hasn't been run end-to-end (written with no Mac available to test
    it) — treat the first run as the real test, same as the rest of this project.

## Project layout

```
ios/
  project.yml              XcodeGen spec — the source of truth for the Xcode project
  MyWispr/                 Host app target (SwiftUI): onboarding + word-list settings
  MyWisprKeyboard/         Keyboard extension target: mic UI, speech recognition, cleanup
  Shared/                  DisfluencyCleaner.swift — used by the extension and by tests
  MyWisprTests/            Unit tests porting tests/test_postprocess.py's cases
```

## Build with Xcode (the Mac path)

This project was written and committed from a Linux container with no Xcode, no iOS
Simulator, and no way to compile or run Swift code. Everything below is written against
well-documented, stable APIs (`UIInputViewController`, `SFSpeechRecognizer`,
`AVAudioEngine`, App Groups), but **it has not been built or run** — treat the first
build as the real test, and expect to fix small things (an Info.plist key, a signing
setting) that only surface in Xcode.

1. Install [Xcode](https://apps.apple.com/app/xcode/id497799835) and
   [XcodeGen](https://github.com/yonaskolb/XcodeGen) (`brew install xcodegen`).
2. Generate the Xcode project:
   ```
   cd ios
   xcodegen generate
   open MyWispr.xcodeproj
   ```
3. In Xcode, select the **MyWispr** target → Signing & Capabilities → set your Team
   (a free Apple ID works for local installs). Repeat for the **MyWisprKeyboard**
   target. If "Automatically manage signing" doesn't provision the App Group
   (`group.com.mywispr.ios`) on its own, add the App Groups capability manually on
   both targets and check the same group.
   - **Free Apple ID caveat**: apps installed this way expire after 7 days and need
     rebuilding from Xcode to keep working. A paid Apple Developer account ($99/yr)
     removes that limit if you want it to stick around.
4. Connect your iPhone, select it as the run destination, and Build & Run (⌘R) — this
   installs the MyWispr app. On the phone: Settings → General → VPN & Device
   Management → trust your developer certificate.
5. Open the MyWispr app on your phone and follow its three onboarding steps: add the
   MyWispr keyboard in Settings → Keyboard → Keyboards, then turn on **Allow Full
   Access** (required for microphone + speech recognition — this is what triggers
   iOS's "this keyboard has full access" warning; it's expected).
6. Test it: open Notes or Messages, tap-and-hold the globe key on the keyboard, pick
   MyWispr, tap the mic, say something, tap again to stop. Cleaned-up text should land
   at the cursor.

### Sharing it with a small group via TestFlight

If you have a paid Apple Developer Program account and want family/friends to install
this without sideloading tools, TestFlight is the path — it's still not the App Store
(no public listing, no full review, just a light Beta App Review for external testers
that's typically approved within a day). This requires Xcode on a Mac: Product →
Archive, then distribute the archive to App Store Connect, create a TestFlight group,
and add testers by email — they install the TestFlight app and accept an invite. Builds
expire after 90 days and need re-uploading periodically. This isn't automated by
anything in this repo yet; it's a manual Xcode/App Store Connect flow each time.

## Why not whisper.cpp / WhisperKit on iOS

whisper.cpp (via `pywhispercpp` on the Mac, or the Swift port
[WhisperKit](https://github.com/argmaxinc/WhisperKit) on iOS) loads model weights
in-process — fine for a standalone app, but a keyboard extension's memory cap makes it
impractical there. If a future standalone-app version (not a keyboard extension) wants
Whisper-level quality/control instead of Apple's fixed model, WhisperKit is the
reasonable path — that's a different app shape from what's here, not a drop-in swap.

## Keeping DisfluencyCleaner.swift in sync

`Shared/DisfluencyCleaner.swift` is a manual port of `src/postprocess.py`. If you
change the Python cleanup rules, port the change here too and update
`MyWisprTests/DisfluencyCleanerTests.swift`'s case table (it mirrors
`tests/test_postprocess.py`) to check it.
