#!/usr/bin/env python3
"""
Gemini Snap — two-click region → screenshot → Gemini in Chrome

Selection:
  1. ./region_select (Objective-C overlay) if present or buildable via clang
  2. Python two-click via CoreGraphics (no drag; minimal UI)
  3. --mode drag → screencapture -i as last resort

Upload path:
  Capture PNG to a temp file → put PNG on clipboard → open Gemini in Chrome
  → focus page → ⌘V → wait → Enter

Chrome control prefers `open -a` (no Automation permission) + System Events
keystrokes (needs Accessibility for Terminal).
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from typing import Optional, Tuple

if sys.platform != "darwin":
    print("Gemini Snap only runs on macOS.", file=sys.stderr)
    sys.exit(1)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REGION_SELECT_BIN = os.path.join(SCRIPT_DIR, "region_select")
REGION_SELECT_SRC = os.path.join(SCRIPT_DIR, "RegionSelect.m")
GEMINI_URL = "https://gemini.google.com/app"
DEFAULT_LOAD_WAIT = 4.5
DEFAULT_PASTE_WAIT = 1.5


@dataclass
class Rect:
    x: int
    y: int
    w: int
    h: int

    def as_screencapture_R(self) -> str:
        return f"{self.x},{self.y},{self.w},{self.h}"

    @classmethod
    def parse(cls, s: str) -> "Rect":
        parts = [int(p.strip()) for p in s.split(",")]
        if len(parts) != 4:
            raise ValueError("rect must be x,y,w,h")
        x, y, w, h = parts
        if w < 0:
            x += w
            w = abs(w)
        if h < 0:
            y += h
            h = abs(h)
        return cls(x, y, max(w, 1), max(h, 1))


def notify(title: str, message: str) -> None:
    def esc(s: str) -> str:
        return s.replace("\\", "\\\\").replace('"', '\\"')

    subprocess.run(
        ["osascript", "-e", f'display notification "{esc(message)}" with title "{esc(title)}"'],
        capture_output=True,
    )


def run_osascript(script: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
        check=False if not check else False,
    )


# ---------------------------------------------------------------------------
# Two-click: native binary
# ---------------------------------------------------------------------------
def try_build_region_select() -> Optional[str]:
    if os.path.isfile(REGION_SELECT_BIN) and os.access(REGION_SELECT_BIN, os.X_OK):
        return REGION_SELECT_BIN
    if not os.path.isfile(REGION_SELECT_SRC):
        return None
    if not shutil.which("clang"):
        return None

    print("Building two-click selector with clang (one-time)…", flush=True)
    build = os.path.join(SCRIPT_DIR, "build.sh")
    if os.path.isfile(build):
        result = subprocess.run(["/bin/zsh", build], cwd=SCRIPT_DIR)
    else:
        result = subprocess.run(
            [
                "clang",
                "-fobjc-arc",
                "-O2",
                "-framework",
                "Cocoa",
                "-o",
                REGION_SELECT_BIN,
                REGION_SELECT_SRC,
            ]
        )
    if result.returncode != 0:
        return None
    if os.path.isfile(REGION_SELECT_BIN):
        os.chmod(REGION_SELECT_BIN, 0o755)
        return REGION_SELECT_BIN
    return None


def select_region_native() -> Tuple[str, Optional[Rect]]:
    """
    Returns (status, rect) where status is:
      'ok' | 'cancel' | 'unavailable' | 'error'
    """
    binary = try_build_region_select()
    if not binary:
        return "unavailable", None

    print("Click first corner, then opposite corner (Esc cancels)…", flush=True)
    result = subprocess.run([binary], capture_output=True, text=True)
    if result.returncode != 0:
        if result.returncode == 1 or "cancelled" in (result.stderr or "").lower():
            print("Cancelled.")
            return "cancel", None
        print(result.stderr or result.stdout, file=sys.stderr)
        return "error", None

    lines = (result.stdout or "").strip().splitlines()
    if not lines:
        return "error", None
    try:
        return "ok", Rect.parse(lines[-1].strip())
    except ValueError as e:
        print(f"Bad region output: {e}", file=sys.stderr)
        return "error", None


# ---------------------------------------------------------------------------
# Two-click: pure Python + CoreGraphics (ctypes) — no overlay, no drag
# ---------------------------------------------------------------------------
def _load_quartz():
    import ctypes
    import ctypes.util

    path = ctypes.util.find_library("CoreGraphics")
    if not path:
        path = "/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics"
    cg = ctypes.CDLL(path)

    class CGPoint(ctypes.Structure):
        _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double)]

    cg.CGEventCreate.restype = ctypes.c_void_p
    cg.CGEventCreate.argtypes = [ctypes.c_void_p]
    cg.CGEventGetLocation.restype = CGPoint
    cg.CGEventGetLocation.argtypes = [ctypes.c_void_p]
    cg.CGEventSourceButtonState.restype = ctypes.c_bool
    cg.CGEventSourceButtonState.argtypes = [ctypes.c_uint32, ctypes.c_uint32]
    return cg, CGPoint


def _mouse_down(cg) -> bool:
    # kCGEventSourceStateCombinedSessionState = 0
    # kCGMouseButtonLeft = 0
    return bool(cg.CGEventSourceButtonState(0, 0))


def _mouse_pos(cg, CGPoint) -> Tuple[float, float]:
    ev = cg.CGEventCreate(None)
    pt = cg.CGEventGetLocation(ev)
    return float(pt.x), float(pt.y)


def select_region_python_two_click() -> Optional[Rect]:
    """
    Two discrete clicks using CoreGraphics button state.
    No on-screen rectangle preview (clang overlay is preferred for that).
    """
    try:
        cg, CGPoint = _load_quartz()
    except Exception as e:
        print(f"CoreGraphics unavailable: {e}", file=sys.stderr)
        return None

    print(
        "\n=== Two-click capture ===\n"
        "  1) Move to the FIRST corner and click once\n"
        "  2) Move to the OPPOSITE corner and click once\n"
        "  Ctrl+C cancels\n",
        flush=True,
    )
    notify("Gemini Snap", "Click first corner of the region")

    def wait_click(label: str) -> Optional[Tuple[float, float]]:
        print(f"Waiting for {label}…", flush=True)
        # Wait for release first (avoid counting a held button)
        while _mouse_down(cg):
            time.sleep(0.02)
        # Wait for press
        while not _mouse_down(cg):
            time.sleep(0.02)
        x, y = _mouse_pos(cg, CGPoint)
        # Wait for release
        while _mouse_down(cg):
            time.sleep(0.02)
        print(f"  {label}: ({int(x)}, {int(y)})", flush=True)
        return x, y

    try:
        p1 = wait_click("corner 1")
        notify("Gemini Snap", "Click opposite corner")
        time.sleep(0.15)  # debounce
        p2 = wait_click("corner 2")
    except KeyboardInterrupt:
        print("\nCancelled.")
        return None

    if not p1 or not p2:
        return None

    x1, y1 = p1
    x2, y2 = p2
    x = int(round(min(x1, x2)))
    y = int(round(min(y1, y2)))
    w = int(round(abs(x2 - x1)))
    h = int(round(abs(y2 - y1)))
    return Rect(x, y, max(w, 1), max(h, 1))


def select_region_interactive_drag() -> bool:
    print("Drag a rectangle (Esc cancels)…", flush=True)
    return subprocess.run(["screencapture", "-i", "-c", "-x"]).returncode == 0


# ---------------------------------------------------------------------------
# Capture + clipboard
# ---------------------------------------------------------------------------
def capture_region_to_file(rect: Rect, path: str) -> None:
    cmd = ["screencapture", "-x", "-t", "png", "-R", rect.as_screencapture_R(), path]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0 or not os.path.isfile(path) or os.path.getsize(path) == 0:
        raise RuntimeError(
            f"screencapture failed ({result.returncode}): "
            f"{result.stderr or result.stdout or 'check Screen Recording permission'}"
        )


def copy_png_file_to_clipboard(path: str) -> None:
    """
    Put a PNG file on the general pasteboard as real image data.
    More reliable for Gemini paste than screencapture -c alone.
    """
    abs_path = os.path.abspath(path)
    # Method 1: classic AppleScript PNGf read
    script = f'''
set thePath to POSIX file "{abs_path}"
set the clipboard to (read thePath as «class PNGf»)
'''
    result = run_osascript(script)
    if result.returncode == 0:
        return

    # Method 2: AppKit NSImage
    script2 = f'''
use framework "AppKit"
use framework "Foundation"
set img to current application's NSImage's alloc()'s initWithContentsOfFile:"{abs_path}"
if img is missing value then error "Could not load image"
set pb to current application's NSPasteboard's generalPasteboard()
pb's clearContents()
pb's writeObjects:{{img}}
'''
    result2 = run_osascript(script2)
    if result2.returncode == 0:
        return

    # Method 3: screencapture already supports -c from file? re-capture -c
    # Fall back: use `osascript` error details
    raise RuntimeError(
        "Could not put image on clipboard.\n"
        f"PNGf method: {result.stderr or result.stdout}\n"
        f"AppKit method: {result2.stderr or result2.stdout}"
    )


def clipboard_has_image() -> bool:
    script = '''
try
    set t to (clipboard info) as string
    return t
on error
    return ""
end try
'''
    result = run_osascript(script)
    info = (result.stdout or "").lower()
    if any(x in info for x in ("pngf", "tiff", "jpeg", "picture", "image")):
        return True

    # AppKit type list
    script2 = """
