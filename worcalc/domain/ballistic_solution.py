"""Application-facing ballistic elevation solver without UI dependencies."""

from __future__ import annotations

from pathlib import Path

from .ballistics import (
    CurveModel,
    LinearModel,
    PchipModel,
    PolynomialModel,
    elevation_for_range,
    height_adjusted_elevation,
    load_reference_points,
)
from .projectile import ARTILLERY_GRAVITY_METRES_PER_SECOND_SQUARED
from .trajectory import (
    TerrainProfilePoint,
    TrajectoryClearanceResult,
    analyze_trajectory_clearance,
)


class BallisticSolutionEngine:
    def __init__(self, reference_path: Path) -> None:
        self.points = load_reference_points(reference_path)
        self.models: list[CurveModel] = [
            LinearModel(self.points),
            PchipModel(self.points),
            PolynomialModel(self.points, 2),
            PolynomialModel(self.points, 3),
        ]
        self.method_index = 3

    @property
    def method_names(self) -> list[str]:
        return [model.name for model in self.models]

    @property
    def method_name(self) -> str:
        return self.models[self.method_index].name

    def set_method(self, index: int) -> None:
        if not 0 <= index < len(self.models):
            raise ValueError(f"Unknown ballistic method index: {index}")
        self.method_index = index

    def solve(
        self,
        horizontal_range_yards: float,
        target_height_change_metres: float,
    ) -> float | None:
        minimum = self.points[0].elevation_deg
        maximum = self.points[-1].elevation_deg
        base_elevation = elevation_for_range(
            self.models[self.method_index],
            horizontal_range_yards,
            minimum,
            maximum,
        )
        if base_elevation is None:
            return None
        return height_adjusted_elevation(
            base_elevation,
            horizontal_range_yards,
            target_height_change_metres,
        )

    def analyze_clearance(
        self,
        horizontal_range_yards: float,
        target_height_change_metres: float,
        terrain_profile: tuple[TerrainProfilePoint, ...],
        speed_metres_per_second: float,
        drag_per_second: float,
        safety_margin_metres: float = 0.01,
    ) -> TrajectoryClearanceResult | None:
        angle = self.solve(
            horizontal_range_yards,
            target_height_change_metres,
        )
        if angle is None:
            return None
        return analyze_trajectory_clearance(
            terrain_profile,
            horizontal_range_yards,
            angle,
            speed_metres_per_second,
            drag_per_second,
            gravity_metres_per_second_squared=(
                ARTILLERY_GRAVITY_METRES_PER_SECOND_SQUARED
            ),
            muzzle_height_metres=0.762,
            safety_margin_metres=safety_margin_metres,
            confidence="estimated",
        )
