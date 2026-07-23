#!/usr/bin/env python3
"""
Background hotkey listener for Gemini Snap.

Default: Ctrl+Shift+G
Launches gemini_snap.py in a subprocess (no GUI frameworks in this process
beyond a lightweight NSEvent monitor).

If PyObjC is missing/broken, exit with instructions to use Raycast/Shortcuts instead.
"""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import threading

if sys.platform != "darwin":
    print("macOS only.", file=sys.stderr)
    sys.exit(1)

try:
    from AppKit import NSApplication, NSEvent, NSKeyDownMask  # type: ignore
except ImportError:
    print(
        "PyObjC not available — cannot register a global hotkey from Python.\n"
        "Bind your shortcut in Raycast/Alfred/Shortcuts to:\n"
        f"  {os.path.join(os.path.dirname(os.path.abspath(__file__)), 'run.sh')}",
        file=sys.stderr,
    )
    sys.exit(1)


KEYCODES = {
    "a": 0, "s": 1, "d": 2, "f": 3, "h": 4, "g": 5, "z": 6, "x": 7,
    "c": 8, "v": 9, "b": 11, "q": 12, "w": 13, "e": 14, "r": 15,
    "y": 16, "t": 17, "1": 18, "2": 19, "3": 20, "4": 21, "6": 22,
    "5": 23, "9": 25, "7": 26, "8": 28, "0": 29, "o": 31, "u": 32,
    "i": 34, "p": 35, "l": 37, "j": 38, "k": 40, "n": 45, "m": 46,
}

NSEventModifierFlagCommand = 1 << 20
NSEventModifierFlagShift = 1 << 17
NSEventModifierFlagControl = 1 << 18
NSEventModifierFlagOption = 1 << 19
MOD_MASK_ALL = (
    NSEventModifierFlagCommand
    | NSEventModifierFlagShift
    | NSEventModifierFlagControl
    | NSEventModifierFlagOption
)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_SNAP = os.path.join(SCRIPT_DIR, "gemini_snap.py")
RUN_SH = os.path.join(SCRIPT_DIR, "run.sh")


def parse_modifiers(spec: str) -> int:
    parts = {p.strip().lower() for p in spec.replace("-", "+").split("+") if p.strip()}
    mapping = {
        "cmd": NSEventModifierFlagCommand,
        "command": NSEventModifierFlagCommand,
        "shift": NSEventModifierFlagShift,
        "ctrl": NSEventModifierFlagControl,
        "control": NSEventModifierFlagControl,
        "alt": NSEventModifierFlagOption,
        "option": NSEventModifierFlagOption,
        "opt": NSEventModifierFlagOption,
    }
    mask = 0
    for p in parts:
        if p not in mapping:
            raise SystemExit(f"Unknown modifier: {p}")
        mask |= mapping[p]
    return mask


class HotkeyRunner:
    def __init__(self, snap_path: str, keycode: int, mod_mask: int, extra_args: list):
        self.snap_path = snap_path
        self.keycode = keycode
        self.mod_mask = mod_mask
        self.extra_args = extra_args
        self._lock = threading.Lock()
        self._running = False

    def matches(self, event) -> bool:
        if event.keyCode() != self.keycode:
            return False
        flags = int(event.modifierFlags()) & MOD_MASK_ALL
        return flags == self.mod_mask

    def launch_snap(self) -> None:
        with self._lock:
            if self._running:
                return
            self._running = True

        def _run():
            try:
                # Prefer run.sh so region_select is built if needed
                if os.path.isfile(RUN_SH):
                    cmd = ["/bin/zsh", RUN_SH, *self.extra_args]
                else:
                    cmd = [sys.executable, self.snap_path, *self.extra_args]
                subprocess.call(cmd, cwd=SCRIPT_DIR)
            finally:
                with self._lock:
                    self._running = False

        threading.Thread(target=_run, daemon=True).start()


def main() -> int:
    parser = argparse.ArgumentParser(description="Global hotkey → Gemini Snap")
    parser.add_argument("--key", default="g")
    parser.add_argument("--modifiers", default="ctrl+shift")
    parser.add_argument("--snap", default=DEFAULT_SNAP)
    parser.add_argument("snap_args", nargs="*")
    args = parser.parse_args()

    key = args.key.lower()
    if key not in KEYCODES:
        print(f"Unsupported key '{key}'.", file=sys.stderr)
        return 1

    runner = HotkeyRunner(args.snap, KEYCODES[key], parse_modifiers(args.modifiers), args.snap_args)

    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(1)  # accessory

    def on_key(event):
        if runner.matches(event):
            print(f"Hotkey → {args.snap}", flush=True)
            runner.launch_snap()

    def on_key_local(event):
        on_key(event)
        return event

    monitor = NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(NSKeyDownMask, on_key)
    local = NSEvent.addLocalMonitorForEventsMatchingMask_handler_(NSKeyDownMask, on_key_local)

    if monitor is None:
        print(
            "Could not register global key monitor (Accessibility permission?).\n"
            f"Or bind a shortcut to: {RUN_SH}",
            file=sys.stderr,
        )
        return 1

    print(
        f"Gemini Snap hotkey: {args.modifiers}+{key}\n"
        "Ctrl+C to quit.",
        flush=True,
    )

    def _stop(signum, frame):
        if monitor:
            NSEvent.removeMonitor_(monitor)
        if local:
            NSEvent.removeMonitor_(local)
        sys.exit(0)

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)
    app.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
