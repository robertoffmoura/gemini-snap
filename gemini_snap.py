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
import base64
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
DEFAULT_LOAD_WAIT = 5.0
# Max seconds to poll the Gemini UI for image-attachment readiness before Enter.
# We return as soon as the attachment is detected — this is not a fixed sleep.
DEFAULT_PASTE_WAIT = 5.0
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
	# Chromium-family apps that expose Chrome's AppleScript dictionary
	# (execute javascript on tabs). Safari uses a different command.
	_CHROMIUM_BROWSERS = {
		"google chrome",
		"google chrome canary",
		"google chrome beta",
		"google chrome dev",
		"brave browser",
		"microsoft edge",
		"microsoft edge beta",
		"microsoft edge dev",
		"chromium",
		"arc",
		"dia",
		"vivaldi",
		"opera",
	}

	# JS: is Gemini's composer present and focusable?
	_JS_COMPOSER_STATUS = r"""
(function () {
  var input = document.querySelector(
    'div[contenteditable="true"], [role="textbox"], rich-textarea, textarea'
  );
  if (!input) return "no-input";
  try { input.focus(); } catch (e) {}
  return "ready";
})();
""".strip()

	# JS: fingerprint of "something attached in the composer".
	# Returns a compact token like "b2:r1:s1:i3" so we can diff before/after paste.
	#   b = blob/data preview images
	#   r = visible remove/dismiss buttons
	#   s = enabled send buttons
	#   i = large images in the lower (composer) half of the viewport
	#   u = 1 if an upload/progress indicator is visible
	_JS_ATTACH_FINGERPRINT = r"""
(function () {
  try {
    function isVisible(el) {
      if (!el) return false;
      var r = el.getBoundingClientRect();
      return r.width > 0 && r.height > 0;
    }

    var busy = document.querySelector(
      '[aria-busy="true"], [role="progressbar"], mat-progress-spinner, circular-progress'
    );
    var u = busy && isVisible(busy) ? 1 : 0;

    var b = 0, iLarge = 0;
    var imgs = document.querySelectorAll("img");
    for (var i = 0; i < imgs.length; i++) {
      var img = imgs[i];
      if (!isVisible(img)) continue;
      var src = (img.currentSrc || img.src || "").toLowerCase();
      var w = Math.max(img.naturalWidth || 0, img.clientWidth || 0, img.width || 0);
      var h = Math.max(img.naturalHeight || 0, img.clientHeight || 0, img.height || 0);
      if (src.indexOf("blob:") === 0 || src.indexOf("data:image") === 0) {
        b += 1;
        continue;
      }
      if (w >= 48 && h >= 48) {
        var top = img.getBoundingClientRect().top;
        if (top > window.innerHeight * 0.35) iLarge += 1;
      }
    }

    var r = 0, s = 0;
    var buttons = document.querySelectorAll("button, [role='button']");
    for (var j = 0; j < buttons.length; j++) {
      var btn = buttons[j];
      if (!isVisible(btn)) continue;
      var label = (
        (btn.getAttribute("aria-label") || "") + " " +
        (btn.getAttribute("data-tooltip") || "") + " " +
        (btn.title || "")
      ).toLowerCase();
      if (
        label.indexOf("remove") !== -1 ||
        label.indexOf("delete") !== -1 ||
        label.indexOf("dismiss") !== -1
      ) {
        r += 1;
      }
      if (label.indexOf("send") !== -1) {
        var disabled =
          btn.disabled ||
          btn.getAttribute("aria-disabled") === "true" ||
          (btn.classList && btn.classList.contains("disabled"));
        if (!disabled) s += 1;
      }
    }

    return "b" + b + ":r" + r + ":s" + s + ":i" + iLarge + ":u" + u;
  } catch (err) {
    return "error";
  }
})();
""".strip()

	def __init__(self, browser_name: str = DEFAULT_BROWSER):
		self.browser_name = browser_name

	@property
	def _browser_key(self) -> str:
		return self.browser_name.strip().lower()

	def _supports_javascript_bridge(self) -> bool:
		key = self._browser_key
		return key == "safari" or key in self._CHROMIUM_BROWSERS

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

	def run_javascript(self, js: str) -> Tuple[Optional[str], Optional[str]]:
		"""
		Execute JavaScript in the frontmost browser tab.

		Returns (result, error). result is the JS return value as a string when
		successful. error is a short reason when the bridge is unavailable or
		the call failed (e.g. JS-from-Apple-Events disabled).

		The payload is base64-wrapped so we never fight AppleScript string
		escaping for quotes/newlines inside the probe scripts.
		"""
		b64 = base64.b64encode(js.encode("utf-8")).decode("ascii")
		# Decode + eval in-page; String() normalizes non-string returns.
		wrapper = (
			f'(function(){{var s=atob("{b64}");'
			f"var r=eval(s);return(r===undefined||r===null)?\"\":String(r);}})()"
		)
		# Escape for embedding inside an AppleScript double-quoted string.
		# Without this the `"` around the base64 payload and the `?"":`
		# empty-string literal break the AppleScript string delimiter.
		wrapper = wrapper.replace('\\', '\\\\').replace('"', '\\"')

		key = self._browser_key
		if key == "safari":
			script = f'''
tell application "Safari"
	try
		if (count of windows) = 0 then return "ERR:NOWIN"
		return do JavaScript "{wrapper}" in current tab of front window
	on error errText
		return "ERR:" & errText
	end try
end tell
'''
		elif key in self._CHROMIUM_BROWSERS:
			script = f'''
tell application "{self.browser_name}"
	try
		if (count of windows) = 0 then return "ERR:NOWIN"
		return execute active tab of front window javascript "{wrapper}"
	on error errText
		return "ERR:" & errText
	end try
end tell
'''
		else:
			return None, f"JS bridge not supported for browser {self.browser_name!r}"

		res = run_osascript(script)
		out = (res.stdout or "").strip()
		err = (res.stderr or "").strip()
		if res.returncode != 0:
			return None, err or out or "osascript failed"
		if out.startswith("ERR:"):
			return None, out[4:].strip() or "javascript error"
		# Chrome sometimes returns missing value as empty / "missing value"
		if out.lower() in ("", "missing value"):
			return None, "empty javascript result"
		return out, None

	def wait_for_tab_loaded(self, timeout: float) -> bool:
		"""
		Poll the browser's native AppleScript `loading` flag until the active
		tab finishes its document load (loading == false).
		"""
		script = f'''
tell application "{self.browser_name}"
	activate
	try
		if (count of windows) = 0 then return "NOWIN"
		return (loading of active tab of front window) as string
	on error errText
		return "ERR:" & errText
	end try
end tell
'''
		# Safari uses a slightly different property path in some versions;
		# fall through to timeout and let composer polling take over.
		start_time = time.time()
		deadline = start_time + max(timeout, 0.5)
		while time.time() < deadline:
			res = run_osascript(script)
			out = (res.stdout or "").strip().lower()
			if out == "false":
				return True
			# Brief poll interval — not a fixed readiness wait
			time.sleep(0.1)
		return False

	def _poll_js_status(
		self,
		js: str,
		ready_values: Tuple[str, ...],
		timeout: float,
		poll_interval: float = 0.12,
	) -> Tuple[bool, str, bool]:
		"""
		Poll a JS status probe until it returns one of ready_values or timeout.

		Returns (ok, detail, bridge_usable):
		  - ok: got a ready status
		  - detail: last status or error reason
		  - bridge_usable: False if JS Apple Events is broken/disabled (caller
		    should fall back to a timed sleep). True if the bridge worked but
		    the condition simply wasn't met before timeout.
		"""
		if not self._supports_javascript_bridge():
			return False, "js-bridge-unsupported", False

		deadline = time.time() + max(timeout, 0.2)
		last = "pending"
		js_error_streak = 0
		saw_valid_response = False

		while time.time() < deadline:
			value, err = self.run_javascript(js)
			if err is not None:
				js_error_streak += 1
				last = f"js-error:{err}"
				low = err.lower()
				fatal = any(
					s in low
					for s in (
						"javascript from apple events",
						"allow javascript",
						"not allowed",
						"cannot execute",
						"executing javascript is turned off",
						"javascript is turned off",
					)
				)
				# Sustained errors with no successful probe ⇒ bridge unusable
				if (fatal and js_error_streak >= 2) or (js_error_streak >= 8 and not saw_valid_response):
					if fatal:
						print(
							"  JavaScript from Apple Events appears disabled.\n"
							"  Enable: View → Developer → Allow JavaScript from Apple Events\n"
							"  Falling back to timed wait.",
							flush=True,
						)
					return False, last, False
				time.sleep(poll_interval)
				continue

			js_error_streak = 0
			saw_valid_response = True
			last = (value or "").strip().lower()
			if last in ready_values:
				return True, last, True
			time.sleep(poll_interval)

		return False, last, saw_valid_response

	def wait_for_composer_ready(self, timeout: float) -> bool:
		"""Wait until Gemini's text/composer input exists in the DOM."""
		print("Waiting for Gemini composer…", flush=True)
		ok, detail, _bridge = self._poll_js_status(
			self._JS_COMPOSER_STATUS,
			ready_values=("ready",),
			timeout=timeout,
		)
		if ok:
			return True
		print(f"  Composer not ready ({detail}); pasting anyway…", flush=True)
		return False

	@staticmethod
	def _parse_attach_fingerprint(token: str) -> Optional[dict]:
		"""Parse 'b2:r1:s1:i3:u0' into a dict. Returns None if malformed."""
		token = (token or "").strip().lower()
		if not token or token == "error" or token.startswith("js-error:"):
			return None
		parts = {}
		for piece in token.split(":"):
			if len(piece) < 2 or not piece[1:].isdigit():
				return None
			parts[piece[0]] = int(piece[1:])
		if not all(k in parts for k in ("b", "r", "s", "i", "u")):
			return None
		return parts

	def _attachment_ready(self, before: Optional[dict], after: Optional[dict]) -> bool:
		"""
		True when the post-paste fingerprint shows a new attachment and no
		upload spinner.
		"""
		if not after:
			return False
		# Still uploading/processing
		if after.get("u", 0) > 0:
			return False
		if not before:
			# Absolute signals: local preview, remove chip, or enabled send
			return after["b"] > 0 or after["r"] > 0 or after["s"] > 0

		# Diff against pre-paste baseline — strongest signal
		if after["b"] > before["b"]:
			return True
		if after["r"] > before["r"]:
			return True
		if after["i"] > before["i"]:
			return True
		# Send became enabled after paste (image-only message)
		if after["s"] > before["s"]:
			return True
		return False

	def snapshot_attach_fingerprint(self) -> Tuple[Optional[str], bool]:
		"""
		Read current attachment fingerprint.
		Returns (token_or_None, bridge_usable).
		"""
		if not self._supports_javascript_bridge():
			return None, False
		value, err = self.run_javascript(self._JS_ATTACH_FINGERPRINT)
		if err is not None:
			return None, False
		token = (value or "").strip()
		if not token or token.lower() == "error":
			return None, True
		return token, True

	def wait_for_image_ready_to_submit(
		self,
		timeout: float,
		before_fingerprint: Optional[str] = None,
	) -> Tuple[bool, bool]:
		"""
		After paste: poll until the attachment fingerprint changes (new image
		preview / remove chip / send enabled) and no upload spinner is shown.

		Returns (ready, bridge_usable).
		"""
		print("Polling UI for image attachment…", flush=True)
		if not self._supports_javascript_bridge():
			return False, False

		before = self._parse_attach_fingerprint(before_fingerprint or "")
		deadline = time.time() + max(timeout, 0.2)
		last = "pending"
		js_error_streak = 0
		saw_valid = False

		while time.time() < deadline:
			value, err = self.run_javascript(self._JS_ATTACH_FINGERPRINT)
			if err is not None:
				js_error_streak += 1
				last = f"js-error:{err}"
				low = err.lower()
				fatal = any(
					s in low
					for s in (
						"javascript from apple events",
						"allow javascript",
						"not allowed",
						"cannot execute",
						"executing javascript is turned off",
						"javascript is turned off",
					)
				)
				if (fatal and js_error_streak >= 2) or (js_error_streak >= 8 and not saw_valid):
					if fatal:
						print(
							"  JavaScript from Apple Events appears disabled.\n"
							"  Enable: View → Developer → Allow JavaScript from Apple Events\n"
							"  Falling back to timed wait.",
							flush=True,
						)
					return False, False
				time.sleep(0.1)
				continue

			js_error_streak = 0
			saw_valid = True
			last = (value or "").strip()
			after = self._parse_attach_fingerprint(last)
			if self._attachment_ready(before, after):
				print(f"  Image ready (before={before_fingerprint or '—'} after={last})", flush=True)
				return True, True
			time.sleep(0.1)

		if saw_valid:
			print(
				f"  Image-ready poll timed out (last={last}); submitting anyway…",
				flush=True,
			)
			return False, True
		return False, False

	def _keystroke_paste(self) -> None:
		script = f'''
tell application "System Events"
	if exists process "{self.browser_name}" then
		tell process "{self.browser_name}"
			set frontmost to true
		end tell
	end if
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

	def _keystroke_submit(self) -> None:
		# Focus composer via JS when possible, then press Return.
		self.run_javascript(self._JS_COMPOSER_STATUS)
		# Brief settle: the DOM can report attachment-ready before Gemini's
		# internal state is fully wired to accept Return.
		time.sleep(0.3)
		submit_script = f'''
