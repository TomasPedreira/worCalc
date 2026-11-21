# Map projection corrections

Applied 19 October 2026 after the user authorized the full map-pack rollout.
Boundary: integration (offline catalog, native projection and saved-plan consumers).

All 99 maps have an explicit alignment entry in `native/assets/catalog.json`.
The original game-exported corners and locations remain in that file for audit;
the Rust engine resolves `map_alignments` exactly once, before exposing maps,
locations or calculations. The manifest covers the updated catalog.

| Battlefield | Maps | Changed projection | Unchanged |
| --- | ---: | ---: | ---: |
| Antietam | 31 | 30 | 1 |
| Drill Camp | 35 | 18 | 17 |
| Harpers Ferry | 19 | 8 | 11 |
| South Mountain | 14 | 4 | 10 |
| Total | 99 | 60 | 39 |

Several changes outside Antietam remove only small cross-axis corner rounding
errors. An already neutral projection is left byte-for-byte unchanged, with
coordinate revision zero. Changed maps use coordinate revision one.

## Alignment policy and its limits

* Miller's Cornfield retains the building-derived similarity used in the terrain
  trial: rotation **3.6640287500 degrees**, scale **0.9966191038**,
  `a=0.9945819506168841`, `z=0.06368972860255215`,
  `tx=64.7161502102499`, `ty=-55.14150220355123`.
* Nicodemus Hill retains the user-verified compass-angle/building fit: rotation
  **3.9517783291 degrees**, scale **1.0011130277**,
  `a=0.9987327872264953`, `z=0.06899357875718132`,
  `tx=68.56048969982542`, `ty=-68.77829190522698`.
* Other Antietam cropped maps rotate about their image centre to the candidate
  battlefield heading **-50 degrees**. Their angle is calculated from each
  original projection; Miller's 3.66-degree value is not copied to other maps.
  Scale and centre are retained. The -50-degree direction comes from Antietam's
  `UI.CompassBias` and is supported by the Miller/Nicodemus trials. The artwork
  generator's use of this field has **not** been established.
* The remaining battlefield images use neutral world axes. Their source corners
  sometimes contain cross-axis skew. This is removed while retaining the
  projected X/Y scale and the world position of the image centre. A rigid
  rotation would preserve the skew and can worsen landmark placement.
* Neutral full-map views, including the independently checked **CSA Drill Camp**,
  receive the identity transform. No subpixel diagnostic roof fit is applied to
  CSA Drill Camp. Antietam Onslaught's zero-heading definition is also retained.

The rollout beyond Miller, Nicodemus and the checked Drill Camp/Outskirts
landmarks is an **axis-normalization policy**, not independent surveying of all
99 artworks. It cannot establish that every crop has the right translation or
scale. Remaining maps still need spot checks against recognizable in-game
positions. Different artwork errors can require later per-map overrides.

A subsequent before/after terrain-overlay audit covered all 60 changed entries:
43 have supportive overlay evidence and 17 remain inconclusive. This includes
all 30 changed Antietam entries and 13 of the additional corrections. Most of
the inconclusive changes are below two native image pixels; Picket Patrol 01 is
the larger unresolved case. See `docs/map-alignment-verification.md` for the
method, controls, limits and complete evidence location.

Outskirts (`map-68`, also sharing the definition with `map-72`) illustrates the
skew case: its X vector contains 99 metres of unwanted world Y across the image,
while its Y vector is vertical. Two independently identified Miller-model roofs
improve from about 52 and 20 native pixels of error to below 4.5 pixels after
neutral-axis rectification. A rigid 5.38-degree rotation fails those checks.
The roof centres come from placed CGF geometry and image components, not cannon
positions. Research measurements are in `tmp/gun-coordinate-audit/`; durable
regression values and their provenance are in
`native/core/tests/fixtures/alignment.json`.

## One projection for terrain and markers

For an original pixel-to-world matrix `A`, origin `O`, and image correction
`p_new = B p_old + t`, the corrected projection is:

```text
A_new = A inverse(B)
O_new = O - A_new t
```

Thus a corrected marker and every point on its flight path resolve to the same
world position as the original world-backed feature. Image clicks use the
corrected projection when sampling terrain. All static location kinds are
reprojected, including batteries, objectives, spawns and guns. World XYZ values,
terrain files, launch height and barrel angle offsets are unchanged.

For neutral-axis rectification, the pixel correction is affine and can contain
shear; the formula above still applies. The implementation rejects singular or
unsupported corrections and rejects resolving an already corrected catalog.

## Saved plans and observations

New calculation results and recorded impacts carry the map's coordinate revision.
Old observations remain stored, but observations from a different revision are
excluded from empirical estimates. Legacy CSA Drill Camp observations remain
eligible because its projection stays at revision zero.

On loading or importing an old plan for a changed map:

* User-placed picture points retain their image coordinates.
* Guns exactly matching an old default spawn move to its corrected position,
  provided that position remains inside the image.
* Previous geometry and firing settings are preserved in `alignment_history`.
  They are included in JSON exports, but their old firing cards are not shown
  as current solutions.
* The interface reports how many firing settings need recalculation. Opening
  such a target preserves ammunition preferences and notes, leaves elevation
  and fuze blank, and requires a fresh native solution before saving.
* Migration is persisted through the existing durable store, retaining the
  previous-file backup. A failed migration write prevents editing and does not
  overwrite the original document.

Plans on unchanged maps retain their original settings. Reopening or importing
an already migrated plan does not apply the correction again.

## Verification

Focused Rust checks cover all 99 entries and all **850 starting guns**, full
world-coordinate round trips for every static location, unchanged neutral maps,
17 measured roof landmarks, held-out Miller gun silhouettes from the user's
WoRTool reference (six individual guns and the other four-gun group), corrected gun ground samples, stale
observation exclusion, skew correction and invalid input. All **171 frozen
mission cases** are also evaluated at their corrected image positions, retaining
their physical-world range, ground heights, clearance and ballistic results.

The retired implementation's frozen references remain unchanged. Their legacy
projection is reconstructed by omitting the new alignment policy in the test
asset adapter; separate tests exercise the shipping corrected engine. This keeps
the independent historical physics reference without blessing the old artwork
alignment as the new expected behavior.

Frontend checks cover one-time migration, import/export, write failure recovery,
point preservation, hidden stale firing cards, notes and fresh recalculation.
Final validation passed: `cargo test --workspace` (18 integration tests),
`npm.cmd test` (126 tests), including unchanged compass cardinals and updated
bearings for reprojected world points. Calculator and sketcher Tauri release builds pass.
Both portable desktop packages contain the updated catalog. The existing
non-fatal Cargo PDB output-name collision warning remains.
