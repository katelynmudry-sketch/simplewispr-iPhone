#!/usr/bin/env bash
# Generates /Applications/MyWispr.app — a minimal hand-rolled bundle that
# replaces the Automator wrapper. The bundle executable is a pre-compiled Mach-O
# trampoline (scripts/trampoline) that execv's bash run.sh, preserving the
# bash-indirection TCC attribution rule while satisfying LaunchServices' Mach-O
# requirement.
#
# Usage: bash scripts/build-app.sh
# Run from any directory — the install root is always:
#   ~/Library/Application Support/MyWispr/app/
set -euo pipefail

APP=/Applications/MyWispr.app
INSTALL_ROOT="$HOME/Library/Application Support/MyWispr/app"
RUN_SH="$INSTALL_ROOT/scripts/run.sh"

echo "Building $APP ..."

if [ ! -f "$RUN_SH" ]; then
    echo "ERROR: run.sh not found at:"
    echo "  $RUN_SH"
    echo "Copy the project files to the install root first, then re-run this script."
    exit 1
fi

# Warn if replacing the Automator bundle (different bundle ID — TCC re-grant needed)
if [ -d "$APP" ]; then
    EXISTING_ID=$(defaults read "$APP/Contents/Info" CFBundleIdentifier 2>/dev/null || echo "unknown")
    if [ "$EXISTING_ID" != "com.mywispr.app" ]; then
        echo "NOTE: Replacing existing bundle (ID: $EXISTING_ID)."
        echo "      TCC grants must be re-applied to the new MyWispr.app identity."
        echo "      Removing $APP ..."
    fi
    rm -rf "$APP"
fi

# Bundle skeleton
mkdir -p "$APP/Contents/MacOS"
mkdir -p "$APP/Contents/Resources"

# Info.plist
cat > "$APP/Contents/Info.plist" << 'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>MyWispr</string>
    <key>CFBundleIdentifier</key>
    <string>com.mywispr.app</string>
    <key>CFBundleName</key>
    <string>MyWispr</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleInfoDictionaryVersion</key>
    <string>6.0</string>
    <key>CFBundleVersion</key>
    <string>1</string>
    <key>LSUIElement</key>
    <true/>
    <key>NSMicrophoneUsageDescription</key>
    <string>MyWispr uses the microphone to record your speech for transcription.</string>
    <key>NSAccessibilityUsageDescription</key>
    <string>MyWispr uses Accessibility to paste transcribed text at the cursor.</string>
    <key>LSRequiresNativeExecution</key>
    <true/>
</dict>
</plist>
PLIST

# Bundle executable — a pre-compiled Mach-O trampoline that execv's bash run.sh.
# LaunchServices requires a Mach-O (not a shell script) to launch a bundle.
# The trampoline calls execv("/bin/bash", run_sh_path, argv...) so the bash
# parent stays alive, preserving TCC attribution to MyWispr.app.
# Source: scripts/trampoline.c  Binary: scripts/trampoline (universal arm64+x86_64)
TRAMPOLINE="$(cd "$(dirname "$0")" && pwd)/trampoline"
if [ ! -f "$TRAMPOLINE" ]; then
    echo "ERROR: trampoline binary not found at $TRAMPOLINE"
    echo "       Rebuild it: cc -arch arm64 -arch x86_64 -o scripts/trampoline scripts/trampoline.c"
    exit 1
fi
EXEC="$APP/Contents/MacOS/MyWispr"
cp "$TRAMPOLINE" "$EXEC"
chmod +x "$EXEC"

# Ad-hoc codesign — required for LaunchServices to launch the bundle.
# No Developer ID needed; -s - means adhoc.
codesign --force --deep -s - "$APP"

echo ""
echo "Done. Built $APP"
echo "  Bundle ID:  com.mywispr.app"
echo "  Executable: $EXEC"
echo "  run.sh:     $RUN_SH"
echo ""
echo "Next steps (see INSTALL.md for the full walkthrough):"
echo "  1. Launch /Applications/MyWispr.app — grant Microphone when prompted."
echo "  2. System Settings → Privacy & Security → Accessibility → add MyWispr (+)."
echo "  3. Hold the hotkey, speak, release — grant Automation → System Events on first paste."
