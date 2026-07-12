# Installing MyWispr

MyWispr is a macOS menu-bar push-to-talk transcription app. This guide walks you from a fresh machine to a working first transcription.

**Time:** about 10 minutes plus the base model download (~142 MB, one time only).

---

## Prerequisites

- macOS 12 or later (Apple Silicon or Intel)
- Python 3.10 or later — download from [python.org](https://www.python.org/downloads/) if you don't have it

To check your Python version, open Terminal (Applications → Utilities → Terminal) and type:

```
python3 --version
```

If you see `Python 3.10.x` or higher, you're good. If you see a version below 3.10, or "command not found", install Python from python.org first.

---

## Step 1 — Copy files to the install location

Copy the MyWispr folder to:

```
~/Library/Application Support/MyWispr/app/
```

To do this in Terminal:

```bash
# Create the install directory
mkdir -p "$HOME/Library/Application Support/MyWispr/app"

# Copy the files (replace /path/to/MyWispr with where you unzipped or cloned MyWispr)
cp -R /path/to/MyWispr/. "$HOME/Library/Application Support/MyWispr/app/"
```

After copying, verify you have:

```
~/Library/Application Support/MyWispr/app/
  src/
  scripts/
  launchd/
  requirements.txt
  ...
```

---

## Step 2 — Run setup

In Terminal:

```bash
bash "$HOME/Library/Application Support/MyWispr/app/scripts/setup.sh"
```

This creates a Python virtual environment, installs all dependencies, and sets up the daily audio cleanup job. It takes about a minute the first time.

---

## Step 3 — Build the app bundle

```bash
bash "$HOME/Library/Application Support/MyWispr/app/scripts/build-app.sh"
```

This creates `/Applications/MyWispr.app` — the app you'll launch from Finder or Spotlight.

---

## Step 4 — Grant permissions (three steps)

macOS requires three permissions. You grant them once; they persist.

### 4a — Microphone (automatic prompt)

Double-click **MyWispr** in your Applications folder (or Spotlight → "MyWispr").

A dialog will appear:

> **"MyWispr" would like to access the microphone.**

Click **OK**.

### 4b — Accessibility (manual grant)

1. Open **System Settings** → **Privacy & Security** → **Accessibility**.
2. Click the **+** button.
3. Navigate to **Applications** → select **MyWispr** → click **Open**.
4. Make sure the toggle next to MyWispr is **on** (blue).

### 4c — Automation → System Events (automatic prompt on first paste)

This one appears automatically the first time you complete a transcription. When you see:

> **"MyWispr" wants access to control "System Events.app".**

Click **Allow**.

Note: your first transcription will land on the clipboard but may not auto-paste (the grant hasn't been given yet). After you click Allow, all subsequent pastes work automatically.

---

## Step 5 — Download the base model (first launch)

MyWispr needs a Whisper speech model to transcribe. On first launch (with no model installed), the menu bar will show **MW ⚠** and offer download options.

Click the **MW** icon in the menu bar → **Download base model (~142 MB)**.

The download runs in the background and takes a minute or two depending on your connection. The menu bar shows the download percentage. When it finishes, the icon changes to **MW** and the app is ready.

---

## Step 6 — Your first transcription

1. Open any text field — for example, a new TextEdit document (File → New, Format → Make Plain Text).
2. Click inside the document so the cursor is there.
3. Hold the **Right Option** key on your keyboard, speak a sentence, then release the key.
4. Your words appear at the cursor.

That's it. MyWispr runs in the menu bar; click the **MW** icon to see recent transcripts, change settings, or quit.

---

## Changing the hotkey

If Right Option conflicts with your keyboard layout (some layouts use it for special characters), you can change it:

Menu bar **MW** → **Settings** → **Hotkey** → choose a different key.

---

## Uninstalling

1. Quit MyWispr (menu bar **MW** → **Quit**).
2. Delete `/Applications/MyWispr.app`.
3. Delete `~/Library/Application Support/MyWispr/` (contains audio, transcripts, and models).
4. Unload the cleanup job:
   ```bash
   launchctl unload ~/Library/LaunchAgents/com.mywispr.cleanup.plist
   rm ~/Library/LaunchAgents/com.mywispr.cleanup.plist
   ```

---

## Troubleshooting

**MW ⚠ in menu bar after launch** — a permission is missing. Click the icon; it will say which one and offer a link to System Settings.

**Transcript on clipboard but nothing pasted** — the Automation → System Events permission hasn't been granted yet, or you were in a password field (secure input blocks auto-paste by design). The text is always on your clipboard; paste manually with Cmd+V.

**"venv not found" error on launch** — the setup step didn't complete. Re-run `scripts/setup.sh`.

**Hotkey doesn't seem to work** — make sure MyWispr's Accessibility permission is toggled on in System Settings → Privacy & Security → Accessibility.
