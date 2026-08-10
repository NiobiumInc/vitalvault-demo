#!/usr/bin/env bash
# VitalVault — one-command setup + run for the Full-only FHE app.
# ILLUSTRATIVE / DEMO-ONLY. NOT A MEDICAL DEVICE.
#
# Builds anything missing (OpenFHE + Niobium client + fhetch_driver + the
# VitalVault stage binaries), then starts the local FHE bridge + UI.
# Re-running is cheap: it only builds what's absent.
#
# Usage:   ./serve/run.sh [PORT]      (default port 8000)
# Requires: macOS on Apple silicon (arm64), Xcode CLT, cmake, python3.
set -euo pipefail

# Resolve repo root from this script's location — NO hardcoded user paths.
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
cd "$ROOT"
PORT="${1:-8010}"
# Toolchain location. Defaults to the pinned submodule so a recursive clone is
# turnkey; set NIOBIUM_CLIENT_ROOT to build against your own niobium-client
# checkout instead (e.g. a newer version than the pinned one).
NC="${NIOBIUM_CLIENT_ROOT:-$ROOT/third_party/niobium-client}"
FD="$NC/vendor/niobium-fhetch/build/tests/fhetch_driver/fhetch_driver"
VVB="$ROOT/vitalvault/nb_out/build"

# --- platform guard ---------------------------------------------------------
if [ "$(uname -s)" != "Darwin" ] || [ "$(uname -m)" != "arm64" ]; then
  echo "ERROR: the prebuilt-style binaries are macOS arm64 (Apple silicon)."
  echo "       This host is $(uname -s)/$(uname -m). See serve/README.md (Linux needs a full rebuild)."
  exit 1
fi
for tool in cmake python3 git; do
  command -v "$tool" >/dev/null 2>&1 || { echo "ERROR: '$tool' not found. Install Xcode CLT + cmake."; exit 1; }
done

# --- submodule --------------------------------------------------------------
# The DSL compiler + FHE toolchain live in the niobium-client submodule. A fresh
# clone should use `git clone --recurse-submodules`; if not, we init it here.
if [ ! -f "$NC/Makefile" ]; then
  echo "[1/4] initializing niobium-client submodule (recursive)…"
  git submodule update --init --recursive
fi

# --- OpenFHE + libnbfhetch + examples (the big one; ~15-30 min first time) ---
# OpenFHE translation units are memory-heavy (~1-2 GB each), so cap parallelism
# at min(cores, RAM_GB/2) to avoid OOM/swap on smaller machines (8 GB -> 4).
CORES=$(sysctl -n hw.ncpu 2>/dev/null || echo 4)
CAP=$(( $(sysctl -n hw.memsize 2>/dev/null || echo 8589934592) / 1073741824 / 2 )); [ "$CAP" -lt 2 ] && CAP=2
JOBS=$(( CORES < CAP ? CORES : CAP ))
if ! ls "$NC"/vendor/lib/openfhe/lib/libOPENFHEpke*.dylib >/dev/null 2>&1 \
   || ! ls "$NC"/build/vendor/niobium-fhetch/libnbfhetch*.dylib >/dev/null 2>&1; then
  echo "[2/4] building OpenFHE + Niobium client with -j$JOBS (first time only — 15-30+ min)…"
  # `release` = config-release + build-release (config MUST run before build).
  make -C "$NC" release NUM_CPUS="$JOBS"
else
  echo "[2/4] OpenFHE + Niobium client present — skipping."
fi

# --- fhetch_driver (cooperative-replay helper) ------------------------------
if [ ! -x "$FD" ]; then
  echo "[3/4] building fhetch_driver…"
  make -f Makefile.vitalvault "$FD"
else
  echo "[3/4] fhetch_driver present — skipping."
fi

# --- VitalVault stage binaries (DSL -> C++ -> binaries) ---------------------
if [ ! -x "$VVB/compute_wellness" ] || [ ! -x "$VVB/decrypt_report" ]; then
  echo "[4/4] building VitalVault stage binaries…"
  make -f Makefile.vitalvault vitalvault
else
  echo "[4/4] VitalVault binaries present — skipping."
fi

echo ""
echo "Starting the Full FHE bridge on http://127.0.0.1:$PORT/"
echo "  Real CKKS ring 65536 (128-classic). Each run takes SEVERAL MINUTES + ~6-7 GB RAM."
echo "  Open the URL, enter your data, and the app runs keygen -> encrypt -> compute -> decrypt."
echo ""
exec python3 serve/fhe_bridge.py --port "$PORT"
