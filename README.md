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

## LAN web calculator

To use worCalc from another device on the same network, start the FastAPI server:

```powershell
.\.venv\Scripts\python.exe -m worcalc.web
```

Open `http://localhost:8000` on the computer running worCalc. On a phone or
another computer, replace `localhost` with the server computer's IPv4 address,
shown by `ipconfig` (for example, `http://192.168.1.20:8000`). Allow Python on
private networks if Windows Firewall prompts.

The browser workflow supports one fire mission at a time. Choose a grouped map
from the map drawer, use **Place gun** and **Place target**, then request the
solution. Drag the map to pan, pinch to zoom, and drag either marker to refine
its position. Cannon, ammunition, and elevation-model settings are available
from the fire-controls panel. The server has no authentication and should only
be exposed on a trusted local network.

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

The collapsible **Target history** card keeps numbered targets for the current app
session. Save the current gun/target pair as `T1`, `T2`, and so on, then use **New
target** to retain the user-placed gun while starting another mission. Left-clicking
a numbered map marker or history row selects it; clicking the selected target again
collapses its map solution and impact marks. Only the selected target's observed shots
are drawn, keeping the map uncluttered.

**Record impact** logs an observed round as over/short and left/right yard offsets
from the selected target. Positive values mean over and right; negative values mean
short and left. Each shot is kept under its target and rendered as a compact `S1`,
`S2`, etc. marker at its estimated landing position. Elevation fired, fuze, and an
optional note can be stored with the observation.

### Terrain-aware distance and coordinate diagnostics

Sampled altitude is always active. The app reads gun and target elevations from
compiled game terrain and uses their height difference to calculate 3D slant
distance. The fire-mission panel always shows horizontal (`H`), slant (`S`), and
height difference (`ΔH`) with enough precision to expose small corrections. A card
beside the target marker shows slant range, fuze/flight time, and ballistic elevation.
The **Show elevation gradient** checkbox changes only the map colors and never disables
altitude calculations.

**Show elevation gradient** overlays a high-contrast blue-to-red elevation gradient.
The colors use the overview grid's 10th–90th elevation percentiles. Heights come
from decoded native terrain sectors, including their quantization and variable
resolution. Object anchors are only a fallback for asset packages without terrain.
Holes and coordinates outside the terrain return unknown heights. Bridges and
other object collision meshes are not included. See
[terrain decoding](docs/terrain-decoding.md) for format details and validation.

Spawn, battery, and objective tooltips show decoded elevation, world X/Y, and
projected pixel coordinates. These make systematic crop or projection offsets
reproducible. Hovering anywhere inside the map continuously shows pixel X/Y, world
X/Y, and interpolated elevation. The compass uses the game transform without the
former extra 90-degree display rotation.

Static green squares show playable guns' starting placements from the selected
scenario's game-file layer. Amber battery markers are artillery crew spawn
references. Starting placements do not track movement; see
[gun starting positions](docs/gun-starting-positions.md) for coverage and limitations.
The yellow `G` marker is the gun position placed by
the user for the current fire mission.

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
defaults to **Unified physics (provisional)**: one physical trajectory determines
elevation, flight time, and terrain obstruction for the selected cannon and ammunition.
It solves directly for the target's horizontal range and terrain height. Per-cannon
launch height, forward displacement, angle offset, and limits are configurable.
See [the solver documentation](docs/unified-physics.md) for assumptions and calibration.

The elevation-method selector retains the previous models for comparison, including
the theoretical gravity/linear-drag curve. For these legacy methods, ranges outside
the official 380–4,180 yard table are calculated by
extrapolating the selected curve. The curve is inverted using horizontal range, then
corrected by the signed gun-to-target sight angle, so uphill targets increase the
indicated elevation and downhill targets decrease it.

The fire-mission panel samples the current elevation field, plots the terrain and
shell arc, and identifies the first obstruction. Unified physics displays the
normal target elevation on a clear route. On an obstructed route it searches for
the lowest terrain-clearing elevation, rounds upward to the game's 0.01° setting,
and recalculates fuze and target clearance for that raised path. Web diagnostics
retain the original direct trajectory for comparison with in-game shots. Native
terrain profiles sample at intervals of at most one metre.

The legacy comparison methods retain their estimated clearance analysis, which
searches for the minimum higher
elevation that clears the route by one metre. When a raised trajectory is required,
the panel reports its height above the target, predicted impact range, and the number
of yards over or short of the selected target. Red and amber map markers show the
obstruction and predicted impact. Results remain explicitly marked **estimated**
because the projectile model and finite route sampling still need in-game
validation.

For an analysis plot that overlays the reference points, both interpolations,
least-squares polynomial fits, and the theoretical gravity/linear-drag trajectory:

```powershell
.\.venv\Scripts\python.exe scripts\plot_ballistic_models.py `
  --output ballistic_model_comparison.png --no-show
```

The standalone plot's legacy theoretical curve reads velocity and drag from the installed profiles in
`worcalc/domain/projectile.py`, uses the ammo definition's 9.1 m/s² gravity,
and launches 1.4 m (about 4.59 ft) above the impact plane. By default, its bore angle is
calibrated so the physics curve hits the table's first (0°, 380 yd) boresight
point. Use `--cannon`, `--projectile`, `--gravity`, `--muzzle-height-feet`, or
`--angle-offset` to test other assumptions; omit `--no-show` for an interactive
window. Run the script with `--help` for all options.

Browser desktop controls: wheel zooms around the cursor; left drag pans; G/T select
gun/target placement, F fits the map, and Escape returns to panning. Large desktop
screens keep the map library and fire controls open beside the map. Elevation and
fuze appear beside the target. Gun, target, and static spawn markers render in a
screen-space overlay so they remain sharp, fixed-size, and anchored while zooming.

The browser always uses unified physics and starts in **Operational clearance**
mode. **Calibration test** mode exposes the direct physics elevation and impact
controls without changing operational recommendations. Its actual elevation field
defaults to the recommendation rounded to the game's 0.01° adjustment step. Correct
it before marking if a different setting was fired. Impact marks are saved in
`logs/calculations.jsonl` with that actual setting,
their calculation ID, original shot inputs, terrain prediction recomputed at the
actual angle, and distance from the predicted impact.
Mark impacts before changing the gun, target, or ammunition. Moving them clears
the visible marks but keeps saved logs. The server retains the latest 200
calculations for impact association; after a restart, recalculate first.

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
