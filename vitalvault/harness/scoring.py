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
"""VitalVault Stage-3 cleartext scoring engine (the GROUND TRUTH).

ILLUSTRATIVE / DEMO-ONLY. NOT A MEDICAL DEVICE. NOT FOR CLINICAL USE.

This is the reference implementation the encrypted pipeline is verified
against (the package's "get it working in plaintext first" step). It is
deliberately split by trust boundary so the eventual client/server division
is obvious:

  CLIENT-SIDE (cleartext, on the user's own data — leaks nothing new):
    - unit handling / feature engineering (BMI, WHtR done by the caller)
    - standardization  z = (x - mid) / hw   and clamp to [-Z_CLAMP, Z_CLAMP]
    - presence masking + within-panel weight renormalization
    - confidence/completeness score (from the mask only)
    - bio-age: add ChronoAge, apply the favorable-delta CAP
    - banding / interpretation / disclaimers

  SERVER-SIDE (this is the part that becomes the encrypted CKKS circuit):
    - per-marker penalty(z)            [Chebyshev on the server]
    - weighted system penalties -> scores
    - bio-age delta = weighted sum of (signed z | penalty) terms
    - per-term contributions (attribution)
    - follow-up indicators (|z| > FOLLOWUP_Z)

The functions are tagged in their docstrings with [CLIENT] or [SERVER] so the
boundary is unambiguous when we port to .nb in Stage 7.
"""

from . import constants as C


# ===========================================================================
# [CLIENT] standardization
# ===========================================================================
def standardize(marker_key, value):
    """[CLIENT] z = (value - mid) / hw, clamped to [-Z_CLAMP, Z_CLAMP]."""
    m = C.MARKER_BY_KEY[marker_key]
    z = (value - m.mid) / m.hw
    return max(-C.Z_CLAMP, min(C.Z_CLAMP, z))


# ===========================================================================
# [SERVER] penalty shapes (this becomes the Chebyshev approximation)
# ===========================================================================
def penalty(marker_key, z):
    """[SERVER] Non-negative penalty for a standardized value, BRANCH-FREE.

    Each shape is a smooth closure of {x, abs(x), consts} so it can be fitted
    by a single Chebyshev interpolant on [-Z_CLAMP, Z_CLAMP] and evaluated on
    the server with no data-dependent branch. These exact forms are mirrored
    in server.nb so the encrypted output matches this ground truth.

    Building blocks (branch-free one-sided ramps):
      pos(x) = (x + |x|)/2   == max(0, x)
      neg(x) = (x - |x|)/2   == min(0, x)
    """
    m = C.MARKER_BY_KEY[marker_key]
    s = C.PENALTY_SCALE
    ax = abs(z)
    pos = (z + ax) / 2.0   # max(0, z)
    neg = (z - ax) / 2.0   # min(0, z)

    if m.shape == C.U_SHAPED:
        return s * z * z

    if m.shape == C.U_WIDE_LOW:
        # full penalty on the high side, softened on the low side
        return s * pos * pos + s * C.UWIDE_LOW_FACTOR * neg * neg

    if m.shape == C.DIRECTIONAL_HIGH:
        # higher is better: penalize only the low side (z<0)
        return s * neg * neg

    if m.shape == C.DIRECTIONAL_LOW:
        if marker_key == "rhr":
            # lower is better to a floor: full penalty on the high side; on the
            # low side, no penalty until below the athletic floor RHR_LOW_FLOOR_Z,
            # then re-engage. below_floor = min(0, z - floor) (floor is negative).
            below = (z - C.RHR_LOW_FLOOR_Z)
            below_neg = (below - abs(below)) / 2.0   # min(0, z - floor)
            return s * pos * pos + s * below_neg * below_neg
        # generic lower-is-better: penalize only the high side
        return s * pos * pos

    raise ValueError("unknown shape %r" % m.shape)


# ===========================================================================
# [CLIENT] presence masking + weight renormalization
# ===========================================================================
def present_markers(profile):
    """[CLIENT] keys the user actually supplied (value is not None)."""
    return [m.key for m in C.MARKERS if profile.get(m.key) is not None]


