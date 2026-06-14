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
"""VitalVault Stage-3 constants — biomarker scoring framework (ILLUSTRATIVE).

============================================================================
  ILLUSTRATIVE / DEMO-ONLY.  NOT A MEDICAL DEVICE.  NOT FOR CLINICAL USE.
============================================================================
This module is the single source of truth for the VitalVault V1 scoring
model. It is intentionally separated from the computation code so it can be
reviewed in isolation before anything is frozen into the encrypted circuit.

PROVENANCE OF THE NUMBERS
-------------------------
Two distinct kinds of value live here, and the distinction is deliberate:

  * `ref_range` (the low/high text)  — representative ADULT laboratory
    reference intervals, broadly consistent with commonly published ranges
    (e.g. ACC/AHA blood-pressure categories, ADA glucose/A1C cut-points,
    NCEP/ATP lipid desirables, common adult lab TSH/T3/T4 windows). These
    are summarized for a DEMO and are NOT a clinical standard; real intervals
    vary by lab, assay, age, sex, and population.

  * `mid`, `hw`, panel `weight`, and bio-age `beta`  — CONSTRUCTED by the
    VitalVault authors for demo plausibility. `mid` is ~the center of the
    reference interval; `hw` (half-width) is ~half its span. Weights and
    betas are invented to produce intuitive outputs. These have NO clinical
    provenance and must never be presented as validated.

Everything a user ever sees that derives from these numbers must carry the
illustrative / non-diagnostic framing.
"""

# ---------------------------------------------------------------------------
# Scoring shapes
# ---------------------------------------------------------------------------
# DIRECTIONAL_HIGH : higher value is better (penalty grows as z goes negative)
# DIRECTIONAL_LOW  : lower value is better, down to a floor (penalty grows as
#                    z goes positive; mild/zero penalty below midpoint)
# U_SHAPED         : both directions are worse (penalty grows with |z|)
# U_WIDE_LOW       : U-shaped, but the low side is widened/softened so that
#                    healthy-low values (e.g. athletic resting HR, healthy
#                    low-normal BP) are not unfairly penalized.
DIRECTIONAL_HIGH = "directional_high"
DIRECTIONAL_LOW = "directional_low"
U_SHAPED = "u_shaped"
U_WIDE_LOW = "u_wide_low"

# Markers whose bio-age contribution uses penalty MAGNITUDE (always-adds for
# deviation) rather than signed z. Per the approved "U-marker bio-age fix":
# a U-shaped marker has no anti-aging bonus for sitting at center, only the
# absence of penalty — so deviation in either direction adds apparent age.
PENALTY_BASED_BIOAGE = {U_SHAPED, U_WIDE_LOW}


class Marker:
    """One biomarker's full illustrative spec (one row of the review table)."""

    def __init__(self, key, name, unit, mid, hw, ref_range, shape, beta,
                 panel, rationale, caveats, illustrative=True):
        self.key = key            # stable id, fixes slot position in the vector
        self.name = name
        self.unit = unit
        self.mid = mid            # CONSTRUCTED midpoint
        self.hw = hw              # CONSTRUCTED half-width
        self.ref_range = ref_range  # representative interval (demo summary)
        self.shape = shape
        self.beta = beta          # CONSTRUCTED bio-age years/SD (or years/penalty)
        self.panel = panel
        self.rationale = rationale
        self.caveats = caveats
        self.illustrative = illustrative


# ---------------------------------------------------------------------------
# Panels (order is FIXED — it defines slot layout in the encrypted vector and
# must never change once frozen, or old ciphertexts/keys become incompatible).
# ---------------------------------------------------------------------------
PANELS = ["core", "metabolic", "lipid", "thyroid"]

# Panel "information weight" for the data-completeness/confidence score.
# Reflects how much each panel informs the flagship outputs (Core anchors
# bio-age and is always present; labs add progressively). NOT medical weight.
PANEL_INFO_WEIGHT = {
    "core": 0.40,
    "metabolic": 0.25,
    "lipid": 0.20,
    "thyroid": 0.15,
}

# Composite-score panel weights (how panels combine into the overall
# VitalScore). Renormalized client-side over PRESENT panels only.
PANEL_COMPOSITE_WEIGHT = {
    "core": 0.30,
    "metabolic": 0.30,
    "lipid": 0.25,
    "thyroid": 0.15,
}

