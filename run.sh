#!/bin/bash
# Gemini Snap launcher
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"

PYTHON="${PYTHON:-python3}"
exec "$PYTHON" "$ROOT/gemini_snap.py" "$@"

