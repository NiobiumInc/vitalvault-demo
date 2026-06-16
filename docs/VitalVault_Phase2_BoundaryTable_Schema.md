# VitalVault — Phase 2 Tier-Boundary Table (Schema Only)

**Status:** Design target, not implemented. Phase 1 (direction-aware labels, two-green + neutral visual, "Healthy" rename, provisional amber) is live. This document defines the *structure* the source-checked accuracy pass will fill in to move from the provisional 3-tier `z`-based color system to a 5-tier, clinically-anchored status hierarchy.

---

## Why this exists

The current tier engine (`tierOf(marker, z)`) derives color/label/badge from a marker's `z`-score and `shape`. That is provisional: a uniform `z` cutoff misfires against real reference ranges (verified — LDL amber triggers ~146 while normal extends to ~160; glucose amber ~109 while normal extends to ~125). Correct status coloring requires **explicit, per-marker, source-checked boundaries** rather than `z`-math.

This table is the single data structure that will drive the final system. Because `tierOf` already centralizes all color/label/badge logic, Phase 2 is: (1) author this table, (2) swap `tierOf`'s internals from `z`-thresholds to boundary lookups. Bar, badge, labels, and status all inherit automatically.

---

## The five-tier status hierarchy (target)

| Tier | Color | Meaning | Boundary source |
|---|---|---|---|
| Optimal | Dark green | Longevity-favorable sub-zone | Longevity-medicine convention (aspirational overlay — see caution) |
| Healthy / Near Optimal | Light green | Within normal reference range, not peak | Clinical reference range |
| Borderline | Yellow | At the edge of the normal range | Clinical reference range |
| Elevated / Low | Orange | Outside the normal reference range | Clinical reference range |
| Clearly Outside Range | Red | Substantially outside reference range | Clinical reference range |

**Governing principle:** healthy values stay green. Caution colors (yellow/orange/red) are reserved for values genuinely at or beyond the reference-range edge — never for "healthy but not optimal."

---

## Per-marker schema

Each marker gets a `boundaries` object. Boundaries are expressed in the marker's **native units** (not `z`), so they're directly source-checkable against clinical references.

### Directional markers (lower-is-better, e.g. LDL, triglycerides, hs-CRP)

Ascending cut-points; everything below the first is Optimal, everything above the last is Red:

```
boundaries: {
  direction: "lower",           // optimal is the LOW end
  optimalMax:   <value>,        // <= this  -> Optimal      (dark green)
  healthyMax:   <value>,        // <= this  -> Healthy      (light green)
  borderlineMax:<value>,        // <= this  -> Borderline   (yellow)
  elevatedMax:  <value>,        // <= this  -> Elevated     (orange)
                                // >  this  -> Outside Range (red)
  source: "<citation>",         // e.g. "NCEP ATP III (LDL)"
  optimalSource: "<citation>"   // separate cite for the optimal line (see caution)
}
```

Example shape (illustrative values — to be source-checked, NOT final):
```
ldl: { direction:"lower", optimalMax:80, healthyMax:115, borderlineMax:160,
       elevatedMax:190, source:"NCEP ATP III", optimalSource:"longevity-medicine convention" }
```

### Directional markers (higher-is-better, e.g. HDL)

Descending logic — optimal is the HIGH end. Mirror of the above:

```
boundaries: {
  direction: "higher",          // optimal is the HIGH end
  optimalMin:   <value>,        // >= this -> Optimal
  healthyMin:   <value>,        // >= this -> Healthy
  borderlineMin:<value>,        // >= this -> Borderline
  elevatedMin:  <value>,        // >= this -> Elevated (here "Low")
                                // <  this -> Outside Range (red)
  source, optimalSource
}
```
Note: for higher-is-better, the amber/red end is the LOW side, so the orange tier label reads "Low" and red is "clearly low." HDL also needs the documented "very high isn't extra-protective" exception (an optional soft cap at the top).

### Middle-best markers (e.g. BMI, blood pressure, glucose, thyroid)

Two-sided: a central optimal band with symmetric (or asymmetric) tiers on each side. Needs up to **eight** cut-points (four per side):

```
boundaries: {
  direction: "middle",
  // ascending: redLo < elevatedLo < borderlineLo < healthyLo < [OPTIMAL] < healthyHi < borderlineHi < elevatedHi < redHi
  optimalLo, optimalHi,         // inside [optimalLo, optimalHi] -> Optimal
  healthyLo, healthyHi,         // inside healthy band but outside optimal -> Healthy
  borderlineLo, borderlineHi,   // -> Borderline (yellow)
  elevatedLo, elevatedHi,       // -> Elevated/Low (orange)
                                // beyond elevatedLo/elevatedHi -> Outside Range (red)
  source, optimalSource
}
```
Sides may be asymmetric (e.g. for BMI the low-side and high-side cut-points differ). Where a side has no meaningful "outside range" (rare), that bound may be omitted and the tier clamps.

---

## `tierOf` Phase 2 behavior (pseudocode, not implemented)

```
function tierOf(marker, value):
    b = marker.boundaries
    if b.direction == "lower":
        if value <= b.optimalMax:    return "optimal"
        if value <= b.healthyMax:    return "healthy"
        if value <= b.borderlineMax: return "borderline"
        if value <= b.elevatedMax:   return "elevated"
        return "outside"
    if b.direction == "higher":
        ... mirror with *Min and >= ...
    if b.direction == "middle":
        ... map value into the nearest side's band ...
```

The bar's per-segment coloring, the anchor labels, the badge, and the marker status all continue to read from `tierOf` — so they remain consistent by construction, exactly as in Phase 1.

---

## Boundary sourcing notes (for the accuracy pass)

- **Anchor the four clinical boundaries** (healthy / borderline / elevated / outside) to recognized references where they exist: e.g. NCEP/ACC-AHA for lipids, ADA for glucose/A1C, standard assay reference ranges for thyroid/liver/kidney, AHA/CDC strata for hs-CRP. Record the citation per marker in `source`.
- **The optimal boundary is different — treat it honestly.** "Optimal" is a longevity-medicine value judgment, *not* a clinical reference-range fact. Reference ranges define normal/abnormal; they do not define optimal. So `optimalSource` must cite the stated longevity convention used, and the UI/education should present the optimal line as an aspirational overlay, not implied clinical consensus.
- **Sex- and age-specific boundaries** will be required for some markers (creatinine, testosterone, HDL's sex difference, etc.). The schema should allow `boundaries` to be either a single object or `{ male:{...}, female:{...} }` — this dovetails with the deferred sex-specific scoring work (Kidney/Hormones).
- **Units must match the marker's native unit** exactly (the same unit shown in the UI), so boundaries are directly checkable and no conversion logic creeps in.
- **Provisional → final:** until a marker's `boundaries` object exists and is source-checked, that marker falls back to the current provisional `z`-based 3-tier behavior. Migration can be per-marker (a marker with `boundaries` uses the 5-tier path; one without uses the provisional path), so the pass can land system-by-system like the education content did.

---

## Scope reminder

This is presentation/interpretation only. It does **not** change scoring, marker midpoints/half-widths/shapes/betas, panel assignments, the Python harness, or the FHE pipeline. The boundary table drives *color and status labeling*; the bio-age and system-score math remain exactly as verified.