# ---------------------------------------------------------------------------
# THE MARKER TABLE  (all mid/hw/beta/weight ILLUSTRATIVE; ref_range = demo
# summary of representative adult intervals)
# ---------------------------------------------------------------------------
# `weight` below is the marker's weight WITHIN its panel (pre-renormalization;
# weights within a panel sum to ~1 when all its markers are present).
MARKERS = [
    # ---- CORE (engineered + vitals; "age"/"sex" handled separately) --------
    Marker("bmi", "Body Mass Index", "kg/m^2", 21.7, 4.0, "18.5-25.0 healthy",
           U_SHAPED, 0.4, "core",
           "Range = standard WHO/CDC healthy band; mid/hw constructed.",
           "Doesn't separate muscle vs fat; invalid for athletes/elderly/"
           "pregnancy; ethnicity-adjusted cutoffs exist."),
    Marker("whtr", "Waist-to-Height Ratio", "ratio", 0.48, 0.05, "<0.5 lower-risk",
           DIRECTIONAL_LOW, 0.4, "core",
           "'0.5' cutoff widely cited; mid/hw constructed.",
           "Modest sex differences; less validated than BMI."),
    Marker("rhr", "Resting Heart Rate", "bpm", 62.0, 13.0, "~49-75 (athletes lower)",
           # APPROVED FIX: directional/lower-is-better to a floor, NOT strict U,
           # so endurance athletes are not penalized for bradycardia.
           DIRECTIONAL_LOW, 0.5, "core",
           "Lower-is-better to a physiological floor; mid/hw constructed.",
           "Very fitness-dependent; beta-blockers lower it; very low can be "
           "athletic OR pathological (floor guards the extreme)."),
    Marker("sbp", "Systolic Blood Pressure", "mmHg", 112.0, 13.0, "<120 normal (ACC/AHA)",
           # APPROVED FIX: U-shaped but low side widened (healthy low BP ok).
           U_WIDE_LOW, 0.8, "core",
           "'<120' = ACC/AHA normal; mid/hw constructed; low side widened.",
           "Single readings noisy; technique matters."),
    Marker("dbp", "Diastolic Blood Pressure", "mmHg", 74.0, 9.0, "<80 normal (ACC/AHA)",
           U_WIDE_LOW, 0.5, "core",
           "'<80' = ACC/AHA normal; mid/hw constructed; low side widened.",
           "Same as systolic."),
    Marker("sleep", "Sleep Duration", "hours", 7.5, 1.5, "7-9 h (NSF/CDC guidance)",
           U_SHAPED, 0.3, "core",
           "'7-9h' common public guidance; mid/hw constructed.",
           "Self-reported; quality != duration; age-dependent."),
    Marker("activity", "Activity Level", "0-1 scaled", 0.6, 0.4, "higher better (0-4 ordinal)",
           DIRECTIONAL_HIGH, 0.3, "core",
           "Self-defined ordinal mapped to 0-1; mid/hw constructed.",
           "Coarse, subjective; not a validated instrument."),

    # ---- METABOLIC ---------------------------------------------------------
    Marker("glucose", "Fasting Glucose", "mg/dL", 85.0, 15.0, "70-99 normal (ADA)",
           U_SHAPED, 0.7, "metabolic",
           "'70-99' = ADA fasting normal; mid/hw constructed.",
           "Requires fasting; single-point; hypoglycemia matters (U-shape)."),
    Marker("a1c", "Hemoglobin A1C", "%", 5.2, 0.5, "<5.7 normal (ADA)",
           DIRECTIONAL_LOW, 1.0, "metabolic",
           "'<5.7' = ADA; mid/hw constructed.",
           "Affected by anemia, Hb variants, RBC turnover."),
    Marker("insulin", "Fasting Insulin", "uIU/mL", 7.0, 4.0, "~2-12 (assay-dependent)",
           U_SHAPED, 0.3, "metabolic",
           "Assay-dependent range; mid/hw constructed.",
           "Highly assay-dependent; fasting required. OPTIONAL marker."),

    # ---- LIPID -------------------------------------------------------------
    Marker("hdl", "HDL Cholesterol", "mg/dL", 58.0, 18.0, ">40(M)/>50(F) desirable",
           DIRECTIONAL_HIGH, 0.5, "lipid",
           "NCEP/ATP-style desirable thresholds; mid/hw constructed.",
           "SEX-DEPENDENT (V1 uses unified); very high HDL not always good."),
    Marker("ldl", "LDL Cholesterol", "mg/dL", 90.0, 35.0, "<100 optimal (NCEP)",
           DIRECTIONAL_LOW, 0.5, "lipid",
           "'<100 optimal' = NCEP; mid/hw constructed.",
           "Risk-context dependent; statin targets lower for high-risk."),
    Marker("tg", "Triglycerides", "mg/dL", 90.0, 50.0, "<150 normal (NCEP)",
           DIRECTIONAL_LOW, 0.5, "lipid",
           "'<150' = NCEP; mid/hw constructed.",
           "Very fasting-sensitive; day-to-day variable."),
    Marker("tc", "Total Cholesterol", "mg/dL", 175.0, 40.0, "<200 desirable (NCEP)",
           U_SHAPED, 0.3, "lipid",
           "'<200' = NCEP; mid/hw constructed; very low also flagged (U).",
           "Crude alone; HDL/LDL split more informative."),

    # ---- THYROID -----------------------------------------------------------
    Marker("tsh", "TSH", "mIU/L", 1.8, 1.3, "~0.4-4.0 (common lab)",
           U_SHAPED, 0.3, "thyroid",
           "'0.4-4.0' common adult lab range; mid/hw constructed.",
           "Range debated (some 0.4-2.5); age/pregnancy differ; inverse to "
           "thyroid hormone."),
    Marker("ft3", "Free T3", "pg/mL", 3.3, 0.7, "~2.3-4.2 (lab-dependent)",
           U_SHAPED, 0.2, "thyroid",
           "Representative lab range; mid/hw constructed.",
           "Assay-dependent units; less standardized."),
    Marker("ft4", "Free T4", "ng/dL", 1.2, 0.4, "~0.8-1.8 (lab-dependent)",
           U_SHAPED, 0.2, "thyroid",
           "Representative lab range; mid/hw constructed.",
           "Assay-dependent; interpret with TSH."),
]

