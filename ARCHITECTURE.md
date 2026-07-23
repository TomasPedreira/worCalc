# worCalc architecture

The repository is organized by change boundary. A feature should normally be
implemented inside one area and exposed through a small public function or data
class before the main window is changed.

```text
worcalc/
  domain/      Pure calibration, ranging, projectile, and ballistic math
  maps/        PAK catalog, entity decoding, projection, and elevation sampling
  ui/          Qt widgets and application composition
  paths.py     Shared repository data locations
scripts/       Thin developer-tool entry points
tests/         Tests grouped by the production boundary they exercise
src/           Temporary compatibility facades for old src.* imports
```

## Dependency direction

```text
domain  <-  maps  <-  ui
   ^                    |
   +--------------------+
```

- `domain` must not import Qt, map assets, or UI code.
- `maps` may use domain primitives but must not import Qt.
- `ui` composes both layers and owns rendering only.
- `scripts` are entry points; reusable code belongs under `worcalc`.
- Production code must never import from `scripts` or the compatibility `src`
  package.

## Parallel work

Safe concurrent ownership areas:

| Area | Primary files | Typical work |
| --- | --- | --- |
| Ballistics | `worcalc/domain/ballistics.py`, `projectile.py` | Models and physics |
| Ranging | `worcalc/domain/ranging.py`, `calibration.py` | Distance and transforms |
| Map data | `worcalc/maps/` | PAK parsing, locations, terrain/elevation |
| Map rendering | `worcalc/ui/map_view.py` | Markers, overlays, interaction |
| Explorer | `worcalc/ui/ballistics_explorer.py` | Curve-analysis UI |
| Integration | `worcalc/ui/main_window.py` | Wiring feature APIs into the app |

Only the integration owner should normally edit `main_window.py` during a
multi-agent pass. Other agents should deliver tested APIs from their owned
boundary. This keeps merge conflicts localized to a short integration step.

Every change should add or update a focused test. Run:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

The `src.*` facades are compatibility-only and can be removed after downstream
callers have migrated to `worcalc.*`.
