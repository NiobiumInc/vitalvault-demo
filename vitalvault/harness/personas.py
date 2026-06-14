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
"""VitalVault Stage-3 personas + client-side feature engineering.

ILLUSTRATIVE / DEMO-ONLY. NOT A MEDICAL DEVICE. NOT FOR CLINICAL USE.

Personas are raw inputs as a user would enter them (height/weight/waist in
real units, activity as a 0-4 ordinal). `engineer()` performs the CLIENT-SIDE
transforms (the ones that need division/branching and must NOT be in the
encrypted circuit): BMI, waist-to-height ratio, activity scaling. The result
is the fixed-key profile dict the scoring engine consumes.

Each persona also demonstrates OPTIONAL-FIELD handling: some omit panels or
individual optional markers entirely (value left absent), exercising the
presence-mask path without changing the circuit.
"""

# ---- client-side feature engineering --------------------------------------
def engineer(raw):
    """[CLIENT] derive BMI, WHtR, activity scalar from raw inputs.

    Division/branching live here in cleartext on the user's own data — this
    leaks nothing new and keeps these ops out of the encrypted circuit.
    """
    p = dict(raw)
    h_m = raw["height_cm"] / 100.0
    p["bmi"] = round(raw["weight_kg"] / (h_m * h_m), 2)
    if raw.get("waist_cm") is not None:
        p["whtr"] = round(raw["waist_cm"] / raw["height_cm"], 4)
    else:
        p["whtr"] = None  # optional marker absent
    # activity 0-4 ordinal -> 0..1 scalar
    if raw.get("activity_ordinal") is not None:
        p["activity"] = round(raw["activity_ordinal"] / 4.0, 3)
    else:
        p["activity"] = None
    return p


# ---- the five review personas (raw inputs) --------------------------------
# Keys absent from a persona = that marker/panel not provided by the user.
PERSONAS = {
    "healthy_college_student": {
        "label": "Healthy college student (full Core+Metabolic+Lipid, no Thyroid)",
        "age": 20, "sex": "F",
        "height_cm": 168, "weight_kg": 62, "waist_cm": 74,
        "activity_ordinal": 3,
        "rhr": 60, "sbp": 115, "dbp": 75, "sleep": 8.0,
        "glucose": 88, "a1c": 5.1, "insulin": 6,
        "hdl": 60, "ldl": 88, "tg": 80, "tc": 165,
        # thyroid omitted entirely
    },
    "sedentary_middle_aged": {
        "label": "Sedentary middle-aged adult (all four panels)",
        "age": 48, "sex": "M",
        "height_cm": 178, "weight_kg": 92, "waist_cm": 102,
        "activity_ordinal": 1,
        "rhr": 78, "sbp": 128, "dbp": 84, "sleep": 6.0,
        "glucose": 102, "a1c": 5.8, "insulin": 14,
        "hdl": 42, "ldl": 138, "tg": 180, "tc": 215,
        "tsh": 2.2, "ft3": 3.1, "ft4": 1.1,
    },
    "endurance_athlete": {
        "label": "Endurance athlete (the RHR/BP stress test)",
        "age": 35, "sex": "M",
        "height_cm": 180, "weight_kg": 70, "waist_cm": 80,
        "activity_ordinal": 4,
        "rhr": 42, "sbp": 108, "dbp": 66, "sleep": 8.0,
        "glucose": 84, "a1c": 5.0, "insulin": 4,
        "hdl": 72, "ldl": 85, "tg": 70, "tc": 170,
        "tsh": 1.6, "ft3": 3.4, "ft4": 1.3,
    },
    "elevated_a1c": {
        "label": "User with elevated A1C (Core+Metabolic+Lipid, no Thyroid)",
        "age": 50, "sex": "F",
        "height_cm": 165, "weight_kg": 78, "waist_cm": 90,
        "activity_ordinal": 2,
        "rhr": 72, "sbp": 122, "dbp": 80, "sleep": 7.0,
        "glucose": 120, "a1c": 6.2,  # insulin omitted (optional)
        "hdl": 50, "ldl": 110, "tg": 140, "tc": 195,
    },
    "thyroid_abnormal": {
        "label": "User with thyroid abnormalities (Core+Thyroid only, no Metabolic/Lipid)",
        "age": 40, "sex": "F",
        "height_cm": 162, "weight_kg": 60, "waist_cm": 72,
        "activity_ordinal": 2,
        "rhr": 64, "sbp": 114, "dbp": 74, "sleep": 7.0,
        # metabolic + lipid omitted entirely
        "tsh": 6.5, "ft3": 2.4, "ft4": 0.7,
    },
    "core_only_basic": {
        "label": "Core-only user (tests Limited/Basic confidence band)",
        "age": 30, "sex": "M",
        "height_cm": 175, "weight_kg": 75, "waist_cm": 85,
        "activity_ordinal": 2,
        "rhr": 66, "sbp": 118, "dbp": 76, "sleep": 7.5,
        # no labs at all
    },
}


def engineered_personas():
    """All personas after client-side engineering, ready for scoring."""
    return {name: engineer(raw) for name, raw in PERSONAS.items()}
