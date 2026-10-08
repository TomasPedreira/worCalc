# Agent working agreement

Read `ARCHITECTURE.md` before changing code.

- Claim one boundary (`native/core` domain/maps, a specific UI component, or integration).
- Keep Tauri, UI, network and filesystem composition outside `native/core`.
- Put reusable calculations in Rust libraries and plan operations in the pure frontend model.
- Add focused tests alongside every behavior change.
- Use native commands directly; do not reintroduce Python, browser-server fallbacks or launchers.
- Coordinate changes to shared data classes before editing their consumers.
- Run the full native suites (`cargo test --workspace` and `npm test`) before handoff.
