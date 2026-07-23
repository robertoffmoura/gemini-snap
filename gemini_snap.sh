#!/bin/bash
# Shell wrapper — prefers region_select two-click, else Python, else drag.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
exec /bin/bash "$ROOT/run.sh" "$@"
