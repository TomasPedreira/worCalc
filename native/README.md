# worCalc native application

Desktop and Android use Tauri, the same embedded interface and `worcalc-core`.
The build uses Node.js and Rust. Runtime requires no Python, PAK files, web server
or launcher. The fire calculator and Sketcher share native calculations and maps.

## Windows

```powershell
npm.cmd ci
npm.cmd test
cargo test --workspace
npm.cmd run desktop:build
```

The release executable and resource folder stay together. This workspace also
provides a portable copy under `artifacts/desktop/worCalc`. `tauri dev` uses a
local Vite server for development only; release HTML/JS/CSS are embedded.

## Offline data

`native/assets` is the canonical pack. Its catalog contains map dimensions,
projection, locations, weapon profiles and launch geometry. WebP images have
individual paths; WRT1 terrain grids are shared per battlefield. The Node
preparer checks the length and SHA-256 of every asset before staging the pack in
`src-tauri/resources`. Retain the canonical pack or `artifacts/data` backup.

WRT1 is zlib-compressed little-endian binary: a four-byte magic, four uint32 values
(world size, unit metres, sector metres, tile count), followed by X-major tiles.
Each tile starts with five int32 values (sector X/Y, grid size, offset steps,
height step), then grid-size squared uint16 values. Elevation bits and terrain
holes are preserved. The reader rejects invalid dimensions, tile order, truncated
data and payloads larger than 64 MiB.

The engine keeps one battlefield terrain in memory, at most 200 calculation
traces and 2,000 observations. Observations persist in app-private storage;
Sketcher plans use durable primary/backup files and JSON import/export.

## Android

Existing Android tooling is retained. It requires Java 21, SDK 36 and an NDK in
addition to Rust and Node:

```powershell
$env:JAVA_HOME = 'C:/Program Files/Java/jdk-21'
$env:ANDROID_HOME = 'C:/Users/pedre/AppData/Local/Android/Sdk'
$env:NDK_HOME = "$env:ANDROID_HOME/ndk/29.0.14206865"
npm.cmd run android:build
```

The PowerShell builder copies native resources explicitly and signs the ARM64 APK
with the local development key under `artifacts/android`. Keep that key for
subsequent upgrades. Use an appropriate release signing process for distribution.
This desktop migration has been validated on Windows; Android device validation
must be repeated after a new APK build.

## Validation

`cargo test --workspace` checks physics, terrain, malformed data, the native
command contract, storage recovery, exports, and frozen reference results across
all maps and weapon profiles. `npm test` checks IPC, map loading/cancellation,
calculator interactions, shared Sketcher points, independent configurations,
stale calculations, failed writes, imports and data-pack integrity. Tests run
without Python. Calculation references were captured before retiring the legacy
implementation, whose 221-test suite passed.
