# worCalc

worCalc measures straight-line distances on War of Rights gameplay-area minimaps.
The maps, battlefield names, and pixel-to-world transforms come from the game's
CryEngine PAK assets; world-space map distances are converted from metres to yards.

## PAK map data

The main application reads:

```text
paks/
  gameplay_area_calibrations.json
  converted_minimaps/
    <Battlefield>/Generated/Maps/<Battlefield>/<Mode>/GameplayArea_<n>.png
```

The JSON catalog is generated from the local `Assets/LevelsLooseFiles.pak` definitions.
It associates each PNG with its battlefield, mode, in-game gameplay-area name,
physical dimensions, rotation, and full affine pixel-to-world transform. The app no
longer uses the former `maps/` images or manual `res.config` calibrations.

To regenerate the catalog from the installed game assets:

```powershell
.\.venv\Scripts\python.exe paks\extract_gameplay_calibrations.py
```

The extraction and DDS conversion utilities are documented in `paks/README.md`.

## Run on Windows

For first-time setup, screenshots-free step-by-step instructions, later
launches, basic use, and troubleshooting, see
[`RUNNING_ON_WINDOWS.txt`](RUNNING_ON_WINDOWS.txt).

Quick setup for users already comfortable with PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m worcalc
```

Choose a map from the Battlefield → Mode → gameplay-area selector, then click two
points to see their distance in yards and an estimated 3-inch shell time of flight.
The estimate uses the installed shell physics values of 370 m/s and 0.1 air
resistance. It is shown as a recommended physics-based fuze time rather than copying
the game's longer dynamic-table estimate, which can overshoot the mapped target.
Use the **Round** selector to switch between Shell (370 m/s) and Case
(375 m/s) for the 3-inch gun; the displayed fuze estimate updates immediately.
The **Cannon** selector also supports the 12-pounder Napoleon, whose Shell and Case
profiles both use 439 m/s and 0.31 air resistance from the installed game data.
The 10-pounder Parrott is available using the shared rifled-artillery Shell and Case
profiles because the installed scripts do not expose a separate Parrott ammunition
definition.
Endpoints are draggable and update the result immediately. Right-click an endpoint to
remove it. The first map click places the cannon, the second places the target, and
later map clicks relocate only the target. Use **Clear** to reset the complete fire
mission. The mouse wheel zooms and dragging the map pans.

### Terrain-aware distance and coordinate diagnostics

Sampled altitude is always active. The app estimates gun and target elevations from
nearby positioned objects and uses their height difference to calculate 3D slant
distance. The fire-mission panel always shows horizontal (`H`), slant (`S`), and
height difference (`ΔH`) with enough precision to expose small corrections. A card
beside the target marker shows slant range, fuze/flight time, and ballistic elevation.
The **Show elevation gradient** checkbox changes only the map colors and never disables
altitude calculations.

**Show elevation gradient** overlays a high-contrast blue-to-red elevation gradient.
The colors use the map's 10th–90th elevation percentiles so sparse object-height
outliers do not hide small terrain changes. The current
overlay is explicitly diagnostic: CryEngine's `terrain.dat` contains compiled sector
data rather than a directly readable heightmap, so the field is interpolated from
the thousands of positioned game-object elevation anchors in each level. It is useful
for checking alignment against contours and known high/low ground, but it is not yet
the native terrain mesh.

Spawn, battery, and objective tooltips show decoded elevation, world X/Y, and
projected pixel coordinates. These make systematic crop or projection offsets
reproducible. Hovering anywhere inside the map continuously shows pixel X/Y, world
X/Y, and interpolated elevation. The compass uses the game transform without the
former extra 90-degree display rotation.

The green endpoint is the origin and the red endpoint is the target. Range rings
appear every 50 yards around the origin, with 100-yard rings emphasized and the final
ring labeled. The full game-authored affine transform is used, so distance and ring
geometry remain accurate on rotated or slightly non-square gameplay areas.

The final ring also acts as a world-oriented compass. N/E/S/W follow the directions
stored by the game rather than assuming that the top of every PNG is north. The map
information bar shows scale, physical dimensions, rotation, and elevation-anchor
coverage. A scale ruler remains fixed in the upper-left of the viewport and updates
as the view zooms.

The fire-mission panel presents bearing as a north-up map compass beneath the
elevation-method selector: map-up is 0°, right is 90°, down is 180°, and left is
270°. Its needle, cardinal marks, numeric degrees, and compass direction update
whenever the target is placed or moved. The control column scrolls vertically on
short windows so the compass and solution readouts never compress into each other.

PAK minimaps are displayed as dark ink on warm parchment by default. The **Map style**
selector switches between this UI-style composition and the raw grayscale mask without
changing the underlying image coordinates or calibration.

The selector starts collapsed. Search matches battlefield, mode, and gameplay-area
names and expands matching branches automatically.

## Ballistic curve explorer

```powershell
.\.venv\Scripts\python.exe scripts\ballistic_curve_explorer.py
```

The explorer plots the official 3-inch rifled-cannon reference data and switches
among linear interpolation, PCHIP, quadratic fit, and cubic fit. It is a standalone
developer tool and is no longer embedded in the main application. The application
uses the same domain models directly through its elevation-method selector, which
also offers a theoretical gravity/linear-drag curve and defaults to the cubic
least-squares fit. The theoretical option follows the selected cannon and ammunition
physics profile. Ranges outside the official 380–4,180 yard table are calculated by
extrapolating the selected curve. The curve is inverted using horizontal range, then
corrected by the signed gun-to-target sight angle, so uphill targets increase the
indicated elevation and downhill targets decrease it.

The fire-mission panel also performs an estimated route-clearance analysis. It
samples the current elevation field along the firing bearing, plots the terrain and
shell arc, identifies the first obstruction, and searches for the minimum higher
elevation that clears the route by one metre. When a raised trajectory is required,
the panel reports its height above the target, predicted impact range, and the number
of yards over or short of the selected target. Red and amber map markers show the
obstruction and predicted impact. Results remain explicitly marked **estimated**
until the compiled CryEngine
terrain heightmap is decoded; the current field is interpolated from positioned game
objects.

For an analysis plot that overlays the reference points, both interpolations,
least-squares polynomial fits, and the theoretical gravity/linear-drag trajectory:

```powershell
.\.venv\Scripts\python.exe scripts\plot_ballistic_models.py `
  --output ballistic_model_comparison.png --no-show
```

The theoretical curve reads velocity and drag from the installed profiles in
`worcalc/domain/projectile.py`, uses the ammo definition's 9.1 m/s² gravity,
and launches 1.4 m (about 4.59 ft) above the impact plane. By default, its bore angle is
calibrated so the physics curve hits the table's first (0°, 380 yd) boresight
point. Use `--cannon`, `--projectile`, `--gravity`, `--muzzle-height-feet`, or
`--angle-offset` to test other assumptions; omit `--no-show` for an interactive
window. Run the script with `--help` for all options.

## Tests

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

## Code organization

Production code lives in the feature-oriented `worcalc` package:

- `domain/` contains pure calibration, ranging, projectile, and ballistic math.
- `maps/` owns PAK catalogs, entity decoding, projection, and elevation.
- `ui/` owns Qt rendering and application composition.
- `scripts/` contains thin developer entry points only.
- `src/` contains temporary compatibility facades for old imports.

See `ARCHITECTURE.md` for dependency rules and parallel-agent ownership guidance.
