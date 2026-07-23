# Agent working agreement

Read `ARCHITECTURE.md` before changing code.

- Claim one boundary (`domain`, `maps`, a specific UI widget, or integration).
- Avoid editing `worcalc/ui/main_window.py` unless assigned integration work.
- Do not import Qt into `domain` or `maps`.
- Do not put reusable implementation in `scripts`.
- Add focused tests alongside every behavior change.
- Preserve the `src.*` compatibility facades while downstream imports migrate.
- Coordinate changes to shared data classes before editing their consumers.
- Run the full unittest suite before handoff.