use framework "AppKit"
set pb to current application's NSPasteboard's generalPasteboard()
set types to (pb's types()) as list
set joined to ""
repeat with t in types
    set joined to joined & (t as text) & ","
end repeat
return joined
"""
    result2 = run_osascript(script2)
    types = (result2.stdout or "").lower()
    return any(
        t in types
        for t in (
            "public.png",
            "public.tiff",
            "public.jpeg",
            "nspasteboardtypepng",
            "nspasteboardtypetiff",
        )
    )


# ---------------------------------------------------------------------------
# Chrome + Gemini
# ---------------------------------------------------------------------------
def open_gemini_in_chrome() -> None:
    """
    Open Gemini in Chrome without requiring Automation permission when possible.
    """
    # `open -a` uses Launch Services — usually works even when AppleScript Automation is denied.
    r = subprocess.run(
        ["open", "-a", "Google Chrome", GEMINI_URL],
        capture_output=True,
        text=True,
    )
    if r.returncode == 0:
        return

    # Fallback: AppleScript
    script = f'''
tell application "Google Chrome"
    activate
    open location "{GEMINI_URL}"
end tell
'''
    result = run_osascript(script)
    if result.returncode != 0:
        raise RuntimeError(
            "Could not open Google Chrome.\n"
            f"{r.stderr or r.stdout}\n{result.stderr or result.stdout}\n"
            "Is Google Chrome installed?"
        )


def _front_chrome() -> None:
    subprocess.run(["open", "-a", "Google Chrome"], capture_output=True)
    # Also try AppleScript activate (may prompt for Automation once)
    run_osascript('tell application "Google Chrome" to activate')


def paste_and_maybe_submit(
    load_wait: float,
    paste_wait: float,
    auto_submit: bool,
) -> None:
    """
    After Gemini tab is open: wait, paste image, optionally press Enter.

    Needs Accessibility for Terminal so System Events can send keystrokes.
    """
    print(f"Waiting {load_wait:.1f}s for Gemini to load…", flush=True)
    time.sleep(load_wait)

    _front_chrome()
    time.sleep(0.5)

    # Probe Accessibility early with a harmless System Events call
    probe = run_osascript(
        'tell application "System Events" to get name of first process whose frontmost is true'
    )
    if probe.returncode != 0:
        raise RuntimeError(
            "macOS blocked System Events (needed to press ⌘V).\n"
            f"Detail: {(probe.stderr or probe.stdout or '').strip()}\n\n"
            "Fix (required):\n"
            "  1. System Settings → Privacy & Security → Accessibility\n"
            "  2. Enable your terminal app (Terminal / iTerm / Warp / VS Code)\n"
            "  3. Fully quit that app (Cmd+Q) and reopen it\n"
            "  4. Run ./run.sh again\n"
        )

    # Click near bottom-center of the front Chrome window to focus the composer,
    # then paste. Wrapped so a click failure still attempts paste.
    script = f'''
tell application "System Events"
    if exists process "Google Chrome" then
        tell process "Google Chrome"
            set frontmost to true
            try
                set win to front window
                set {{wx, wy}} to position of win
                set {{ww, wh}} to size of win
                -- Gemini prompt is near the bottom center
                click at {{wx + (ww div 2), wy + wh - 90}}
            end try
        end tell
    end if
    delay 0.4
    keystroke "v" using {{command down}}
end tell
'''
    result = run_osascript(script)
    if result.returncode != 0:
        # Minimal fallback: paste only
        simple = run_osascript(
            'tell application "System Events" to keystroke "v" using {command down}'
        )
        if simple.returncode != 0:
            raise RuntimeError(
                "Could not paste into Chrome.\n"
                f"Detail: {(result.stderr or simple.stderr or '').strip()}\n\n"
                "The screenshot is on your clipboard — click Gemini and press ⌘V.\n"
                "Also check Accessibility is enabled for your terminal (see above)."
            )

    if auto_submit:
        print(f"Waiting {paste_wait:.1f}s for image to attach, then Enter…", flush=True)
        time.sleep(paste_wait)
        _front_chrome()
        time.sleep(0.2)
        ent = run_osascript('tell application "System Events" to key code 36')
        if ent.returncode != 0:
            print(
                "Paste likely worked; Enter failed. Press Return in Gemini manually.",
                file=sys.stderr,
            )


def open_gemini_and_paste(
    load_wait: float = DEFAULT_LOAD_WAIT,
    paste_wait: float = DEFAULT_PASTE_WAIT,
    auto_submit: bool = True,
) -> None:
    open_gemini_in_chrome()
    paste_and_maybe_submit(load_wait, paste_wait, auto_submit)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Two-click screen capture → Gemini in Chrome"
    )
    parser.add_argument("--load-wait", type=float, default=DEFAULT_LOAD_WAIT)
    parser.add_argument("--paste-wait", type=float, default=DEFAULT_PASTE_WAIT)
    parser.add_argument("--no-submit", action="store_true")
    parser.add_argument("--save", metavar="PATH", help="Also keep PNG at PATH")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--rect", metavar="X,Y,W,H")
    parser.add_argument(
        "--mode",
        choices=("two-click", "drag"),
        default="two-click",
        help="two-click (default) or drag (screencapture -i)",
    )
    args = parser.parse_args(argv)

    rect: Optional[Rect] = None
    png_path: Optional[str] = None
    tmp_dir = None
    already_on_clipboard = False

    try:
        if args.rect:
            rect = Rect.parse(args.rect)
        elif args.mode == "drag":
            if not select_region_interactive_drag():
                print("Cancelled.")
                return 1
            already_on_clipboard = True
        else:
            # two-click preferred: native overlay, else Python click-click
            status, rect = select_region_native()
            if status == "cancel":
                return 1
            if status != "ok":
                print("Using Python two-click fallback…", flush=True)
                rect = select_region_python_two_click()
                if rect is None:
                    return 1

        if rect is not None:
            print(f"Capturing {rect.as_screencapture_R()} …", flush=True)
            if args.save:
                png_path = os.path.abspath(args.save)
            else:
                tmp_dir = tempfile.mkdtemp(prefix="gemini-snap-")
                png_path = os.path.join(tmp_dir, "capture.png")
            try:
                capture_region_to_file(rect, png_path)
                copy_png_file_to_clipboard(png_path)
            except RuntimeError as e:
                print(str(e), file=sys.stderr)
                notify("Gemini Snap", "Screenshot failed — Screen Recording permission?")
                return 2

        if not clipboard_has_image():
            print(
                "Clipboard has no image. Enable Screen Recording for Terminal,\n"
                "quit & reopen Terminal, then retry.",
                file=sys.stderr,
            )
            notify("Gemini Snap", "No image on clipboard")
            return 2

        print("Screenshot ready on clipboard.", flush=True)

        if args.dry_run:
            print(f"Dry run OK.{f' Saved: {png_path}' if png_path else ''}")
            notify("Gemini Snap", "Screenshot copied to clipboard")
            return 0

        print("Opening Gemini in Chrome and pasting…", flush=True)
        try:
            open_gemini_and_paste(
                load_wait=args.load_wait,
                paste_wait=args.paste_wait,
                auto_submit=not args.no_submit,
            )
        except RuntimeError as e:
            print(str(e), file=sys.stderr)
            notify(
                "Gemini Snap",
                "Paste failed — enable Accessibility for Terminal",
            )
            print(
                "\nManual fallback: the image IS on your clipboard.\n"
                "Click the Gemini prompt and press ⌘V, then Enter.",
                file=sys.stderr,
            )
            return 3

        notify(
            "Gemini Snap",
            "Sent to Gemini" if not args.no_submit else "Pasted into Gemini",
        )
        print("Done.", flush=True)
        return 0
    finally:
        if tmp_dir and os.path.isdir(tmp_dir) and not args.save:
            shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
