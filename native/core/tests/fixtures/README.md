# Calculation references

These immutable results were captured before retiring the Python implementation,
after its complete 221-test suite passed. The Rust suite reads JSON directly;
Python is unnecessary to run tests or build the application.

Coverage: 127 physics/clearance cases (all velocity/drag profiles, zero and tiny
drag, unreachable targets, angle limits, near-gun and near-target crests), 12
empirical fits, 171 missions covering all 99 maps, all weapon/projectile profiles,
operating/calibration/airburst modes, an observed impact, and map locations from
all four battlefields. Numeric comparisons use an absolute tolerance of 1e-6.
Random vectors were captured with seeds 4382 and 1099. UUIDs are excluded.

Keep these expectations independent of the implementation. Do not regenerate
them from Rust to make a failing test pass.
