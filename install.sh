#!/bin/zsh
# Install Gemini Snap: build native selector + optional hotkey LaunchAgent.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
PYTHON="${PYTHON:-/usr/bin/python3}"
LABEL="com.gemini-snap.hotkey"
PLIST="$HOME/Library/LaunchAgents/${LABEL}.plist"

echo "==> Gemini Snap installer"
echo "    Root: $ROOT"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "This only works on macOS." >&2
  exit 1
fi

# Prefer Apple's Python for any residual ObjC use in the hotkey daemon.
if [[ ! -x "$PYTHON" ]]; then
  PYTHON="$(command -v python3)"
fi

echo "==> Default mode: macOS drag-select (screencapture -i) — no Swift build"
if [[ -x "$ROOT/region_select" ]]; then
  echo "    Found prebuilt region_select (optional two-click available)"
fi

chmod +x "$ROOT/gemini_snap.py" "$ROOT/run.sh" "$ROOT/gemini_snap.sh" "$ROOT/build.sh" 2>/dev/null || true
chmod +x "$ROOT/hotkey_daemon.py" 2>/dev/null || true

# Hotkey daemon still uses PyObjC only for NSEvent monitoring (no custom NSView).
# Use a venv with system python when possible to avoid conda segfaults.
VENV="$ROOT/.venv"
echo "==> Creating virtualenv with: $PYTHON"
if "$PYTHON" -c "import sys; print(sys.version)" 2>/dev/null; then
  "$PYTHON" -m venv "$VENV" || python3 -m venv "$VENV"
else
  python3 -m venv "$VENV"
fi
# shellcheck disable=SC1091
source "$VENV/bin/activate"
pip install --upgrade pip
pip install -r "$ROOT/requirements.txt" || {
  echo "PyObjC install failed — hotkey daemon may not work; ./run.sh still works."
}

MODIFIERS="${MODIFIERS:-ctrl+shift}"
KEY="${KEY:-g}"

echo "==> Writing LaunchAgent: $PLIST"
mkdir -p "$HOME/Library/LaunchAgents"

# Hotkey launches run.sh (not Python GUI) — crash-safe path
cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>${VENV}/bin/python</string>
    <string>${ROOT}/hotkey_daemon.py</string>
    <string>--key</string>
    <string>${KEY}</string>
    <string>--modifiers</string>
    <string>${MODIFIERS}</string>
    <string>--snap</string>
    <string>${ROOT}/gemini_snap.py</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>${HOME}/Library/Logs/gemini-snap.log</string>
  <key>StandardErrorPath</key>
  <string>${HOME}/Library/Logs/gemini-snap.err.log</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key>
    <string>/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin</string>
  </dict>
</dict>
</plist>
EOF

launchctl bootout "gui/$(id -u)/${LABEL}" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST" 2>/dev/null || launchctl load "$PLIST"
launchctl kickstart -k "gui/$(id -u)/${LABEL}" 2>/dev/null || true

echo ""
echo "==> Installed."
echo ""
echo "Test capture (no Chrome):"
echo "  ./run.sh --dry-run"
echo ""
echo "Hotkey: ${MODIFIERS}+${KEY}"
echo ""
echo "Permissions (System Settings → Privacy & Security):"
echo "  • Screen Recording"
echo "  • Accessibility"
echo "  • Automation → Google Chrome"
echo ""
echo "If you use conda, prefer Apple Python for the daemon:"
echo "  PYTHON=/usr/bin/python3 ./install.sh"
