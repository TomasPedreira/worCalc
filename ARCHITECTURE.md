# worCalc architecture

worCalc is a local Tauri application. Its entry screen selects the fire calculator
or Sketcher. Both use the same Rust calculation library and bundled map pack.

```text
native/core/           Pure Rust physics, projection, terrain and calibration
native/core/tests/     Unit tests and independent calculation references
native/frontend/src/   Local HTML/CSS/JS interface and pure plan model
native/frontend/       Tauri IPC adapter, Vite configuration and Node tests
native/assets/         Canonical offline catalog, images, terrain and hash manifest
native/prepare-assets.js  Node-only validation and staging of the data pack
src-tauri/src/         Native composition, resource reads and durable storage
src-tauri/resources/   Generated copies of the validated data pack
```

## Dependency direction

The interface invokes local Tauri commands. Tauri composes `worcalc-core` with a
bundled `AssetStore` and app-private storage. The Rust core has no UI, Tauri, network
or file-system dependency; callers supply its assets. Reusable calculations belong
in the core, and reusable plan operations belong in `sketch-model.js`.

`transport.js` exposes structured `maps`, `options`, `locations`, `calculate` and
`impact` operations. Map images arrive as binary IPC responses. There is no HTTP
API, browser fallback, Python runtime, Python build step or launcher. Vite's local
server is used only by `tauri dev`; release builds embed the compiled interface.

## Maps and calculations

The canonical pack holds all 99 maps and four shared battlefield terrains.
`manifest.json` records each file's length and SHA-256. Preparation validates the
complete pack before staging resources. Keep this pack or its archive when cleaning
generated build directories. Raw game PAK extraction is outside the current build.

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
Selection displays saved values without writes and opens an editable side
inspector. Explicit Save applies coordinates, cannon or independent firing settings.
Map editing enables placement and dragging. Persistent point IDs are internal
storage references. Sketcher markers have no labels or hover titles; the inspector
and lists omit IDs. Legacy names are stripped while preserving references.
Delete keys and inspector buttons remove the most recently selected point, with
relationship cleanup in the model. Calculations use the same Rust engine as the
calculator and allow exact defaults or manual elevation/fuze overrides.

`sketch_store.rs` saves app-private `sketches.json` with a recoverable previous
revision. Export creates unique JSON files in Downloads. Import validates the
document before replacing included maps. See `docs/sketcher.md`.

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
