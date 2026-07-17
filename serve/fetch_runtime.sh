#!/usr/bin/env bash
# Provision the native FHE runtime into vendor/fhe_runtime/ (git-ignored).
#
#   ./serve/fetch_runtime.sh                 # download if configured, else build from source
#   ./serve/fetch_runtime.sh --build-runtime # force build from source (the supported path)
#   ./serve/fetch_runtime.sh --download      # force download (requires archive_url in runtime.lock)
#
# The from-source path shallow-clones niobium-client at the EXACT pinned commit
# into .cache/ and builds OpenFHE + FHETCH + fhetch_driver + autofacade from THAT
# source (it does NOT reuse third_party/niobium-client). It requires internet to
# clone the pinned source, unless .cache/ already holds it.
#
# No hardcoded user paths: the repo root is resolved from this script's location.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
cd "$ROOT"

LOCK="vendor/runtime.lock"
RUNTIME="vendor/fhe_runtime"
CACHE="$ROOT/.cache"
SRC="$CACHE/niobium-src"

lock() { grep -E "^$1[[:space:]]*=" "$LOCK" | head -1 | sed 's/^[^=]*=[[:space:]]*//; s/[[:space:]]*$//'; }
URL="$(lock niobium_client_url)"
COMMIT="$(lock niobium_client_commit)"
ARCH="$(lock arch)"
ARCHIVE_URL="$(lock archive_url)"
ARCHIVE_SHA="$(lock archive_sha256)"

MODE="auto"
case "${1:-}" in
  --build-runtime) MODE="build" ;;
  --download)      MODE="download" ;;
  "" )             MODE="auto" ;;
  *) echo "usage: $0 [--build-runtime|--download]"; exit 2 ;;
esac

# --- platform guard ---------------------------------------------------------
host="$(uname -s | tr '[:upper:]' '[:lower:]')-$(uname -m)"
if [ "$host" != "$ARCH" ]; then
  echo "ERROR: runtime pin is for '$ARCH' but this host is '$host'."
  echo "       Build from source on this platform with --build-runtime (may need porting)."
  [ "$MODE" = "download" ] && exit 1
fi

if [ "$MODE" = "auto" ]; then
  if [ -n "$ARCHIVE_URL" ]; then MODE="download"; else MODE="build"; fi
fi

# ===========================================================================
# Download path (phase 2 — only when archive_url is configured)
# ===========================================================================
if [ "$MODE" = "download" ]; then
  [ -n "$ARCHIVE_URL" ] || { echo "ERROR: --download but archive_url is empty in $LOCK (phase-2/optional)."; exit 1; }
  mkdir -p "$CACHE"
  echo "[runtime] downloading $ARCHIVE_URL"
  curl -fL "$ARCHIVE_URL" -o "$CACHE/runtime.tgz"
  echo "[runtime] verifying sha256"
  echo "$ARCHIVE_SHA  $CACHE/runtime.tgz" | shasum -a 256 -c -
  rm -rf "$RUNTIME"; mkdir -p "$RUNTIME"
  tar -xzf "$CACHE/runtime.tgz" -C "$RUNTIME"
  echo "$COMMIT" > "$RUNTIME/VERSION"
  echo "[runtime] installed from archive → $RUNTIME"
  exit 0
fi

# ===========================================================================
# Build-from-source path (supported)
# ===========================================================================
for t in git cmake make; do command -v "$t" >/dev/null || { echo "ERROR: '$t' required."; exit 1; }; done

echo "[runtime] shallow-cloning $URL @ $COMMIT into .cache/ (needs internet unless cached)…"
mkdir -p "$SRC"
if [ ! -d "$SRC/.git" ]; then git -C "$SRC" init -q; git -C "$SRC" remote add origin "$URL"; fi
# fetch the exact pinned commit (GitHub allows fetching a reachable SHA)
if ! git -C "$SRC" fetch --depth 1 origin "$COMMIT" 2>/dev/null; then
  echo "[runtime] direct SHA fetch unavailable; fetching branch then checking out the pin…"
  git -C "$SRC" fetch --depth 50 origin '+refs/heads/*:refs/remotes/origin/*'
