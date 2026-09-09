# Unified physics solver

The desktop and web app now default to **Unified physics (provisional)**.
The previous interpolation, polynomial, and boresighted theoretical methods
remain selectable for comparison. Their behavior is unchanged.

The new method solves for a lower-angle shot that reaches the target's actual
height at its horizontal range, within the selected cannon's angle limits. The
same linear-drag equations produce flight time and the trajectory used for
terrain checks. It does not extrapolate the reference CSV, add a sight angle to
a level-ground curve, or warp the trajectory to force an intersection.

The model uses `dv/dt = -k*v + gravity`. Launch velocity follows the physical
angle (displayed angle plus offset). Forward spawn displacement follows that
angle too. Zero drag and very small drag are handled without cancellation in
the vertical displacement calculation. A maximum-height search brackets the
lower-angle root; targets outside range/angle limits return no solution.

## Launch configuration

Edit `worcalc/domain/launch_profiles.json` and restart the app/server to change
each gun's launch height, forward distance, displayed-angle offset, and limits.
These are separate records so calibration can diverge between guns.

Defaults are deliberately **provisional**: 1.2 m above the gun's ground reference
and zero forward displacement (pivot hypothesis). All guns currently retain the
+0.48 degree community experimental estimate. These are not verified runtime spawn
transforms. The recovered model-origin pivot heights are not silently substituted
for ground clearance. See `artillery-launch-investigation.md` for the distinction.
Angle limits use the local archetype configuration. Projectile speed/drag are
selected by cannon and ammunition; gravity is 9.1 m/s².

If endpoint elevation is unavailable, current callers retain the existing
level-ground assumption. Terrain clearance remains unavailable when the route
contains missing heights. This solver does not make missing terrain known.

## Obstructions and flight time

The route includes the gun, target, and all supplied intermediate terrain samples.
There is no near-gun or terminal exclusion zone. First terrain intersection is
refined against the physical arc and linearly interpolated terrain. Tests include
obstacles one yard from the gun and five yards before the target.

A predicted terrain collision triggers a search for the lowest display angle
that clears every intermediate sample by 0.01 m. Operational web results round
that angle upward to the next 0.01-degree gun setting and recalculate flight time
and height over the target for the raised path. Web calculation diagnostics in
`logs/calculations.jsonl` retain the predicted collision, direct elevation, and
full sampled arcs. Calibration test mode exposes that original direct elevation
for controlled in-game validation. If no supported gun angle clears the route,
the clearance elevation is unavailable.

For an unobstructed shot, the fuze value represents ideal flight time to the
target point, without a detonation/mechanism delay. First collision and clearance
are relative to the sampled terrain profile, not all game collision geometry.
Native terrain sampling is at most one metre apart; vegetation, bridges, and
other object colliders can still invalidate a prediction. The 0.01 m numerical
clearance margin does not model shot dispersion.

The first 3-inch calibration series used one fixed Drill Camp CSA gun and bearing.
At -0.15 degrees, three marked impacts landed from 164 to 172 yards. At -0.14
degrees, one hit the ridge at 178 yards while two cleared it and landed at 332 to
333 yards. Shots at -0.13 and -0.10 degrees landed at 335 and 341 yards. These
observations locate the ridge-clearance transition between nearby game settings.
Later open-route and hilltop tests showed sub-yard agreement for the 10-pounder
Parrott at roughly 311 and 526 yards. These local observations support the current
profile but do not establish accuracy on every map, ammunition type, or range.

## Operational and calibration modes

The web app always uses unified physics. **Operational clearance** is the
startup mode and displays the lowest terrain-clearing elevation, rounded upward
to the gun's 0.01-degree setting. **Calibration test** displays the direct
physics elevation and enables impact recording so launch profiles can be
checked without changing operational recommendations.

## Verification

- Vacuum solution compared with the closed-form range equation.
- Independent RK4 integration for all three cannon profiles, Shell/Case, and
  uphill/level/downhill targets at 300 yards verifies both endpoint and time.
- Launch-height/forward/angle changes, small drag, invalid inputs, and unreachable
  targets checked separately.
- Terrain tests cover early and late obstructions, first collision, and an
  unmodified arc reaching an elevated target.
- Desktop and web integration tests verify consistent flight time, raised
  clearance solutions, and direct elevations in calibration mode. In-game
  validation remains necessary.
