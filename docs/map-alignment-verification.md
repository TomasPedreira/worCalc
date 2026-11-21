# Map alignment verification

Performed 19 October 2026 after the user requested the omitted before/after
terrain-overlay checks. Boundary: maps verification. This audit generated
research evidence; it did not change any shipping map, terrain, physics profile,
saved plan or application file.

## Result

All 60 changed map entries were compared with their original projections using
elevation-colour and computed-contour overlays. This includes all 35 changed
skirmish entries. The other 12 bundled skirmish entries have identity corrections.
The unchanged CSA Drill Camp was included as a control.

| Group | Entries | Supportive overlay evidence | Inconclusive |
| --- | ---: | ---: | ---: |
| Antietam rotations and measured fits | 30 | 30 | 0 |
| Other battlefield corrections | 30 | 13 | 17 |
| Total changed entries | 60 | 43 | 17 |

"Supportive" means the shipping version agrees better with the depicted relief;
it is not a claim of survey accuracy at every picture point. No blanket pass
was assigned to all 60 entries. Duplicate Conquest/Contention entries can share
world projections, so they are not independent map surveys.

The 13 supported additional entries are Alexander Farm, Larsen Homestead,
Smith Field, Union Camp, Pat's Turnpike, Crecy's Cornfield, Wagon Road,
South Woodlot, Stefan's Lot, Confederate Encampment, Crossley Creek, and
Outskirts in both Conquest and Contention. Several smaller supported changes
have modest evidence rather than the large improvement seen on Outskirts.

Sixteen inconclusive entries move picture points by less than two native image
pixels. Both overlays broadly agree, and the artwork/preview does not reliably
resolve that small difference. A weak positive image diagnostic is not enough
to certify such a correction.

**Picket Patrol 01 (`map-43`) remains the larger unresolved case**, with a maximum
corner displacement of 29.93 native image pixels. Its average contour-direction
agreement improves only slightly, and the spatial diagnostic interval includes
no improvement. A further comparison to the unchanged CSA Drill Camp artwork
shows remaining alignment differences in both versions and does not establish
that the shipping correction is correct. This entry needs stronger independent
landmark evidence before it can receive a verified result. No new transform was
fitted or applied in response to that inconclusive result.

## Method

The isolated Rust harness at
`tmp/gun-coordinate-audit/terrain-probe/src/bin/alignment-audit.rs` reads the
canonical catalog, resolves the actual shipping `align_catalog` policy, and
samples both projections through the unmodified `Terrain::elevation` reader.
Each image is sampled on a four-pixel grid, with heights stored as float32
metres. Both sides of each comparison use identical terrain, height colours
and contour intervals. Display interpolation is approximate.

Every changed entry was inspected in the generated contact sheets. Larger
additional corrections were also inspected in native-resolution details.
The paired image diagnostic compares normals of faint elongated artwork lines
with terrain-gradient directions, excluding dark glyphs and field hatching.
Its 128-pixel spatial blocks provide a rough indication of consistency across
regions. These approximate intervals are not survey confidence bounds.

This diagnostic measures local direction agreement, not exact contour position.
It cannot establish camera geometry, in-game compass heading, or barrel
calibration. The plotted maximum displacement is at image corners; it is not
the displacement of every gun. The height differences compare the same picture
point under two mappings; they are not independently measured elevation errors.

## Controls and validation

CSA Drill Camp has byte-identical original/corrected height grids and identical
image diagnostic values. The independently checked Miller correction improves
as expected. A synthetic analytic hill with known circular contours confirms
that the image diagnostic prefers the correct hill centre over a displaced one.

Grid dimensions, terrain-hole counts, height ranges, mean/max height differences,
image evidence coverage and world-coordinate round trips are checked. All 61
evidence sets are complete: 60 changed entries and the CSA control.

Passed:

- `node tmp/gun-coordinate-audit/verify-alignment-audit.cjs`
- `cargo test --workspace`: 18 integration tests
- `npm.cmd test`: 126 frontend tests

The production catalog remains at SHA-256
`a04bb44798096738e4cf13a65c2fde10d687fd91a458f2916611b025285ab1a8`,
matching the catalog used in release 1.1.3. The four terrain hashes are also
recorded and checked.

## Evidence files

The complete research output is in `outputs/map-alignment-audit/`:

- `README.md`: full map-by-map results and image links.
- `map-results.csv`: per-map verdicts and measured differences.
- `review.json`: results, review notes, image diagnostics and source hashes.
- `audit-data.json`: native sampling metadata and projection checks.
- `source-hashes.json`: exact catalog/terrain input hashes.
- `grids/`: original and shipping float32 height samples.
- `images/`: full overlays, paired comparisons, details and contact sheets.

Reproduction:

```powershell
cargo run --quiet --manifest-path tmp/gun-coordinate-audit/terrain-probe/Cargo.toml --bin alignment-audit -- 'C:/Users/pedre/Desktop/Pessoal/worCalc'
node tmp/gun-coordinate-audit/render-alignment-audit.cjs
node tmp/gun-coordinate-audit/verify-alignment-audit.cjs
node tmp/gun-coordinate-audit/summarize-alignment-audit.cjs
```
