#!/bin/zsh
# Build the two-click region selector with clang (Objective-C).
# Avoids the broken Swift module maps on many CLT installs.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
OUT="$ROOT/region_select"
SRC="$ROOT/RegionSelect.m"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "Build on macOS only." >&2
  exit 1
fi

if ! command -v clang >/dev/null 2>&1; then
  echo "clang not found. Install Xcode Command Line Tools:" >&2
  echo "  xcode-select --install" >&2
  exit 1
fi

echo "Compiling two-click selector (Objective-C + clang)…"
echo "  $SRC → $OUT"

# Prefer macOS SDK if available
SDKROOT="$(xcrun --sdk macosx --show-sdk-path 2>/dev/null || true)"
ARGS=(-fobjc-arc -O2 -framework Cocoa -o "$OUT" "$SRC")
if [[ -n "${SDKROOT}" ]]; then
  ARGS=(-isysroot "$SDKROOT" "${ARGS[@]}")
fi

if ! clang "${ARGS[@]}"; then
  echo "" >&2
  echo "clang build failed. Falling back is still available via Python two-click" >&2
  echo "(no overlay) when you run ./run.sh" >&2
  exit 1
fi

chmod +x "$OUT"
echo "OK: $OUT"
echo "Test: $OUT   (Esc cancels; should print x,y,w,h)"
