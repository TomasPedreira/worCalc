# Offline data pack

Keep `catalog.json`, `manifest.json`, `maps/` and `terrain/` together. These are
the canonical native inputs, independent of generated frontend/build resources.
There are 99 maps, 198 WebP images and four WRT1 terrain files. The manifest
records SHA-256 and size for every file; the Node build validates all of them.

Large game-derived images and terrain are local data, excluded from Git. This
workspace retains a complete backup at `artifacts/data/worcalc-offline-data.zip`.
On a fresh checkout, restore that archive into `native/assets` before building:

```powershell
Expand-Archive -LiteralPath artifacts/data/worcalc-offline-data.zip -DestinationPath native/assets -Force
npm.cmd run assets
```

The current native build consumes this prepared pack. Raw game PAK extraction
has been retired with the Python tools; changing source game assets requires an
updated compatible pack and manifest. Do not delete the pack while cleaning
`src-tauri/resources`, `native/frontend/dist` or `target`.
