#!/bin/bash
# Uninstall Gemini Snap: Clean up shortcuts and services.
set -euo pipefail

SERVICE_NAME="Gemini Snap"
WORKFLOW_DIR="$HOME/Library/Services/${SERVICE_NAME}.workflow"

echo "==> Cleaning up macOS Quick Action Service..."
rm -rf "$WORKFLOW_DIR"

echo "==> Removing keyboard shortcut from preferences..."
PBS_PLIST="$HOME/Library/Preferences/pbs.plist"
if [[ -f "$PBS_PLIST" ]]; then
  /usr/libexec/PlistBuddy -c "Delete :NSServicesStatus:'(null) - ${SERVICE_NAME} - runWorkflowAsService'" "$PBS_PLIST" 2>/dev/null || true
fi

echo "==> Updating services cache..."
/System/Library/CoreServices/pbs -update 2>/dev/null || true

echo "Uninstall completed."
