#!/bin/bash
# Gemini Snap launcher
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"

# Best-effort one-time clang build of the native overlay
if [[ ! -x "$ROOT/region_select" && -f "$ROOT/RegionSelect.m" ]]; then
  if command -v clang >/dev/null 2>&1; then
    echo "Building two-click selector (clang)..."
    SDKROOT="$(xcrun --sdk macosx --show-sdk-path 2>/dev/null || true)"
    ARGS=(-fobjc-arc -O2 -framework Cocoa -o "$ROOT/region_select" "$ROOT/RegionSelect.m")
    if [[ -n "${SDKROOT}" ]]; then
      ARGS=(-isysroot "$SDKROOT" "${ARGS[@]}")
    fi
    if clang "${ARGS[@]}"; then
      chmod +x "$ROOT/region_select"
    else
      echo "Note: overlay build failed — will use Python two-click fallback."
    fi
  fi
fi

PYTHON="${PYTHON:-python3}"
exec "$PYTHON" "$ROOT/gemini_snap.py" "$@"
