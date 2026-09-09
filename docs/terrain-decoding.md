# Native terrain elevation

`worcalc/maps/terrain.py` reads `terrain/terrain.dat` directly from the copied
`paks/<Battlefield>/level.pak`. No separate extraction, new dependency, or game
modification is required. All four supplied battlefields decode successfully.

## Supported format

The reader deliberately supports the observed little-endian terrain chunk 28,
flags 6, node version 7, Z ratio 1. Other formats raise `TerrainFormatError`;
they are not interpreted heuristically or silently replaced with object heights.

The 32-byte header includes the terrain dimensions and complete file length.
Three counted tables precede the quadtree: 360-byte vegetation records, 256-byte
brush names, and 256-byte material names. Each node has a 44-byte header,
optional packed uint16 samples, four-byte alignment, LOD-error floats, surface
IDs, and alignment. Children are ordered (0,0), (half,0), (0,half), (half,half).
The remaining payload is the outdoor object octree; this reader does not decode it.

Each battlefield has 128 x 128 leaf sectors, each 32 metres wide. Stored grids
vary from 3 x 3 through 33 x 33; a one-metre world grid does not mean every sector
stores independent one-metre heights. Samples are X-major (`x * size + y`).
Their low four bits are surface indices; index 15 represents a terrain hole.
The upper twelve bits are integer height steps, not normalized float heights.

For version 7, reconstruct the engine's integer offset and scale:

    maximum = float32(offset + float32(65520 * range))
    offset_steps = int(float32(offset * 20))
    range_steps = int(float32(float32(maximum - offset) * 20))
    step = ceil(range_steps / 4095) if range_steps else 1
    height_metres = (offset_steps + (raw >> 4) * step) * 0.05

Float32 arithmetic before integer truncation matters near quantization boundaries.
Coarse sectors are expanded bilinearly to unit-grid vertices. A query within a
unit cell then interpolates the lower or upper triangle split at dx + dy = 1,
matching the engine height/ray-query approach rather than smoothing that cell
bilinearly. Queries outside the world or inside terrain holes return `None`.
Bridges, buildings and other object collision meshes are not terrain heights.

## Integration and validation

`TerrainElevationField` preserves the `ElevationField` interface. Gun/target and
route heights query native sectors through the map's affine transform and world
origin. Its 65 x 65 overview samples support existing gradient legends and data
availability checks; those samples do **not** drive height interpolation. Legend
extrema/percentiles describe the overview, not guaranteed whole-map extrema.
Profiles cap their spacing at one terrain unit (one metre in these assets).
Finite spacing still cannot certify collision-free trajectories.

Missing archives or missing terrain entries retain the old object-anchor field.
A terrain hole does not fall back to object anchors. A route crossing an unknown
sample returns an empty profile, avoiding a fabricated continuous surface.
Battlefield terrain is cached by archive path, modification time and length.

Tests cover asymmetric axes and sector order, quantization, triangle interpolation,
coarse sectors, holes, boundaries, invalid data, archive loading and map projection.
An optional local-asset test checks all four full battlefields.

An independent coordinate sanity check against positioned spawn entities found:

| Battlefield | Spawn positions compared | Median absolute height difference |
| --- | ---: | ---: |
| Antietam | 344 | 0.167 m |
| DrillCamp | 402 | 0.240 m |
| HarpersFerry | 192 | 0.193 m |
| SouthMountain | 127 | 0.213 m |

Entity positions are not surveyed ground truth. These results support scale and
orientation, not an accuracy guarantee. In-game landmarks and shots remain the
next validation step. Ballistic curves, bore calibration, and clearance policy
are unchanged by this terrain work.

## Format references

Crytek-authored source preserved in the CRYENGINE release mirror:

- [Terrain node loading](https://github.com/MergHQ/CRYENGINE/blob/release/Code/CryEngine/Cry3DEngine/terrain_node_compile.cpp)
- [Packed height interpretation](https://github.com/MergHQ/CRYENGINE/blob/release/Code/CryEngine/Cry3DEngine/terrain_sector.h)
- [Height interpolation and ray queries](https://github.com/MergHQ/CRYENGINE/blob/release/Code/CryEngine/Cry3DEngine/terrain_hmap.cpp)

The newer Lumberyard node version 8 uses a different height/surface layout and
must not be substituted for this version-7 encoding.