def panel_present_markers(profile, panel):
    return [k for k in present_markers(profile)
            if C.MARKER_BY_KEY[k].panel == panel]


def renormalized_weights(profile, panel):
    """[CLIENT] within-panel weights over PRESENT markers, renormalized to 1.

    `weight` lives implicitly as equal-within-panel here; we derive per-marker
    base weight from the panel's marker count so the table stays simple, then
    renormalize over present markers. (A future version can carry explicit
    per-marker weights; equal-weight is the honest V1 default.)
    """
    keys = panel_present_markers(profile, panel)
    if not keys:
        return {}
    w = 1.0 / len(keys)
    return {k: w for k in keys}


def present_panels(profile):
    return [p for p in C.PANELS if panel_present_markers(profile, p)]


# ===========================================================================
# [SERVER] system scores + [CLIENT] composite
# ===========================================================================
def system_score(profile, panel):
    """[SERVER] SystemScore = 100 - sum(weight * penalty(z)), clamped [0,100]."""
    weights = renormalized_weights(profile, panel)
    if not weights:
        return None  # panel absent
    total_penalty = 0.0
    for k, w in weights.items():
        z = standardize(k, profile[k])
        total_penalty += w * penalty(k, z)
    return max(0.0, min(100.0, 100.0 - total_penalty))


def composite_score(profile):
    """[CLIENT] weighted blend of present system scores (weights renormalized)."""
    panels = present_panels(profile)
    scores = {p: system_score(profile, p) for p in panels}
    wsum = sum(C.PANEL_COMPOSITE_WEIGHT[p] for p in panels)
    if wsum == 0:
        return None, scores
    comp = sum(C.PANEL_COMPOSITE_WEIGHT[p] * scores[p] for p in panels) / wsum
    return max(0.0, min(100.0, comp)), scores


# ===========================================================================
# [SERVER] bio-age delta + per-term contributions ; [CLIENT] add age + cap
# ===========================================================================
def bioage_terms(profile):
    """[SERVER] per-marker bio-age contribution (years) and the signed delta.

    Symmetric model: favorable directional markers contribute NEGATIVE years
    (younger), unfavorable POSITIVE. U-shaped markers use penalty MAGNITUDE
    (always >= 0, i.e. deviation only adds apparent age) per the approved fix,
    so score and bio-age never contradict.
    """
    terms = {}
    for k in present_markers(profile):
        m = C.MARKER_BY_KEY[k]
        z = standardize(k, profile[k])
        if m.shape in C.PENALTY_BASED_BIOAGE:
            # penalty magnitude -> years; normalize penalty (0..~100) to ~0..3 SD
            pen = penalty(k, z)
            yrs = m.beta * (pen / C.PENALTY_SCALE) ** 0.5  # ~ beta*|effective z|
            terms[k] = +yrs  # only ever adds age
        else:
            # directional: signed so good direction subtracts age.
            # Sign convention: positive z = "worse" should ADD age.
            if m.shape == C.DIRECTIONAL_HIGH:
                signed = -z  # high (good) -> negative -> subtract age
            else:  # DIRECTIONAL_LOW
                signed = +z  # high (bad) -> positive -> add age
            terms[k] = m.beta * signed
    return terms


def biological_age(profile):
    """[CLIENT] ChronoAge + capped(sum of [SERVER] bio-age terms)."""
    chrono = profile["age"]
    terms = bioage_terms(profile)
    delta = sum(terms.values())
    # APPROVED client-side caps (add no encrypted depth):
    delta = max(-C.BIOAGE_MAX_REDUCTION, min(C.BIOAGE_MAX_INCREASE, delta))
    return chrono + delta, delta, terms


