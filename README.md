# Gemini Snap

> Two-click screen region capture ➔ Instantly open in Gemini ➔ Auto-paste & submit in Google Chrome.

Gemini Snap is a fast macOS productivity tool designed to streamline sending visual context to Google Gemini. Instead of manually taking a screenshot, opening a browser, navigating to Gemini, and pasting the file, Gemini Snap does all of this in a single action.

---

## How It Works

```mermaid
sequenceDiagram
	autonumber
	actor User
	participant Script as run.sh / gemini_snap.py
	participant Overlay as region_select (Obj-C)
	participant OS as macOS (screencapture)
	participant Chrome as Google Chrome

	User->>Script: Trigger Gemini Snap (or press ⌥⌘G)
	Script->>Script: Build region_select binary (if needed)
	Script->>Overlay: Launch multi-display overlay
	Note over Overlay: Semitransparent dark screen overlay
	User->>Overlay: Click first corner & opposite corner
	Overlay-->>Script: Return coordinates (X, Y, W, H)
	Script->>OS: Capture region to temp PNG file
	Script->>OS: Load PNG data into clipboard as 'PNGf'
	Script->>Chrome: Launch & open Gemini URL
	Script->>Script: Delay for page load
	Script->>OS: Simulate keystroke: ⌘V (Paste)
	Script->>Script: Delay for image upload
	Script->>OS: Simulate keystroke: Return (Submit)
```

---

## Quick Start

### 1. Make executable
Configure executable permissions on the launcher:
```bash
chmod +x run.sh
```

### 2. Run standard capture
```bash
./run.sh
```
1. Click once for the first corner of your target region.
2. Move your cursor to the opposite corner (a blue outline guides you).
3. Click again to confirm (or press Esc to cancel).
4. Google Chrome will automatically open Gemini, paste the screenshot, and submit it.
(Note: On the first run, the script will automatically compile the native selector binary).

### 3. Dry-run (Copy to clipboard only)
If you only want the screenshot copied to your clipboard without opening Chrome or pasting:
```bash
./run.sh --dry-run
```

---

## Configuration and Flags

Customize the behavior of Gemini Snap using the following CLI flags:

| Flag | Default | Description |
|---|---|---|
| `--mode <two-click\|drag>` | `two-click` | Choose selection type: Native Objective-C two-click overlay or classic `screencapture -i` dragging. |
| `--dry-run` | *None* | Perform capture and copy to clipboard, but do not open Chrome/Gemini. |
| `--no-submit` | *None* | Open Gemini and paste the screenshot, but do not simulate the final `Return` key press. |
| `--load-wait <seconds>` | `4.5` | Duration (in seconds) to wait for the Gemini web app to load before pasting. |
| `--paste-wait <seconds>` | `1.5` | Duration (in seconds) to wait for the image upload to attach before submitting. |
| `--save <path>` | *None* | Keep the captured PNG saved at a specific file path (by default, it uses a temporary directory). |
| `--rect <x,y,w,h>` | *None* | Capture a predefined screen coordinate rectangle instantly without prompt. |

---

## Global Keyboard Shortcut (Optional)

You can launch Gemini Snap globally from anywhere in macOS using a keyboard shortcut (e.g., `⌥⌘G`).

1. **Register the Service:**
   ```bash
   ./setup_shortcut.sh
   ```
2. **Usage:** Press **Option + Command + G** (`⌥⌘G`) at any time to start capturing.
3. **Uninstall Service:** If you ever need to remove the shortcut and clean up cached settings:
   ```bash
   ./uninstall.sh
   ```
