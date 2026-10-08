# CryEngine PAK research data

These local archives and converted files are retained as research/source data.
The Tauri application and build use the validated pack in `native/assets`; they
do not read this directory. Python extraction and conversion tools have been
retired and archived under `artifacts/migration`.

The War of Rights packages inspected here are ZIP-based CryEngine PAK archives.
Some local ZIP headers use Windows backslashes while the central directory uses
forward slashes. The original importer handled that mismatch. Minimap projection
comes from gameplay-area definitions; gun markers from object/archetype records;
terrain elevations from the packed height grids described in
`docs/terrain-decoding.md`.

Keep the native offline data pack or its backup when cleaning generated files.
See `native/assets/README.md` for its format and restoration instructions.
