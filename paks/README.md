# CryEngine PAK findings

These War of Rights packages are normal ZIP-based CryEngine PAK archives. They
are readable without a key, but their local ZIP headers use Windows backslashes
while the central directory uses forward slashes. `extract_cryengine_paks.py`
handles that legacy mismatch.

## Extracted data

The default extraction keeps the useful map-analysis files and omits the very
large AI navigation and cover caches:

```powershell
.\.venv\Scripts\python.exe paks\extract_cryengine_paks.py --profile core
```

Profiles:

- `metadata`: XML, TXT, CFG, JSON, and LST files only.
- `core`: metadata plus `terrain/terrain.dat` and all minimap DDS files.
- `all`: every archive entry, including cover and navigation caches.

The extraction manifest is `extracted/manifest.json`. The current core result
contains 169 files (801,317,530 uncompressed bytes), including four compiled
terrain files and 101 minimap textures.

## Minimap conversion

The 101 `GameplayArea_*.dds` assets are 2048 x 2048 BC3/DXT5 textures. Their RGB
channels are black; the actual grayscale tactical map is in the alpha channel.
It contains contour lines, roads, buildings, fields, and vegetation.

Convert that alpha channel to directly viewable PNG files with installed FFmpeg:

```powershell
.\.venv\Scripts\python.exe paks\convert_minimap_dds.py --jobs 4
```

The current output is under `converted_minimaps/` and preserves the battlefield,
game mode, and gameplay-area hierarchy:

| Battlefield | PNG maps |
| --- | ---: |
| Antietam | 31 |
| DrillCamp | 35 |
| HarpersFerry | 21 |
| SouthMountain | 14 |

## Terrain facts recovered

Both `levelinfo.xml` and the binary `terrain.dat` header agree on the terrain
layout. All four battlefields use:

- CryEngine Sandbox version 5.4.0.164
- 4096 x 4096 heightmap units
- 1 metre per terrain unit
- 32 metre sectors
- 128 x 128 sectors
- 4096 metre (about 4,479.44 yard) full-world width and height
- `HeightmapZRatio=1`

The editor metadata also provides these maximum terrain heights:

| Battlefield | Maximum height |
| --- | ---: |
| Antietam | 209 m |
| DrillCamp | 300 m |
| HarpersFerry | 336 m |
| SouthMountain | 411 m |

`terrain/terrain.dat` is not a standalone raw heightmap. It is CryEngine's
compiled runtime terrain chunk and also contains vegetation/object and sector
data. Its first 28 bytes match CryEngine's `STerrainChunkHeader` and embedded
`STerrainInfo`, so the height samples are present but still need the engine's
sector serialization decoded before they can be exported as a 16-bit image.

The copied level/minimap packages do not contain the gameplay-area bounds; the
full terrain width must not be applied directly to each cropped texture.

The local game asset copy contains this missing table in
`Assets/LevelsLooseFiles.pak`, under each
`Levels/<Battlefield>/Definitions/<Mode>.json`. Every gameplay area has an
authoritative name and either three world-space map corners or a center and
size. The coordinates are terrain metres and appear in the same order as the
`GameplayArea_N` textures.

`extract_gameplay_calibrations.py` reads those definitions directly from the
installed archive and produces `gameplay_area_calibrations.csv` and
`gameplay_area_calibrations.json`:

```powershell
.\.venv\Scripts\python.exe paks\extract_gameplay_calibrations.py
```

The result covers and names all 101 PAK textures directly from the authoritative
game definitions. It includes scalar X/Y yards-per-pixel values plus a full
pixel-to-world affine transform. The affine form is the authoritative option
because maps may be rotated and a few have mild skew or unequal X/Y scales.

## Relevant CryEngine documentation

- PAK archives are ZIP-based and can be opened by ordinary archive tools:
  https://www.cryengine.com/docs/static/engines/cryengine-3/categories/1638401/pages/1605746
- Level packages contain runtime level data and terrain/heightmap assets:
  https://www.cryengine.com/docs/static/engines/cryengine-3/categories/1638401/pages/1605643
- `STerrainInfo` defines heightmap size, unit size, sector size, Z ratio, and
  water level:
  https://www.cryengine.com/docs/static/engines/cryengine-3/categories/17399809/pages/17075356