# ===========================================================================
# [SERVER] follow-up indicators
# ===========================================================================
def followups(profile):
    """[SERVER] markers with |z| > FOLLOWUP_Z -> conservative nudge.

    Encrypted version uses the iterated-squaring soft indicator; cleartext
    reference uses the hard threshold. Output is a non-diagnostic nudge.
    """
    out = []
    for k in present_markers(profile):
        z = standardize(k, profile[k])
        if abs(z) > C.FOLLOWUP_Z:
            out.append((k, round(z, 2)))
    return out


# ===========================================================================
# [CLIENT] data-completeness / confidence score (from the mask ONLY)
# ===========================================================================
def confidence(profile):
    """[CLIENT] completeness in [0,1] + band. Data completeness, NOT accuracy."""
    score = 0.0
    for p in C.PANELS:
        panel_keys = [m.key for m in C.MARKERS if m.panel == p]
        # exclude purely-optional markers from the "fullness" denominator so a
        # user isn't penalized for skipping an optional lab
        core_keys = [k for k in panel_keys if k not in C.OPTIONAL_MARKERS]
        present = [k for k in core_keys if profile.get(k) is not None]
        frac = (len(present) / len(core_keys)) if core_keys else 0.0
        score += C.PANEL_INFO_WEIGHT[p] * frac
    score = max(0.0, min(1.0, score))
    if score >= 0.85:
        band = "High"
    elif score >= 0.6:
        band = "Moderate"
    elif score >= 0.35:
        band = "Basic"
    else:
        band = "Limited"
    return score, band


# ===========================================================================
# [CLIENT] display floor — keep raw score for testing, soften UI floor
# ===========================================================================
DISPLAY_FLOOR = 30.0   # extreme low raw scores map to ~30, never hard 0.0


def display_score(raw):
    """[CLIENT] map a raw [0,100] system score to a calm display value.

    Post-decrypt, circuit-free. Linearly compresses [0,100] into
    [DISPLAY_FLOOR, 100] so a worst-case profile reads "Needs attention" near
    30 rather than an alarmist 0.0. Ordering and relative gaps are preserved;
    the raw score is retained separately for testing/verification.
    """
    if raw is None:
        return None
    return DISPLAY_FLOOR + (100.0 - DISPLAY_FLOOR) * (raw / 100.0)


# ===========================================================================
# [CLIENT] banding for display
# ===========================================================================
def band_score(value):
    """[CLIENT] map a DISPLAY score to a calm, tolerant band (noise-safe).

    Bands are defined on the displayed (floored) scale. Lowest band is
    "Worth reviewing" — deliberately calm, never clinical/"failure".
    """
    if value is None:
        return "n/a"
    if value >= 80:
        return "Good"
    if value >= 60:
        return "Moderate"
    return "Worth reviewing"


# ===========================================================================
# Top-level: full cleartext report (the reference output)
# ===========================================================================
def evaluate(profile):
    """Run the entire cleartext model. Returns the reference report dict."""
    comp, sys_scores = composite_score(profile)
    bioage, bio_delta, bio_terms = biological_age(profile)
    conf, conf_band = confidence(profile)
    flags = followups(profile)
    # raw scores drive verification; displayed scores drive the UI + bands
    disp_sys = {p: display_score(s) for p, s in sys_scores.items()}
    disp_comp = display_score(comp)
    return {
        "system_scores_raw": {p: (round(s, 3) if s is not None else None)
                              for p, s in sys_scores.items()},
        "system_scores": {p: (round(s, 3) if s is not None else None)
                          for p, s in disp_sys.items()},
        "system_bands": {p: band_score(s) for p, s in disp_sys.items()},
        "composite_raw": round(comp, 3) if comp is not None else None,
        "composite": round(disp_comp, 3) if disp_comp is not None else None,
        "composite_band": band_score(disp_comp),
        "chrono_age": profile["age"],
        "biological_age": round(bioage, 2),
        "bioage_delta": round(bio_delta, 2),
        "bioage_terms": {k: round(v, 3) for k, v in bio_terms.items()},
        "confidence": round(conf, 3),
        "confidence_band": conf_band,
        "followups": flags,
        "present_panels": present_panels(profile),
        "disclaimer": C.disclaimer(),
    }
