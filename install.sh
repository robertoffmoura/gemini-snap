#!/bin/bash
# Install Gemini Snap: build native selector and set executable permissions.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"

echo "==> Gemini Snap installer"
echo "    Root: $ROOT"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "This only works on macOS." >&2
  exit 1
fi

echo "==> Default mode: macOS drag-select (screencapture -i) — no Swift build"
if [[ -x "$ROOT/region_select" ]]; then
  echo "    Found prebuilt region_select (optional two-click available)"
fi

# Compile region_select if source exists
if [[ -f "$ROOT/RegionSelect.m" ]]; then
  /bin/bash "$ROOT/build.sh" || true
fi

# Set executable permissions on scripts and binaries
chmod +x "$ROOT/gemini_snap.py" "$ROOT/run.sh" "$ROOT/gemini_snap.sh" "$ROOT/build.sh" "$ROOT/setup_shortcut.sh" 2>/dev/null || true

echo ""
echo "==> Installed successfully."
echo ""
echo "Test capture (no Chrome):"
echo "  ./run.sh --dry-run"
echo ""
echo "To set up a global keyboard shortcut (⌥⌘G) to run Gemini Snap:"
echo "  ./setup_shortcut.sh"
echo ""
echo "Permissions Checklist (System Settings → Privacy & Security):"
echo "  • Screen Recording"
echo "  • Accessibility (enable your terminal/IDE app)"
echo "  • Automation → Google Chrome"
echo ""
