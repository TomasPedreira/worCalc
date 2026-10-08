# Sketcher

The Tauri application starts with a workspace selector: the fire calculator or
Sketcher. Both use the same map library, map navigation, compass, solution display
and Rust engine through local native commands.

Open `artifacts/desktop/worCalc/worcalc-app.exe` directly. Rebuild and refresh that
portable app and its offline resources with `npm.cmd run desktop:build`.

Sketcher opens in **View mode**. Select a gun to colour its configured targets and
immediately reveal their saved elevation/fuze windows on the map. Other targets
stay dimmed. Click a coloured target to focus its aim, distance and the existing
calculator readout. Use the plan panel's **Gun position** selector when nearby gun
markers overlap at the current zoom. The panel lists the selected gun's settings.
Selection uses saved values without recalculating or modifying the plan. Clicking
a gun or target opens its editable details directly in the right column. Map
markers have no text labels or hover titles. Persistent IDs are internal to
storage and relationships; they are not shown in the interface. There are no
point-name fields. Existing plans retain their IDs and configurations.

**Place gun (G)** is always visible. Select it, then click anywhere on the map to
save a new gun position immediately and select it. The action enters editing
automatically; its coordinates and cannon are immediately editable in the right
column. A new gun inherits the selected gun's cannon type, or the calculator's
default when no gun is selected. Several guns can be placed freely, including on
maps with no default starts. Nearby positions do not snap to a default gun.

Select a gun, then choose **Edit** to prepare its targets or drag existing guns, using the same map
coordinates, pan and zoom as the calculator. A gun move is saved on release;
Escape, cancelled gestures and starting a pinch discard the preview. Moving
invalidates only that gun's saved fire settings; shared targets and the other
guns' configurations remain. An unchanged position preserves its settings.

Existing gun starting positions are included when a map's plan is
first created; the cannon profile is matched to the game reference's name when
available, otherwise it uses the calculator's default. Select the gun to change
it in the side column. **Add target** followed by a map click creates
a target. Clicking an existing target opens a configuration for the selected gun.
The side editor calculates through the existing engine in operational mode. **Save**
stores either its exact defaults or the entered elevation/fuze, ammunition,
ground/airburst mode and notes. Cancelling a new target creates no point or configuration.
The editor shows the selected point's settings. Existing points
can be edited and saved directly in view mode; **Calculate** prepares a new firing
configuration when there is no saved one. **Done editing**
returns to view mode and displays the newly saved settings. Selecting another gun
reveals only that gun's configurations at the same shared target positions.

Targets are shared physical points. Each `(gun_id, target_id)` pair has its own
configuration. Updating one pair preserves every other gun's settings. Notes belong
to the pair. **Remove configuration for this gun** leaves
the physical target and other settings intact. Deleting a shared target removes
all its configurations. Changing a gun's cannon type clears that gun's existing
configurations so that an old solution is never presented for the new weapon.
Editing a shared target's coordinates clears all guns' outdated configurations
for it; saving with a selected gun calculates a replacement for that gun.

**Delete** removes the most recently selected gun or target. The inspector also
provides **Delete gun** / **Delete target** buttons. Deleting a gun removes its fire
settings while preserving shared targets and other guns. Deleting a target removes
the point and every configuration attached to it. Delete inside a text/number
field edits the field normally. With no selected point, Delete does nothing; after
deletion it does not fall back to deleting the active firing gun. An unsaved target
is simply discarded. Numeric IDs are retained after deletion and are not reused.

Manually adjusted values are labelled as saved adjustments. Terrain clearance and
explosion height are not displayed for them because those predictions describe the
original calculated shot. A configuration cannot be saved if the engine returns
no solution.

## Persistence and sharing

The pure `native/frontend/src/sketch-model.js` library owns the versioned document,
validation, relationship operations and transactional store. `sketcher.js` owns
presentation; `app.js` supplies map and fire-mission functions through native IPC.

Tauri uses `native_sketch` IPC to save `sketches.json` in app-private storage. Each
successful save retains the previous revision in `sketches.bak`; startup recovers
that revision if a save was interrupted between renames. A corrupt primary file
is surfaced instead of silently overwritten.

**Export plans** exports the complete library as JSON. Tauri writes a unique file
in Downloads and reports its path. **Import plans** accepts the same JSON file on
desktop or Android, replaces the included maps after a
confirmation when they already exist, and preserves maps absent from the file.
Imports validate the schema version, map identity/dimensions, coordinates, weapon
profiles, point references, pair uniqueness and finite fire settings before saving.
Files are limited to 5 MiB. Unsaved changes and failed writes do not change the
in-memory saved plan. Plans are local; exporting a file is the sharing mechanism.

## Verification

`npm test` covers shared geometry, independent configurations, defaults/overrides,
selection without writes, side-editor saves, most-recent selection deletion,
coordinate changes, cancellation and stale requests, invalid imports, persistence
failures and native IPC. `cargo test -p worcalc-app --lib` covers durable storage,
recovery, invalid updates and exports. `cargo test --workspace` additionally checks
calculator references for all maps and weapon profiles. The full native suites
run without Python.

`npm run test:desktop` additionally builds an isolated Tauri app and drives its
embedded WebView through a local debugging connection. It verifies the complete
placement, calculation, default/override Save, shared-target, side-inspector edits,
Delete keys and buttons, field editing, dragging, Cancel, process restart and
export/import workflow with real native commands and files.
It uses the separate `pt.tomaspedreira.worcalc.flowtest` application identifier and
refuses to write to the normal application's storage. No web server is used.
Install Playwright for this optional UI test, or set `WORCALC_PLAYWRIGHT_PATH` to
an available Playwright package directory. Screenshots and results are written to
`artifacts/validation/desktop-flow`.
