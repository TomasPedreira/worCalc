# worCalc architecture

This repository builds three independent local Tauri applications: worCalc,
worSketch and Kill Tracker. Each opens directly into its own interface, has its
own application identity and storage, and contains only its native command set.
worCalc and worSketch share the Rust calculation library and offline map pack.
Kill Tracker has no map resources or calculation library. There is no hub.

```text
native/core/           Pure Rust physics, projection, terrain and calibration
native/core/tests/     Unit tests and independent calculation references
native/frontend/src/   Local HTML/CSS/JS interface and pure plan model
native/frontend/       Tauri IPC adapter, Vite configuration and Node tests
native/assets/         Canonical offline catalog, images, terrain and hash manifest
native/prepare-assets.js  Node-only validation and staging of the data pack
src-tauri/src/         Native composition, resource reads and durable storage
src-tauri/resources/   Generated copies of the validated data pack
native/apps.json      Application identities, Cargo features and portable paths
```

## Dependency direction

Vite modes `calculator`, `sketcher` and `kill-tracker` create separate frontend
directories. Cargo features select the corresponding native commands; the default
is calculator. Per-app Tauri configs select identity, title and embedded frontend.
`native/build-desktop.ps1` builds and packages each feature independently and
creates direct executable shortcuts. Android builds only the calculator.

The interface invokes local Tauri commands. Tauri composes `worcalc-core` with a
bundled `AssetStore` and app-private storage. The Rust core has no UI, Tauri, network
or file-system dependency; callers supply its assets. Reusable calculations belong
in the core, and reusable plan operations belong in `sketch-model.js`.

`transport.js` exposes structured `maps`, `options`, `locations`, `calculate` and
`impact` operations. Map images arrive as binary IPC responses. There is no HTTP
API, browser fallback, Python runtime, Python build step or launcher. Vite's local
server is used only by `tauri dev`; release builds embed the compiled interface.

## Maps and calculations

On Android and Windows, calculator placement controls sit beside the map name
and a neutral bottom strip switches cannon family, ammunition and aim point.
The quick and advanced controls share the same state and calculation path.
Rifled maps to the 3-inch Ordnance profile (identical to Parrott).
Smoothbore maps to the 12-pounder Napoleon profile.
The initial calculator view fills the canvas. FIT restores the whole map.
Advanced controls are accessible from the map library. worSketch keeps its cannon models.
Explosion height stays visible above the quick controls, and the floating
elevation/fuze window reserves space for that readout.

On Windows, T replaces the target set with one target on the next map click.
Shift+T adds a target. Every target has its own readout and solution, and the
map compass shows the sectors used by all targets. Dragging or removing a
target affects that target, and changing the gun or firing settings recalculates
all targets.
Calibration can select which solution receives an impact record. Temporary
targets are cleared when changing maps.

The canonical pack holds all 99 maps and four shared battlefield terrains.
`manifest.json` records each file's length and SHA-256. Preparation validates the
complete pack before staging resources. Keep this pack or its archive when cleaning
generated build directories. Raw game PAK extraction is outside the current build.

The catalog retains the original export plus a versioned `map_alignments` policy.
The Rust core resolves it once so location markers, terrain sampling and distance
calculations share the same corrected projection. Neutral maps remain unchanged.
Changed maps expose a coordinate revision; observations and saved solutions from
an older revision cannot be reused as current results. Sketch migrations preserve
the old geometry and settings in the exported document's alignment history.
See `docs/map-alignment-corrections.md` for the rollout policy and its limits.

Terrain preserves elevation bits, triangle interpolation and holes. The engine
retains one battlefield at a time, up to 200 calculation traces and up to 2,000
calibration observations. Heavy calculations and resource reads run away from the
UI thread. The interface ignores stale calculations and cancelled image reads.

## Sketcher

`sketch-model.js` owns versioned documents, shared target geometry, independent
gun-to-target settings, validation and transactional persistence. `sketcher.js`
receives map navigation, native calculation and storage through explicit hooks.
`map-marker.js` renders the gun and target markers for both modes, using the same
marker styles. Sketcher adds selection and configuration opacity to their anchors.
`fire-readout.js` supplies the shared elevation/fuze window and text formatting.
Gun selection reveals its saved target windows; a target click focuses the
calculator's mission geometry. Editing and operating have separate visible states.
View selection shows saved targets and cannon choices in the right sidebar,
without edit fields. Edit must be explicitly enabled for placement, dragging,
coordinate/settings changes, deletion and import. Leaving Edit discards unsaved
fields and previews. Explicit Save applies the current edit. During Edit,
`moveSavedPoint` preserves pre-calculated settings without invoking the engine.
The right inspector reserves map space at every width and shared-target selection
offers each linked cannon. Persistent point IDs are internal
storage references. Sketcher markers have no labels or hover titles; the inspector
and lists omit IDs. Legacy names are stripped while preserving references.
Delete keys and inspector buttons remove the most recently selected point, with
relationship cleanup in the model. Calculations use the same Rust engine as the
calculator and allow exact defaults or manual elevation/fuze overrides.

`sketch_store.rs` saves app-private `sketches.json` with a recoverable previous
revision. Export creates unique JSON files in Downloads. Import validates the
document before replacing included maps. On worSketch's first load, an existing
library from the former shared worCalc data directory is copied into worSketch
only if neither a current library nor recovery backup exists. The source is
preserved; corrupt legacy data is reported. See `docs/sketcher.md`.

## Kill tracker

`src-tauri/src/kill_tracker.rs` owns Windows process discovery, executable hash
verification, read-only process handles, stable recorder snapshots, death decoding
and app-private capture files. `native_kill_tracker` composes start/poll/stop outside
the core. Opening the workspace does not attach; Start requires explicit read-only
authorization. Handles close on Stop, capture errors and app exit. The frontend
polls serially every 250 ms while its own app is open, and keeps
up to 2,000 recent rows. Full raw changes and decoded JSONL/CSV are saved under
the app data directory's `kill-captures`. Capture supports only the verified
0.0.201.2 executable; other builds are refused before opening a process handle.

See `docs/kill-tracker.md` for controls and output files.

## Change boundaries and validation

Claim core/domain, maps, a UI component, or integration before editing. Keep shared
schema changes coordinated with consumers. Add focused tests for behavior changes.
Run the full native suites before handoff:

```powershell
npm.cmd test
cargo test --workspace
npm.cmd run tauri -- build --no-bundle
```

The retired Python suite passed all 221 tests before removal. Its independent
physics, clearance, empirical, map-mission and impact results are retained as JSON
fixtures, checked by Rust without requiring Python. The legacy source, including
uncommitted tools, is recoverable from the local `artifacts/migration` archive;
it is outside the active application and build.
