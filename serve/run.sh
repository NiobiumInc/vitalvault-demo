#!/usr/bin/env bash
# VitalVault — one-command setup + run for the Full-only FHE app.
# ILLUSTRATIVE / DEMO-ONLY. NOT A MEDICAL DEVICE.
#
# Provisions the native FHE runtime (into git-ignored vendor/fhe_runtime/) if
# missing, builds the VitalVault stage binaries if missing, then starts the
# local FHE bridge + UI. Re-running is cheap: it only does what's absent.
#
# Usage:   ./serve/run.sh [PORT]      (default port 8010)
# Requires: macOS on Apple silicon (arm64), Xcode CLT, cmake, python3, git.
set -euo pipefail

# Resolve repo root from this script's location — NO hardcoded user paths.
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
cd "$ROOT"
PORT="${1:-8010}"
RUNTIME="$ROOT/vendor/fhe_runtime"
FD="$RUNTIME/vendor/niobium-fhetch/build/tests/fhetch_driver/fhetch_driver"
VVB="$ROOT/vitalvault/nb_out/build"
PIN="$(grep -E '^niobium_client_commit' vendor/runtime.lock | sed 's/^[^=]*=[[:space:]]*//; s/[[:space:]]*$//')"

# --- platform guard ---------------------------------------------------------
if [ "$(uname -s)" != "Darwin" ] || [ "$(uname -m)" != "arm64" ]; then
  echo "ERROR: VitalVault's FHE runtime targets macOS arm64 (Apple silicon)."
  echo "       This host is $(uname -s)/$(uname -m). See serve/README.md."
  exit 1
fi
for tool in cmake python3 git; do
  command -v "$tool" >/dev/null 2>&1 || { echo "ERROR: '$tool' not found. Install Xcode CLT + cmake."; exit 1; }
done

# --- [1/3] native FHE runtime (headers + libs + fhetch_driver) --------------
if [ ! -x "$FD" ] || [ "$(cat "$RUNTIME/VERSION" 2>/dev/null || echo none)" != "$PIN" ]; then
  echo "[1/3] native FHE runtime missing → provisioning from source at pin $PIN"
  echo "      (this shallow-clones the pinned source and builds OpenFHE + FHETCH;"
  echo "       needs internet and can take 10-30+ min the first time)…"
  ./serve/fetch_runtime.sh --build-runtime
else
  echo "[1/3] native FHE runtime present (pin $PIN) — skipping."
fi

# --- [2/3] VitalVault stage binaries (DSL -> C++ -> binaries) ----------------
if [ ! -x "$VVB/compute_wellness" ] || [ ! -x "$VVB/decrypt_report" ]; then
  echo "[2/3] building VitalVault stage binaries…"
  make -f Makefile.vitalvault vitalvault
else
  echo "[2/3] VitalVault binaries present — skipping."
fi

# --- [3/3] serve ------------------------------------------------------------
echo "[3/3] starting the Full FHE bridge on http://127.0.0.1:$PORT/"
echo "      Real CKKS ring 65536 (128-classic). Each run takes SEVERAL MINUTES + several GB RAM."
echo "      Open the URL in a browser (do not open ui/index.html directly)."
echo ""
exec python3 serve/fhe_bridge.py --port "$PORT"
