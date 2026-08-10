#!/usr/bin/env bash
# VitalVault — run the encrypted computation on Niobium Fog (CLI).
# ILLUSTRATIVE / DEMO-ONLY. NOT A MEDICAL DEVICE. NOT FOR CLINICAL USE.
#
# Runs the Full-profile pipeline (real CKKS, ring 65536, 128-classic) with the
# encrypted compute_wellness stage OFFLOADED to the Niobium Fog service instead
# of the local CPU. key_generation, encrypt_profile, and decrypt_report stay
# local: the secret key never leaves this machine — only the ciphertext trace,
# input ciphertexts, and public evaluation keys are dispatched to the worker.
#
# Fog accepts ring 65536 only, so this runner is Full-profile (the Toy profile
# runs on CPU via `make -f Makefile.vitalvault test-vitalvault`, not on Fog).
#
# Prerequisites:
#   * The app is already built — run `./serve/run.sh` once (first build 15-30+ min).
#   * A Fog account is configured — `~/.fog` (run `fog login` if not).
#
# Usage:   ./serve/fog_run.sh [persona]        (default persona: endurance_athlete)
#          NIOBIUM_CLIENT_ROOT=... ./serve/fog_run.sh   (build-your-own client)
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
NC="${NIOBIUM_CLIENT_ROOT:-$ROOT/third_party/niobium-client}"
VV="$ROOT/vitalvault"
B="$VV/nb_out/build"
PROFILE=1                             # Full (ring 65536) — the only ring Fog accepts
PERSONA="${1:-endurance_athlete}"

# --- prerequisites ----------------------------------------------------------
command -v fog >/dev/null 2>&1 || { echo "ERROR: 'fog' CLI not found on PATH."; exit 1; }
if [ ! -f "${FOG_HOME:-$HOME/.fog}/credentials" ] && [ -z "${FOG_API_TOKEN:-}" ]; then
  echo "ERROR: no Fog credentials found. Run 'fog login' first (or set FOG_API_TOKEN)."
  exit 1
fi
REPLAY_BIN="$NC/build/src/fhetch_transport/nbcc_fhetch_replay"
[ -x "$REPLAY_BIN" ] || { echo "ERROR: transport client missing ($REPLAY_BIN). Build it with ./serve/run.sh."; exit 1; }
for b in key_generation encrypt_profile compute_wellness decrypt_report; do
  [ -x "$B/$b" ] || { echo "ERROR: stage binary '$b' not built. Run ./serve/run.sh once."; exit 1; }
done

# --- environment for the FHE binaries + the Fog transport client ------------
export LD_LIBRARY_PATH="$NC/vendor/lib/openfhe/lib:$NC/build/vendor/niobium-fhetch:$NC/vendor/niobium-fhetch/build:$NC/build/_deps/yaml_cpp-build"
export DYLD_LIBRARY_PATH="$LD_LIBRARY_PATH"
export NBCC_FHETCH_DRIVER="$NC/vendor/niobium-fhetch/build/tests/fhetch_driver/fhetch_driver"
export NBCC_FHETCH_REPLAY_BIN="$REPLAY_BIN"

cd "$VV"

# --- 1. inputs: fixed 25-marker vector for the persona, Full slot count ------
# NOTE: the profile's slot count matters — Full uses 32768 slots. (`gen_profiles
# --as-profile full` writes the 512-slot Toy layout, so we call emit_profile
# directly with n_slots=32768.)
echo "[1/5] generating inputs for persona '$PERSONA' (Full, 32768 slots)…"
python3 - "$PERSONA" <<'PY'
import sys
from harness import gen_profiles as G, personas as P
name = sys.argv[1]
eng = P.engineered_personas()
if name not in eng:
    sys.exit("unknown persona '%s'. options: %s" % (name, ", ".join(sorted(eng))))
G.emit_profile(name, eng[name], n_slots=32768, out_dir="full")
PY

# --- 2. client-side: key generation + encryption (secret key stays local) ----
echo "[2/5] key_generation (local; writes the secret key here, never uploaded)…"
"$B/key_generation" "$PROFILE" >/dev/null
echo "[3/5] encrypt_profile (local)…"
"$B/encrypt_profile" "$PROFILE" >/dev/null

# --- 3. record the ciphertext trace (hollow = no heavy math on this machine) --
echo "[4/5] recording the trace (hollow)…"
rm -rf "compute_wellness_profile_${PROFILE}" fhetch_driver_source_* \
       io/full/encrypted/system_scores_*.bin io/full/encrypted/contributions_*.bin \
       io/full/encrypted/followups_*.bin io/full/encrypted/bioage_delta.bin
"$B/compute_wellness" "$PROFILE" --hollow >/dev/null

# --- 4. dispatch the encrypted computation to Fog ----------------------------
# The recorded trace makes the cache valid, so this invocation replays — with
# --target=FOG that hands the trace off to the worker instead of the local sim.
echo "[5/5] dispatching encrypted compute to Fog (--target=FOG)…"
fog submit "$B/compute_wellness" "$PROFILE" --target=FOG

# --- 5. client-side: decrypt the returned result + show the scores -----------
CHRONO="$(python3 -c "import json;print(json.load(open('io/full/reference.json')).get('chrono_age',40.0))")"
"$B/decrypt_report" "$PROFILE" "$CHRONO" > io/full/fhe_decrypted.txt 2>/dev/null
echo ""
echo "=== VitalVault results (decrypted locally from the Fog output) ==="
python3 - <<'PY'
import json
from harness import constants as C
from harness.gen_profiles import N_MARKERS
vals = [float(x) for x in open("io/full/fhe_decrypted.txt").read().split()
        if x.replace(".", "", 1).replace("-", "", 1).isdigit()]
need = 1 + len(C.PANELS) + N_MARKERS + N_MARKERS
vals = vals[-need:]
ref = json.load(open("io/full/reference.json"))
rp = ref.get("system_scores_raw", {})
print("  biological age : %8.3f   (reference %.3f)" % (vals[0], ref["biological_age"]))
for i, p in enumerate(C.PANELS):
    r = rp.get(p)
    tag = "" if r is None else "   (reference %.3f)" % r
    print("  %-14s : %8.3f%s" % (p, vals[1 + i], tag))
print("\n  (illustrative / demo-only — not a medical device; small deltas are CKKS noise)")
PY
