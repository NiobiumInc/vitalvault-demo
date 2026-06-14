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
"""VitalVault Stage-3 STRESS-TAIL profiles.

ILLUSTRATIVE / DEMO-ONLY. NOT A MEDICAL DEVICE. NOT FOR CLINICAL USE.

The random cohort is healthy-skewed and does not exercise the unhealthy tail
(the +10 bio-age cap and the score floor went untouched). These hand-built
profiles deliberately push the edges to confirm the model degrades gracefully
rather than producing nonsense or alarmist output. Values are intentionally
extreme for testing and are NOT representative of typical users.
"""
from . import personas as P

STRESS = {
    "near_clamp_multi": {
        "label": "Multiple markers near the +/-3 clamp (cap stress)",
        "age": 55, "sex": "M",
        "height_cm": 175, "weight_kg": 110, "waist_cm": 120,  # BMI ~35.9
        "activity_ordinal": 0,
        "rhr": 95, "sbp": 158, "dbp": 102, "sleep": 4.5,
        "glucose": 145, "a1c": 7.2, "insulin": 24,
        "hdl": 28, "ldl": 195, "tg": 320, "tc": 290,
        "tsh": 6.0, "ft3": 2.2, "ft4": 0.7,
    },
    "many_flags": {
        "label": "Several follow-up flags simultaneously",
        "age": 60, "sex": "F",
        "height_cm": 160, "weight_kg": 95, "waist_cm": 110,  # BMI ~37
        "activity_ordinal": 0,
        "rhr": 88, "sbp": 150, "dbp": 95, "sleep": 5.0,
        "glucose": 138, "a1c": 6.8,
        "hdl": 30, "ldl": 180, "tg": 280, "tc": 270,
    },
    "minimal_data": {
        "label": "Minimal data (Limited confidence stress)",
        "age": 45, "sex": "M",
        "height_cm": 180, "weight_kg": 82,  # no waist
        # no activity, no labs, only the always-required vitals subset
        "rhr": 70, "sbp": 120, "dbp": 78, "sleep": 7.0,
    },
    "metabolic_extreme": {
        "label": "Significantly elevated metabolic markers",
        "age": 52, "sex": "M",
        "height_cm": 178, "weight_kg": 96, "waist_cm": 108,
        "activity_ordinal": 1,
        "rhr": 74, "sbp": 124, "dbp": 80, "sleep": 6.5,
        "glucose": 160, "a1c": 8.0, "insulin": 28,
        "hdl": 48, "ldl": 115, "tg": 200, "tc": 205,
        # no thyroid
    },
    "thyroid_extreme_low": {
        "label": "Significantly abnormal thyroid (very high TSH, low T3/T4)",
        "age": 38, "sex": "F",
        "height_cm": 163, "weight_kg": 64, "waist_cm": 74,
        "activity_ordinal": 2,
        "rhr": 58, "sbp": 112, "dbp": 72, "sleep": 7.5,
        "glucose": 90, "a1c": 5.3,
        "hdl": 58, "ldl": 95, "tg": 95, "tc": 175,
        "tsh": 9.5, "ft3": 1.9, "ft4": 0.6,
    },
    "thyroid_extreme_high": {
        "label": "Significantly abnormal thyroid (suppressed TSH, high T3/T4)",
        "age": 42, "sex": "F",
        "height_cm": 165, "weight_kg": 58, "waist_cm": 70,
        "activity_ordinal": 3,
        "rhr": 92, "sbp": 122, "dbp": 70, "sleep": 6.0,
        "tsh": 0.05, "ft3": 5.2, "ft4": 2.4,
        # core + thyroid only
    },
}


def engineered_stress():
    return {name: P.engineer(raw) for name, raw in STRESS.items()}
