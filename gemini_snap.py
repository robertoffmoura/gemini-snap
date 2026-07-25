#!/usr/bin/env python3
"""
Gemini Snap — two-click region → screenshot → Gemini in Browser

Modules:
  - BuildService: Objective-C selector build/cache management
  - RegionSelector: Region selection via native overlay
  - ClipboardService: PNG capture and pasteboard operations
  - BrowserAutomator: Browser activation, focus, paste, submit
  - GeminiSnapApp: Workflow orchestrator
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


def get_user_cache_dir() -> str:
	cache_dir = os.path.expanduser("~/Library/Caches/gemini-snap")
	try:
		os.makedirs(cache_dir, exist_ok=True)
		return cache_dir
	except Exception:
		return tempfile.gettempdir()


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REGION_SELECT_SRC = os.path.join(SCRIPT_DIR, "RegionSelect.m")
REGION_SELECT_BIN = os.path.join(get_user_cache_dir(), "region_select")
GEMINI_URL = "https://gemini.google.com/app"
DEFAULT_LOAD_WAIT = 2.5
DEFAULT_PASTE_WAIT = 1.5
DEFAULT_BROWSER = "Google Chrome"


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


class NotificationService:
	@staticmethod
	def notify(title: str, message: str) -> None:
		script = f'display notification "{message}" with title "{title}"'
		run_osascript(script)


def run_osascript(script: str) -> subprocess.CompletedProcess:
	return subprocess.run(
		["osascript", "-"],
		input=script,
		capture_output=True,
		text=True,
	)


# ---------------------------------------------------------------------------
# Services
# ---------------------------------------------------------------------------
class BuildService:
	def __init__(self, src_path: str = REGION_SELECT_SRC, bin_path: str = REGION_SELECT_BIN):
		self.src_path = src_path
		self.bin_path = bin_path

	def get_or_build_binary(self, force_rebuild: bool = False) -> Optional[str]:
		if not force_rebuild and os.path.isfile(self.bin_path) and os.access(self.bin_path, os.X_OK):
			if os.path.isfile(self.src_path):
				if os.path.getmtime(self.bin_path) >= os.path.getmtime(self.src_path):
					return self.bin_path
		if not os.path.isfile(self.src_path) or not shutil.which("clang"):
			return None

		print("Building two-click selector with clang…", flush=True)
		sdkroot = ""
		try:
			res = subprocess.run(
				["xcrun", "--sdk", "macosx", "--show-sdk-path"],
				capture_output=True,
				text=True,
			)
			if res.returncode == 0:
				sdkroot = res.stdout.strip()
		except Exception:
			pass

		args = [
			"clang",
			"-fobjc-arc",
			"-O2",
			"-framework",
			"Cocoa",
			"-o",
			self.bin_path,
			self.src_path,
		]
		if sdkroot:
			args = ["clang", "-isysroot", sdkroot] + args[1:]

		result = subprocess.run(args, cwd=SCRIPT_DIR)
		if result.returncode != 0:
			return None
		if os.path.isfile(self.bin_path):
			os.chmod(self.bin_path, 0o755)
			return self.bin_path
		return None


class RegionSelector:
	def __init__(self, build_service: Optional[BuildService] = None):
		self.build_service = build_service or BuildService()

	def select_region(self, force_rebuild: bool = False) -> Tuple[str, Optional[Rect]]:
		"""
		Returns (status, rect) where status is 'ok' | 'cancel' | 'unavailable' | 'error'
		"""
		binary = self.build_service.get_or_build_binary(force_rebuild=force_rebuild)
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


class ClipboardService:
	@staticmethod
	def capture_region_to_file(rect: Rect, path: str) -> None:
		cmd = ["screencapture", "-x", "-t", "png", "-R", rect.as_screencapture_R(), path]
		result = subprocess.run(cmd, capture_output=True, text=True)
		if result.returncode != 0 or not os.path.isfile(path) or os.path.getsize(path) == 0:
			raise RuntimeError(
				f"screencapture failed ({result.returncode}): "
				f"{result.stderr or result.stdout or 'check Screen Recording permission'}"
			)

	@staticmethod
	def copy_png_to_clipboard(path: str) -> None:
		abs_path = os.path.abspath(path)
		safe_path = abs_path.replace("\\", "\\\\").replace('"', '\\"')
		script = f'''
set thePath to POSIX file "{safe_path}"
set the clipboard to (read thePath as «class PNGf»)
'''
		result = run_osascript(script)
		if result.returncode == 0:
			return

		script2 = f'''
use framework "AppKit"
use framework "Foundation"
set img to current application's NSImage's alloc()'s initWithContentsOfFile:"{safe_path}"
if img is missing value then error "Could not load image"
set pb to current application's NSPasteboard's generalPasteboard()
pb's clearContents()
pb's writeObjects:{{img}}
'''
		result2 = run_osascript(script2)
		if result2.returncode == 0:
			return

		raise RuntimeError(
			"Could not put image on clipboard.\n"
			f"PNGf method: {result.stderr or result.stdout}\n"
			f"AppKit method: {result2.stderr or result2.stdout}"
		)

	@staticmethod
	def has_image() -> bool:
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


class BrowserAutomator:
	def __init__(self, browser_name: str = DEFAULT_BROWSER):
		self.browser_name = browser_name

	def open_gemini(self) -> None:
		r = subprocess.run(
			["open", "-a", self.browser_name, GEMINI_URL],
			capture_output=True,
			text=True,
		)
		if r.returncode == 0:
			return

		script = f'''
tell application "{self.browser_name}"
	activate
	open location "{GEMINI_URL}"
end tell
'''
		result = run_osascript(script)
		if result.returncode != 0:
			raise RuntimeError(
				f"Could not open {self.browser_name}.\n"
				f"{r.stderr or r.stdout}\n{result.stderr or result.stdout}\n"
				f"Is {self.browser_name} installed?"
			)

	def bring_to_front(self) -> None:
		subprocess.run(["open", "-a", self.browser_name], capture_output=True)
		run_osascript(f'tell application "{self.browser_name}" to activate')

	def wait_until_frontmost(self, timeout: float) -> bool:
		end_time = time.time() + max(timeout, 0.5)
		while time.time() < end_time:
			self.bring_to_front()
			probe = run_osascript(
				'tell application "System Events" to get name of first process whose frontmost is true'
			)
			if probe.returncode == 0 and self.browser_name.lower() in (probe.stdout or "").lower():
				return True
			time.sleep(0.2)
		return False

	def paste_and_maybe_submit(
		self,
		load_wait: float = DEFAULT_LOAD_WAIT,
		paste_wait: float = DEFAULT_PASTE_WAIT,
		auto_submit: bool = True,
	) -> None:
		print(f"Waiting for {self.browser_name} to activate…", flush=True)
		self.wait_until_frontmost(load_wait)
		time.sleep(0.3)

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

		script = f'''
tell application "System Events"
	if exists process "{self.browser_name}" then
		tell process "{self.browser_name}"
			set frontmost to true
		end tell
	end if
	delay 0.2
	keystroke "v" using {{command down}}
end tell
'''
		result = run_osascript(script)
		if result.returncode != 0:
			simple = run_osascript(
				'tell application "System Events" to keystroke "v" using {command down}'
			)
			if simple.returncode != 0:
				raise RuntimeError(
					f"Could not paste into {self.browser_name}.\n"
					f"Detail: {(result.stderr or simple.stderr or '').strip()}\n\n"
					"The screenshot is on your clipboard — click Gemini and press ⌘V.\n"
					"Also check Accessibility is enabled for your terminal (see above)."
				)

		if auto_submit:
			print(f"Waiting {paste_wait:.1f}s for image to attach, then Enter…", flush=True)
			time.sleep(paste_wait)
			self.bring_to_front()
			time.sleep(0.2)
			ent = run_osascript('tell application "System Events" to key code 36')
			if ent.returncode != 0:
				print(
					"Paste likely worked; Enter failed. Press Return in Gemini manually.",
					file=sys.stderr,
				)

	def open_and_paste(
		self,
		load_wait: float = DEFAULT_LOAD_WAIT,
		paste_wait: float = DEFAULT_PASTE_WAIT,
		auto_submit: bool = True,
	) -> None:
		self.open_gemini()
		self.paste_and_maybe_submit(load_wait, paste_wait, auto_submit)


# ---------------------------------------------------------------------------
# App Orchestrator
# ---------------------------------------------------------------------------
class GeminiSnapApp:
	def __init__(self, args: argparse.Namespace):
		self.args = args
		self.region_selector = RegionSelector()
		self.clipboard_service = ClipboardService()
		self.browser_automator = BrowserAutomator(args.browser)

	def run(self) -> int:
		rect: Optional[Rect] = None
		png_path: Optional[str] = None
		tmp_dir = None

		try:
			if self.args.rect:
				rect = Rect.parse(self.args.rect)
			else:
				status, rect = self.region_selector.select_region(force_rebuild=self.args.rebuild)
				if status == "cancel":
					return 0
				if status != "ok":
					return 1

			if rect is not None:
				print(f"Capturing {rect.as_screencapture_R()} …", flush=True)
				if self.args.save:
					png_path = os.path.abspath(self.args.save)
				else:
					tmp_dir = tempfile.mkdtemp(prefix="gemini-snap-")
					png_path = os.path.join(tmp_dir, "capture.png")
				try:
					self.clipboard_service.capture_region_to_file(rect, png_path)
					self.clipboard_service.copy_png_to_clipboard(png_path)
				except RuntimeError as e:
					print(str(e), file=sys.stderr)
					NotificationService.notify("Gemini Snap", "Screenshot failed — Screen Recording permission?")
					return 2

			if not self.clipboard_service.has_image():
				print(
					"Clipboard has no image. Enable Screen Recording for Terminal,\n"
					"quit & reopen Terminal, then retry.",
					file=sys.stderr,
				)
				NotificationService.notify("Gemini Snap", "No image on clipboard")
				return 2

			print("Screenshot ready on clipboard.", flush=True)

			if self.args.dry_run:
				print(f"Dry run OK.{f' Saved: {png_path}' if png_path else ''}")
				NotificationService.notify("Gemini Snap", "Screenshot copied to clipboard")
				return 0

			print(f"Opening Gemini in {self.args.browser} and pasting…", flush=True)
			try:
				self.browser_automator.open_and_paste(
					load_wait=self.args.load_wait,
					paste_wait=self.args.paste_wait,
					auto_submit=not self.args.no_submit,
				)
			except RuntimeError as e:
				print(str(e), file=sys.stderr)
				NotificationService.notify(
					"Gemini Snap",
					"Paste failed — enable Accessibility for Terminal",
				)
				print(
					"\nManual fallback: the image IS on your clipboard.\n"
					"Click the Gemini prompt and press ⌘V, then Enter.",
					file=sys.stderr,
				)
				return 3

			NotificationService.notify(
				"Gemini Snap",
				"Sent to Gemini" if not self.args.no_submit else "Pasted into Gemini",
			)
			print("Done.", flush=True)
			return 0
		finally:
			if tmp_dir and os.path.isdir(tmp_dir) and not self.args.save:
				shutil.rmtree(tmp_dir, ignore_errors=True)


def main(argv: Optional[list] = None) -> int:
	parser = argparse.ArgumentParser(
		description="Two-click screen capture → Gemini in web browser"
	)
	parser.add_argument("--browser", default=DEFAULT_BROWSER, help="Target browser (default: Google Chrome)")
	parser.add_argument("--load-wait", type=float, default=DEFAULT_LOAD_WAIT)
	parser.add_argument("--paste-wait", type=float, default=DEFAULT_PASTE_WAIT)
	parser.add_argument("--no-submit", action="store_true")
	parser.add_argument("--save", metavar="PATH", help="Also keep PNG at PATH")
	parser.add_argument("--dry-run", action="store_true")
	parser.add_argument("--rebuild", action="store_true", help="Force recompiling the two-click region selector binary")
	parser.add_argument("--rect", metavar="X,Y,W,H")
	args = parser.parse_args(argv)

	app = GeminiSnapApp(args)
	return app.run()


if __name__ == "__main__":
	sys.exit(main())
