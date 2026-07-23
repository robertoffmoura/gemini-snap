#!/bin/zsh
# Gemini Snap launcher — two-click by default, no Swift.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"

# Best-effort one-time clang build (fast; does not use broken swiftc)
if [[ ! -x "$ROOT/region_select" && -f "$ROOT/RegionSelect.m" ]]; then
  if command -v clang >/dev/null 2>&1; then
    echo "Building two-click selector (clang)…"
    if ! /bin/zsh "$ROOT/build.sh"; then
      echo "Note: overlay build failed — will use Python two-click fallback."
    fi
  fi
fi

PYTHON="${PYTHON:-python3}"
exec "$PYTHON" "$ROOT/gemini_snap.py" "$@"
