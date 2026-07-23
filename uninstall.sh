#!/bin/zsh
set -euo pipefail

LABEL="com.gemini-snap.hotkey"
PLIST="$HOME/Library/LaunchAgents/${LABEL}.plist"

launchctl bootout "gui/$(id -u)/${LABEL}" 2>/dev/null || true
launchctl unload "$PLIST" 2>/dev/null || true
rm -f "$PLIST"

echo "LaunchAgent removed. Virtualenv left in place — delete the folder if you want a full wipe."
