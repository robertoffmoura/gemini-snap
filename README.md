# Gemini Snap

Two-click screen region → screenshot → **new Chrome tab** on Gemini → paste image → Enter.

## Run

```bash
chmod +x run.sh build.sh gemini_snap.py
./run.sh
```

1. **Click** first corner  
2. **Click** opposite corner (Esc cancels)  
3. Chrome opens Gemini, image is pasted and submitted  

Dry run (clipboard only):

```bash
./run.sh --dry-run
```

## Fix the two bugs you hit

### 1. Drag instead of two clicks

Default is **two clicks** again:

- Prefer native overlay: `clang` builds `RegionSelect.m` → `region_select`  
- If that fails: Python two-click (no drag; click, move, click)  
- Only if you ask: `./run.sh --mode drag`

```bash
./build.sh    # optional; run.sh tries this automatically
./run.sh
```

Uses **clang + Objective-C**, not Swift (avoids your `SwiftBridging` CLT bug).

### 2. “Could not drive Chrome” / image not uploaded

Chrome control was rewritten:

| Step | How |
|---|---|
| Open Gemini | `open -a "Google Chrome" URL` (no Automation permission) |
| Paste / Enter | System Events keystrokes (needs **Accessibility**) |
| Image on clipboard | PNG file → pasteboard as `PNGf` (more reliable for Gemini) |

**You must enable Accessibility** or paste cannot be simulated:

1. **System Settings → Privacy & Security → Accessibility**  
2. Enable **Terminal** (or iTerm / Warp / VS Code)  
3. **Quit and reopen** that app  
4. Retry `./run.sh`

If paste still fails, the screenshot is still on the clipboard — click Gemini’s prompt and press **⌘V**.

Optional (only if macOS prompts):

- **Automation** → allow your terminal to control **System Events** / Chrome  

## Flags

```bash
./run.sh --dry-run
./run.sh --no-submit          # paste only
./run.sh --load-wait 7        # slow Gemini
./run.sh --paste-wait 2
./run.sh --mode drag          # old click-drag UI
./run.sh --save /tmp/x.png
```

## Shortcut

Point Raycast / Alfred / Shortcuts at:

```text
/full/path/to/gemini-snap/run.sh
```

## Permissions checklist

| Permission | Why |
|---|---|
| **Screen Recording** | capture region |
| **Accessibility** | synthetic ⌘V / Enter |
| **Automation** | only if macOS asks for System Events / Chrome |

## Files

| File | Role |
|---|---|
| `RegionSelect.m` | Two-click overlay (clang) |
| `build.sh` | Compiles overlay |
| `gemini_snap.py` | Capture + clipboard + Chrome |
| `run.sh` | Entry point |
