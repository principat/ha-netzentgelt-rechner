#!/usr/bin/env bash
# Usage: scripts/e2e-ui.sh <ha-version e.g. 2026.10>
# Visual tests: the real HA frontend in headless Chromium (Playwright); screenshots land in
# tests/e2e/screenshots. One-time setup: uv run python -m playwright install --with-deps chromium
set -euo pipefail
cd "$(dirname "$0")/.."
exec scripts/e2e.sh "${1:-2026.10}" ui
