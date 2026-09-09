"""Local rotating calculation traces for reproducing reported shots."""

import json
import logging
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from threading import Lock

from .paths import PROJECT_ROOT


CALCULATION_LOG = PROJECT_ROOT / "logs" / "calculations.jsonl"
_lock = Lock()
_loggers: dict[Path, logging.Logger] = {}


def record_calculation(details: dict, path: Path = CALCULATION_LOG) -> None:
    """Keep three bounded files; a logging failure must not break calculation."""
    try:
        line = json.dumps({"timestamp_utc": datetime.now(timezone.utc).isoformat(),
                           **details}, allow_nan=False, ensure_ascii=True)
        with _lock:
            logger = _loggers.get(path)
            if logger is None:
                path.parent.mkdir(parents=True, exist_ok=True)
                handler = RotatingFileHandler(path, maxBytes=2_000_000, backupCount=2,
                                              encoding="utf-8", delay=True)
                handler.setFormatter(logging.Formatter("%(message)s"))
                logger = logging.Logger(f"worcalc.calculations.{len(_loggers)}", logging.INFO)
                logger.addHandler(handler)
                logger.propagate = False
                _loggers[path] = logger
            logger.info(line)
    except (OSError, ValueError, TypeError):
        logging.getLogger(__name__).warning("Could not write calculation diagnostics", exc_info=True)


def read_observed_impacts(path: Path = CALCULATION_LOG) -> list[dict]:
    """Read retained impact events, tolerating rotation and malformed log rows."""
    events: dict[str, dict] = {}
    paths = [path.with_name(f"{path.name}.{index}") for index in (2, 1)] + [path]
    for candidate in paths:
        try:
            lines = candidate.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in lines:
            try:
                event = json.loads(line)
            except (json.JSONDecodeError, TypeError):
                continue
            impact_id = event.get("impact_id")
            if event.get("event") == "observed_impact" and impact_id:
                events[impact_id] = event
    return list(events.values())
