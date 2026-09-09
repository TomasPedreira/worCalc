# Artillery launch asset investigation

Inspected the local asset copy on 2026-09-08. This is an evidence report, not a
change to the ballistic solver. Machine-readable values and entry SHA-256 hashes
are in [artillery-asset-evidence.json](artillery-asset-evidence.json).

## Geometry recovered

All four gun definitions contain a named `Muzzle` attachment on the `Cannon`
bone. Its relative rotation is the identity. The barrel geometry is attached to
that same bone. Skeleton default-pose transforms give:

| Gun | Cannon pivot Z above model origin | Muzzle distance along bone +Y |
| --- | ---: | ---: |
| 3-inch Ordnance | 1.158611 m | 1.031668 m |
| 10-pounder Parrott | 1.158611 m | 1.207913 m |
| Napoleon 1857 | 1.198882 m | 0.952721 m |
| Napoleon 1861 CSA | 1.198882 m | 0.952721 m |

The muzzle has effectively zero vertical offset relative to the Cannon bone.
Thus pivot and muzzle have the same default-pose height, but different forward
positions. Elevating the barrel would change muzzle height by approximately
`distance * sin(barrel pitch)` relative to the pivot, for a level carriage.
This describes geometry; it does not prove the projectile uses that attachment.

The reference origin is `root_Gun_Carriage`, with an identity default transform.
These are **model-origin heights**, not measured ground clearances. Suspension,
carriage pitch/roll, and actual ground contact can change world-space heights.
No assumption that the root is exactly on terrain is verified by these files.

## How the transforms were checked

The CHR header identifies CryEngine chunk format 0x746. Compiled-bone chunk
0x2000/version 0x800 contains a 32-byte prefix and twelve 584-byte bone records.
Each record contains inverse World2Bone/Bone2World matrices and a 256-byte name.
Names and matrices were read using record boundaries, not arbitrary string hits.
All twelve matrix pairs in each referenced skeleton passed multiplication-to-
identity checks with maximum component errors below 0.000001.

Reference for the compiled structure:
[Crytek-authored CryHeaders.h in Lumberyard](https://github.com/aws/lumberyard/blob/v1.10.0.0/dev/Code/CryEngine/CryCommon/CryHeaders.h).

## Firing configuration recovered

`Assets/GameData.pak`, entry `Generated/archetype_database_migration.xml`, links
the Parrott to controller category `Ordnance`, matching the 3-inch. Both Napoleon
variants use `Napoleon`. This supports the shared Ordnance ammo profile already
used by the app, but is configuration evidence, not a runtime execution trace.
The runtime `archetype_database.cgb` was not decoded in this investigation.

The controller exposes aiming limits, recoil, elevation-screw travel, a firing
sound, and per-gun fuze tables. Its serialized `firing` element contains only
`FireSound`; no projectile-origin bone/helper or launch-angle correction is
specified there. In particular, no +0.48 degree setting was recovered.

The migration tables differ: the 3-inch has a 0 degree / 380 range entry; the
Napoleons have 0 degree / 300; the Parrott has separate entries including 1 degree
/ 600. Their units and accuracy as current physical impact measurements are not
established here. They must not be used as new calibration truth merely because
they exist in the assets.

## What remains unknown

- Whether server projectile creation uses the Cannon pivot, Muzzle attachment,
  or another position computed in compiled game logic.
- How the displayed angle is calculated relative to the actual launch direction.
- How the default pose is transformed when a gun is settled on uneven ground.
- Whether runtime overrides change any serialized ammo parameters.

`Scripts.pak` contains JSON/XML definitions but no Lua firing implementation.
Searching the inspected Scripts/GameData definitions did not recover the above
logic. Missing exposed fields are not proof of a particular compiled behavior.

The current 1.2 m height differs from the 3-inch default model-origin pivot by
only 0.041389 m. If both were referred to the same ground plane, the approximate
sight-angle difference at 300 yd would be 0.00865 degrees. That discrepancy alone
does not explain a 0.2 degree miss.

## Consequence for the next solver increment

Represent launch geometry explicitly (pivot height, forward offset, angle offset)
per gun. Keep these measured asset values distinct from runtime-verified values.
Do not silently replace the solver's height or derive a universal angle correction
from these model transforms. A stationary-gun test across several known target
distances/heights is still needed to validate the launch convention.
