# worCalc

Three standalone Tauri applications for War of Rights, version 1.1.8:

- **worCalc**: place a gun and target, calculate elevation and fuze,
  inspect terrain clearance, or record observed impacts for calibration.
- **worSketch**: prepare shared targets and save independent firing settings for
  each gun position. Select a gun to highlight its targets and use saved values.
  Plans persist locally and can be exported/imported as JSON.
- **Kill Tracker**: on Windows, explicitly start read-only capture of the running
  supported game build, search the live kill feed and save raw/decoded events
  locally. See `docs/kill-tracker.md` for supported builds and output files.

worCalc and worSketch include 99 maps, projected game markers and battlefield terrain.
Kill Tracker does not include map assets. Each app opens directly, without a hub.
Calculations run in Rust. The interface is embedded in the Tauri WebView. Python,
a web server and a separate launcher are unnecessary.

## Windows

Use the desktop shortcuts or the independent portable folders:

- `artifacts/desktop/worCalc/worcalc-app.exe`
- `artifacts/desktop/worSketch/worsketch.exe`
- `artifacts/desktop/KillTracker/kill-tracker.exe`

Keep each map app's `resources` folder beside its executable. Every app also has
its own portable ZIP. Existing Sketcher plans are copied into worSketch on first
launch, without removing the original library. See `RUNNING_ON_WINDOWS.txt`.

## Android

`npm.cmd run android:build` produces the calculator-only, signed ARM64 APK at
`artifacts/android/worcalc-1.1.8-arm64.apk`, with all maps available offline.
The existing application ID and signing key are retained for upgrades.

## Development

Install Node.js, the Rust toolchain pinned in `rust-toolchain.toml`, Microsoft C++
Build Tools and WebView2. Keep the offline data pack in `native/assets`; a local
backup is under `artifacts/data`. No Python installation or game PAK files are
needed by the native build. See `native/assets/README.md` for restoring the pack.

```powershell
npm.cmd ci
npm.cmd test
cargo test --workspace
npm.cmd run tauri -- dev
# Three standalone executables, portable ZIPs and desktop shortcuts:
npm.cmd run desktop:build
# Windows installer, when required:
npm.cmd run tauri -- build --bundles nsis
```

`tauri dev` uses Vite only during development; the installed application works
offline and communicates with Rust through local IPC. `npm run assets` verifies
the pack and stages Tauri resources using Node.js.

See `ARCHITECTURE.md`, `docs/sketcher.md` and `native/README.md`. Earlier Qt,
browser-server, asset-extraction and capture tools have been retired; their source
is preserved in the local migration archive rather than included in the app.