fi
git -C "$SRC" checkout -q "$COMMIT"
echo "[runtime] initializing niobium-fhetch (+ nested OpenFHE) submodules…"
git -C "$SRC" submodule update --init --recursive --depth 1 vendor/niobium-fhetch

OFHE_INSTALL="$SRC/vendor/lib/openfhe"
# Parallelism: default to all cores, but allow capping (OpenFHE TUs are memory
# heavy — on <=8 GB machines cap with NIOBIUM_BUILD_JOBS=4 to avoid OOM).
JOBS="${NIOBIUM_BUILD_JOBS:-$(sysctl -n hw.ncpu 2>/dev/null || nproc 2>/dev/null || echo 4)}"
echo "[runtime] configuring + building OpenFHE + libnbfhetch + auto-facade with -j$JOBS (this can take 10-30+ min)…"
make -C "$SRC" config-release NUM_CPUS="$JOBS"
make -C "$SRC" build-release  NUM_CPUS="$JOBS"
echo "[runtime] building fhetch_driver (reusing the just-built OpenFHE)…"
make -C "$SRC/vendor/niobium-fhetch" EXTERNAL_OPENFHE=1 OPENFHE_INSTALL_DIR="$OFHE_INSTALL" \
     NUM_CPUS="$JOBS" config-fhetch-release build-release

# --- assemble vendor/fhe_runtime mirroring the layout the generated CMake expects
echo "[runtime] assembling $RUNTIME …"
rm -rf "$RUNTIME"
mkdir -p "$RUNTIME/vendor/lib/openfhe" \
         "$RUNTIME/vendor/niobium-fhetch/build/tests/fhetch_driver" \
         "$RUNTIME/build/vendor/niobium-fhetch" \
         "$RUNTIME/build/src/auto_facade" \
         "$RUNTIME/build/_deps/yaml_cpp-build"
cp -R  "$OFHE_INSTALL/lib"     "$RUNTIME/vendor/lib/openfhe/lib"
cp -R  "$OFHE_INSTALL/include" "$RUNTIME/vendor/lib/openfhe/include"
cp -R  "$SRC/vendor/niobium-fhetch/include" "$RUNTIME/vendor/niobium-fhetch/include"
cp     "$SRC/build/vendor/niobium-fhetch/"libnbfhetch*.dylib "$RUNTIME/build/vendor/niobium-fhetch/"
cp     "$SRC/build/src/auto_facade/"libniobium_client_autofacade.a "$RUNTIME/build/src/auto_facade/"
cp     "$SRC/build/_deps/yaml_cpp-build/"libyaml-cpp*.dylib "$RUNTIME/build/_deps/yaml_cpp-build/"
cp     "$SRC/vendor/niobium-fhetch/build/tests/fhetch_driver/fhetch_driver" \
       "$RUNTIME/vendor/niobium-fhetch/build/tests/fhetch_driver/fhetch_driver"

# --- make fhetch_driver relocatable: resolve dylibs via the vendored lib dir
DRV="$RUNTIME/vendor/niobium-fhetch/build/tests/fhetch_driver/fhetch_driver"
install_name_tool -add_rpath "@loader_path/../../../../lib/openfhe/lib" "$DRV" 2>/dev/null || true
install_name_tool -add_rpath "@loader_path/../../../../../build/vendor/niobium-fhetch" "$DRV" 2>/dev/null || true
chmod +x "$DRV"

# --- provenance + integrity
cp "$SRC/LICENSE" "$RUNTIME/LICENSE" 2>/dev/null || true
cp "$SRC/NOTICE"  "$RUNTIME/NOTICE"  2>/dev/null || true
echo "$COMMIT" > "$RUNTIME/VERSION"
( cd "$RUNTIME" && find . -type f ! -name SHA256SUMS -exec shasum -a 256 {} + > SHA256SUMS )
echo "[runtime] done. $RUNTIME populated ($(du -sh "$RUNTIME" | cut -f1)), pin $COMMIT."
echo "[runtime] (.cache/niobium-src kept for rebuilds; safe to delete to reclaim disk.)"
