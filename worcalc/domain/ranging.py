"""Range calculations that are independent of the user interface."""

from __future__ import annotations

from dataclasses import dataclass
from math import hypot

from .calibration import METRES_TO_YARDS


@dataclass(frozen=True)
class RangeMeasurement:
    horizontal_yards: float
    elevation_change_metres: float | None = None

    @property
    def slant_yards(self) -> float:
        if self.elevation_change_metres is None:
            return self.horizontal_yards
        return hypot(
            self.horizontal_yards,
            self.elevation_change_metres * METRES_TO_YARDS,
        )

    def distance_yards(self, include_elevation: bool) -> float:
        return self.slant_yards if include_elevation else self.horizontal_yards