MARKER_BY_KEY = {m.key: m for m in MARKERS}

# Markers that are OPTIONAL even when their panel is otherwise provided.
OPTIONAL_MARKERS = {"whtr", "insulin"}

# ---------------------------------------------------------------------------
# Global scoring parameters (ILLUSTRATIVE)
# ---------------------------------------------------------------------------
Z_CLAMP = 3.0            # clamp standardized deviation to [-3, +3] (client-side);
                         # bounds the Chebyshev domain on the server.
FOLLOWUP_Z = 2.0         # |z| > 2 -> conservative "discuss with provider" nudge.
BIOAGE_MAX_REDUCTION = 8.0   # APPROVED client-side cap: favorable floor (-8 yr).
BIOAGE_MAX_INCREASE = 10.0   # APPROVED client-side cap: unfavorable ceiling (+10 yr).
                             # Bio-age is the ENGAGING signal; severe outliers are
                             # carried by the follow-up system, not by bio-age.

# Penalty curve: smooth, ~0 near z=0, rising with deviation. A scaled
# quadratic in z (this is the cleartext reference; the server approximates
# the equivalent with a low-degree Chebyshev polynomial on [-Z_CLAMP, Z_CLAMP]).
# PENALTY_SCALE maps a full-clamp deviation (|z|=3) to a meaningful penalty.
PENALTY_SCALE = 100.0 / (Z_CLAMP * Z_CLAMP)   # so |z|=3 -> 100 penalty units

# Directional softening: how much of the "good direction" still counts.
# For DIRECTIONAL_LOW, deviations below midpoint (good) are softened toward 0
# until a floor; for DIRECTIONAL_HIGH, deviations above midpoint (good) softened.
DIRECTIONAL_GOOD_SIDE_FACTOR = 0.0   # good direction contributes no penalty
RHR_LOW_FLOOR_Z = -2.0   # below this z, athletic-low RHR starts to matter again
UWIDE_LOW_FACTOR = 0.35  # low-side penalty multiplier for U_WIDE_LOW markers


def disclaimer() -> str:
    return ("Illustrative wellness estimate. Not a clinical age measurement. "
            "Not a medical device; not for clinical use. Educational only.")


# ---------------------------------------------------------------------------
# APPROVED DESIGN CONSTRAINTS (recorded for Stage 7 client/UI implementation)
# ---------------------------------------------------------------------------
# DC-1 (headline qualification): When one or more follow-up indicators are
#   active, the dashboard MUST qualify the composite/biological-age headline
#   (e.g. "Good — 2 items to review") rather than letting a positive headline
#   visually override the warning. The composite and follow-up systems are
#   independent channels and must read as one coherent story. This is a
#   CLIENT-SIDE presentation rule and adds no encrypted depth.
#
# DC-2 (score floor — PENDING APPROVAL): worst-case system scores currently
#   clamp to exactly 0.0, which reads as alarmist for a non-diagnostic tool.
#   Proposed: a client-side floor mapping the worst realistic profile to
#   ~25-35 ("needs attention") instead of 0. Decision affects the displayed
#   score shape (post-decrypt, circuit-free). Not yet frozen.
DASHBOARD_FLAG_QUALIFIES_HEADLINE = True  # DC-1, approved
