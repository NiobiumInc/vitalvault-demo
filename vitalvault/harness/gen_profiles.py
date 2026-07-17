# Copyright 2024-present Niobium Microsystems, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""VitalVault Stage-3 ground-truth harness (skill Stage 3).

ILLUSTRATIVE / DEMO-ONLY. NOT A MEDICAL DEVICE. NOT FOR CLINICAL USE.

What this does (the package's "get it working in plaintext first" step):

  1. Builds the FIXED feature vector + presence MASK for each profile. The
     vector is always the same length and slot order regardless of which labs
     are present (absent markers -> standardized value 0.0 AND mask 0.0). This
     is exactly what keeps the encrypted circuit fixed and prevents the server
     from inferring which labs were provided: every profile encrypts to the
     same shape, same ciphertext count.
  2. Writes the binary matrices the (future) DSL client stage will load:
        io/<profile>/zvec.bin   float64 [N_SLOTS x N_MARKERS]  standardized z
        io/<profile>/wmask.bin  float64 [N_SLOTS x N_MARKERS]  renorm weights
     (For Stage 3 we just need ONE row populated; the rest is zero padding to
     N_SLOTS, mirroring fraud-flag's column replication. Cohort mode fills
     many rows.)
  3. Computes the cleartext REFERENCE report (scoring.evaluate) and writes it
     to io/<profile>/reference.json — the values the encrypted decrypt stage
     will be asserted against (within a CKKS tolerance).

Standardization, masking, weight renormalization, BMI/WHtR engineering, the
bio-age cap, and confidence are all CLIENT-SIDE here (they leak nothing and
keep depth/division out of the circuit). The penalty/score/bioage-delta/flag
math mirrors what the SERVER will compute encrypted.

Usage:
  python -m harness.gen_profiles personas          # all five review personas
  python -m harness.gen_profiles persona NAME       # one persona
  python -m harness.gen_profiles cohort N [--seed S] # N synthetic users
  python -m harness.gen_profiles review             # print the persona review
"""
import argparse
import json
import random
import struct
import sys
from pathlib import Path

from . import constants as C
from . import scoring as S
from . import personas as P

EXAMPLE_ROOT = Path(__file__).resolve().parent.parent
N_SLOTS_TOY = 512           # dev profile: single replicated user, well under
                            # ringDim/2 (1024) so CKKS packing never overflows
MARKER_ORDER = [m.key for m in C.MARKERS]   # FIXED slot order
N_MARKERS = len(MARKER_ORDER)
# 25-marker model = Core(7) + Metabolic(3) + Lipid(4) + Inflammation(1) +
# Liver(2) + Kidney(1) + Hormone(4) + Thyroid(3) = 25 marker slots.
# This width is FROZEN once we generate keys: changing it invalidates existing
# ciphertexts/keys. Assert it so an accidental table edit can't silently widen
# the encrypted vector.
assert N_MARKERS == 25, "marker vector must be 25 wide, got %d" % N_MARKERS


# ---------------------------------------------------------------------------
# Fixed vector + mask (the privacy-preserving shape invariant)
# ---------------------------------------------------------------------------
def build_vector_and_mask(profile):
    """[CLIENT] -> (zvec, wmask) lists of length N_MARKERS in FIXED order.

    Absent marker: z=0.0 (the reference mean, neutral) and mask weight=0.0.
    Present marker: z=standardized value, mask=its renormalized panel weight.
    Same length and order for everyone -> server cannot tell what's present.
    """
    # renormalized within-panel weights over SCORABLE markers
    panel_w = {p: S.renormalized_weights(profile, p) for p in C.PANELS}
    zvec, wmask = [], []
    for key in MARKER_ORDER:
        # Absent OR present-but-unscored (informational: a sex/context-specific
        # marker without the basis to interpret it) both encrypt as z=0, mask=0
        # -> identical ciphertext shape, and excluded from scoring / bio-age /
        # follow-ups exactly as scoring.py does (is_scorable gates all of them).
        if not S.is_scorable(profile, key):
            zvec.append(0.0)
            wmask.append(0.0)
        else:
            # standardize with the full profile so sex-specific (creatinine,
            # testosterone, shbg) and context-specific (estradiol, progesterone)
            # markers select the correct (mid, hw) CLIENT-side.
            zvec.append(S.standardize(key, profile[key], profile))
            panel = C.MARKER_BY_KEY[key].panel
            wmask.append(panel_w[panel].get(key, 0.0))
    return zvec, wmask


def _write_matrix(path, rows, ncols):
    """Row-major float64, mirroring fraud-flag's binary layout."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        for row in rows:
            assert len(row) == ncols
            f.write(struct.pack("<%dd" % ncols, *row))


def emit_profile(name, profile, n_slots=N_SLOTS_TOY, out_dir=None):
    """Write zvec.bin, wmask.bin (padded to n_slots rows) + reference.json.

    out_dir overrides the io subdirectory name. The encrypted binaries read
    from io/<instance_name> (e.g. io/toy or io/full per shared.niob:iodir), which
    differs from the persona `name`, so the Makefile passes out_dir="toy" to
    place the data where the Toy-profile binary looks for it.
    """
    zrow, wrow = build_vector_and_mask(profile)
    # replicate the single user's row into row 0; zero-pad to n_slots
    zrows = [zrow] + [[0.0] * N_MARKERS for _ in range(n_slots - 1)]
    wrows = [wrow] + [[0.0] * N_MARKERS for _ in range(n_slots - 1)]
    iodir = EXAMPLE_ROOT / "io" / (out_dir if out_dir else name)
    _write_matrix(iodir / "zvec.bin", zrows, N_MARKERS)
    _write_matrix(iodir / "wmask.bin", wrows, N_MARKERS)
    report = S.evaluate(profile)
    report["_marker_order"] = MARKER_ORDER
    report["_persona"] = name
    report["_note"] = ("ILLUSTRATIVE/DEMO-ONLY, non-diagnostic. Reference "
                       "output for encrypted-pipeline verification.")
    with open(iodir / "reference.json", "w") as f:
        json.dump(report, f, indent=2)
    return report


# ---------------------------------------------------------------------------
# Synthetic cohort generator
# ---------------------------------------------------------------------------
def _rand_profile(rng):
    """A plausible-ish synthetic raw profile with random missing panels."""
    sex = rng.choice(["M", "F"])
    age = rng.randint(19, 75)
    height = rng.gauss(178 if sex == "M" else 165, 7)
    weight = rng.gauss(82 if sex == "M" else 68, 13)
    raw = {
        "age": age, "sex": sex,
        "height_cm": round(height, 1), "weight_kg": round(weight, 1),
        "waist_cm": round(rng.gauss(90 if sex == "M" else 80, 10), 1)
                    if rng.random() < 0.7 else None,
        "activity_ordinal": rng.randint(0, 4),
        "rhr": int(rng.gauss(64, 10)),
        "sbp": int(rng.gauss(118, 12)), "dbp": int(rng.gauss(76, 9)),
        "sleep": round(rng.gauss(7.2, 1.1), 1),
    }
    # randomly include lab panels
    if rng.random() < 0.8:
        raw.update(glucose=int(rng.gauss(92, 14)), a1c=round(rng.gauss(5.4, 0.4), 1))
        if rng.random() < 0.4:
            raw["insulin"] = int(rng.gauss(9, 4))
    if rng.random() < 0.7:
        raw.update(hdl=int(rng.gauss(55, 14)), ldl=int(rng.gauss(105, 30)),
                   tg=int(rng.gauss(110, 45)), tc=int(rng.gauss(185, 35)))
    if rng.random() < 0.4:
        raw.update(tsh=round(rng.gauss(2.0, 1.0), 2),
                   ft3=round(rng.gauss(3.2, 0.5), 2),
                   ft4=round(rng.gauss(1.2, 0.3), 2))
    return raw


def gen_cohort(n, seed=42):
    rng = random.Random(seed)
    reports = []
    for i in range(n):
        prof = P.engineer(_rand_profile(rng))
        reports.append(emit_profile("cohort_%05d" % i, prof))
    return reports


# ---------------------------------------------------------------------------
# Persona review printer
# ---------------------------------------------------------------------------
def print_review():
    print("=" * 74)
    print(" VitalVault Stage-3 PERSONA REVIEW  —  ILLUSTRATIVE / DEMO-ONLY")
    print(" Not a medical device. Not diagnostic. " + C.disclaimer())
    print("=" * 74)
    eng = P.engineered_personas()
    for name, prof in eng.items():
        rep = emit_profile(name, prof)
        label = P.PERSONAS[name]["label"]
        print("\n%s\n  %s" % (label, "-" * (len(label))))
        print("  BMI=%.1f  WHtR=%s  panels=%s"
              % (prof["bmi"], prof["whtr"], rep["present_panels"]))
        ss = "  ".join("%s=%s(%s)" % (p, rep["system_scores"][p],
                                      rep["system_bands"][p])
                       for p in rep["present_panels"])
        print("  scores: " + ss)
        print("  composite=%s (%s)" % (rep["composite"], rep["composite_band"]))
        print("  chrono_age=%s  -> biological_age=%s  (delta=%+0.2f)"
              % (rep["chrono_age"], rep["biological_age"], rep["bioage_delta"]))
        print("  confidence=%s (%s)  followups=%s"
              % (rep["confidence"], rep["confidence_band"], rep["followups"]))


def main(argv=None):
    ap = argparse.ArgumentParser(description="VitalVault Stage-3 ground truth")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("personas")
    sp = sub.add_parser("persona"); sp.add_argument("name")
    sp.add_argument("--as-profile", default=None,
                    help="write into io/<as-profile> (e.g. 'toy') to match "
                         "the binary's instance dir, instead of io/<name>")
    sc = sub.add_parser("cohort"); sc.add_argument("n", type=int)
    sc.add_argument("--seed", type=int, default=42)
    sub.add_parser("review")
    args = ap.parse_args(argv)

    if args.cmd in ("personas", "review"):
        print_review()
    elif args.cmd == "persona":
        prof = P.engineer(P.PERSONAS[args.name])
        rep = emit_profile(args.name, prof, out_dir=args.as_profile)
        print(json.dumps(rep, indent=2))
    elif args.cmd == "cohort":
        reps = gen_cohort(args.n, args.seed)
        print("generated %d synthetic profiles -> io/cohort_*/  "
              "(ILLUSTRATIVE/DEMO-ONLY)" % len(reps))
    return 0


if __name__ == "__main__":
    sys.exit(main())
