# Gun starting positions

The Tauri calculator shows static green squares marked G for playable gun starts.
Amber battery markers remain artillery crew spawn references. Sketcher seeds its
initial gun positions from the same catalog and allows selecting them for saved
plans. These positions do not track movement during a match.

The prepared `native/assets/catalog.json` retains positions decoded from each
battlefield's `level.pak/objects.cgb`: object tables, entity archetype IDs, XYZ
positions, and nested layer hierarchy. The retired importer used these rules:
IDs are matched to the four playable cannon archetypes in the supplied
`Assets/GameData.pak/Generated/archetype_database_migration.xml`. Generic
`Entity-*` names are accepted; cannon model props and limber carts are excluded.
No nearest-crew-spawn association or entity-name guess is used.

The marker uses the serialized entity XYZ without an orientation-dependent
offset. The four artillery archetypes reference carriage roots with identity
transforms, and their CDF carriage geometry is attached at that root; the game
assets do not provide evidence for an additional lateral displacement.

Markers require the selected catalog layer to appear in the entity's layer
ancestry. Drill Camp's shared `Artillery` layer is included for its two camp maps.
World positions use the existing calibrated map transform and image bounds check.
The local Drill Camp maps each contain four visible gun starts. Battlefield-wide
playable gun placement totals are Antietam 242, Drill Camp 248, Harpers Ferry 188,
and South Mountain 69, across all decoded layers, before scenario/bounds filtering.

These are authored initial entity origins, not measured muzzle locations or live
server state. Runtime settling, server changes and movement may alter positions.
They have not yet been compared with fresh-round screenshots. Some scenarios have
no decoded playable guns, and some guns lie outside the displayed minimap crop;
an empty overlay does not prove that a server cannot spawn guns there. Missing or
unsupported source files produced no gun markers. Updating game archetypes
requires an updated compatible native data pack.