tell application "System Events"
	if exists process "{self.browser_name}" then
		tell process "{self.browser_name}"
			set frontmost to true
		end tell
	end if
	keystroke return
end tell
'''
		ent = run_osascript(submit_script)
		if ent.returncode != 0:
			print(
				"Paste likely worked; Enter failed. Press Return in Gemini manually.",
				file=sys.stderr,
			)

	def paste_and_maybe_submit(
		self,
		load_wait: float = DEFAULT_LOAD_WAIT,
		paste_wait: float = DEFAULT_PASTE_WAIT,
		auto_submit: bool = True,
	) -> None:
		t0 = time.time()
		print(f"Waiting for {self.browser_name} to load…", flush=True)

		loaded = self.wait_for_tab_loaded(load_wait)
		# SPA shell can report loading=false before the composer mounts.
		# Spend remaining budget (or a short floor) polling the real UI.
		elapsed = time.time() - t0
		composer_budget = max(load_wait - elapsed, 1.5) if loaded else max(load_wait - elapsed, 0.5)
		if self._supports_javascript_bridge():
			self.wait_for_composer_ready(composer_budget)
		elif not loaded:
			print("  Tab-load poll timed out; pasting anyway…", flush=True)

		t_loaded = time.time()
		print(f"  [timing] Page ready in {t_loaded - t0:.2f}s", flush=True)

		# Baseline UI fingerprint so we can detect the paste landing via DOM diff.
		before_fp, _ = self.snapshot_attach_fingerprint()

		self._keystroke_paste()

		t_pasted = time.time()
		print(f"  [timing] Pasted in {t_pasted - t_loaded:.2f}s", flush=True)

		if auto_submit:
			# paste_wait is a *maximum* poll budget for attachment UI, not a fixed sleep.
			ready = False
			bridge_usable = False
			if self._supports_javascript_bridge():
				ready, bridge_usable = self.wait_for_image_ready_to_submit(
					paste_wait,
					before_fingerprint=before_fp,
				)

			if not ready and not bridge_usable:
				# No JS bridge, or Apple Events JS disabled: fall back to timed wait.
				print(
					f"Falling back to {paste_wait:.1f}s wait before Enter…",
					flush=True,
				)
				time.sleep(max(paste_wait, 0.0))

			self._keystroke_submit()
			print(f"  [timing] Total flow: {time.time() - t0:.2f}s", flush=True)

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
		if self.args.load_wait < 0 or self.args.paste_wait < 0:
			print("Error: --load-wait and --paste-wait must be non-negative numbers.", file=sys.stderr)
			return 1

		rect: Optional[Rect] = None
		png_path: Optional[str] = None
		tmp_dir = None

		try:
			if self.args.rect:
				try:
					rect = Rect.parse(self.args.rect)
				except ValueError as e:
					print(f"Error parsing --rect: {e}", file=sys.stderr)
					return 1
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

			print("Done.", flush=True)
			return 0
		finally:
			if tmp_dir and os.path.isdir(tmp_dir):
				shutil.rmtree(tmp_dir, ignore_errors=True)


def main(argv: Optional[list] = None) -> int:
	parser = argparse.ArgumentParser(
		description="Two-click screen capture → Gemini in web browser"
	)
	parser.add_argument("--browser", default=DEFAULT_BROWSER, help="Target browser (default: Google Chrome)")
	parser.add_argument(
		"--load-wait",
		type=float,
		default=DEFAULT_LOAD_WAIT,
		help=(
			"Max seconds to wait for the Gemini tab/composer to become ready "
			f"before pasting (default: {DEFAULT_LOAD_WAIT})"
		),
	)
	parser.add_argument(
		"--paste-wait",
		type=float,
		default=DEFAULT_PASTE_WAIT,
		help=(
			"Max seconds to poll the page UI for image-attachment readiness "
			f"before pressing Enter (default: {DEFAULT_PASTE_WAIT}). "
			"Returns early when the attachment is detected."
		),
	)
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
