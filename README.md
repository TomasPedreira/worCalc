# worCalc

worCalc is an offline Tauri application for War of Rights. Open it and choose:

- **Fire calculator**: place a gun and target, calculate elevation and fuze,
  inspect terrain clearance, or record observed impacts for calibration.
- **Sketcher**: prepare shared targets and save independent firing settings for
  each gun position. Select a gun to highlight its targets and use saved values.
  Plans persist locally and can be exported/imported as JSON.

The application includes 99 maps, projected game markers and battlefield terrain.
Calculations run in Rust. The interface is embedded in the Tauri WebView. Python,
a web server and a separate launcher are unnecessary.

## Windows

Open `worcalc-app.exe` in the portable desktop folder, keeping its `resources`
folder alongside it. See `RUNNING_ON_WINDOWS.txt`. This workspace's desktop build
is under `artifacts/desktop/worCalc`; the ZIP contains that complete folder.

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
# Release executable and complete portable ZIP:
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
