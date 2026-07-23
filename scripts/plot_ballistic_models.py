"""Plot reference, interpolation, least-squares, and theoretical ballistic curves."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from worcalc.domain.ballistics import (  # noqa: E402
    LinearDragTrajectoryModel,
    LinearModel,
    PchipModel,
    PolynomialModel,
    boresight_angle_offset,
    load_reference_points,
    rmse,
)
from worcalc.domain.projectile import (  # noqa: E402
    ARTILLERY_GRAVITY_METRES_PER_SECOND_SQUARED,
    ARTILLERY_PHYSICS,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare fitted, interpolated, and physics-based ballistic curves."
    )
    parser.add_argument(
        "csv",
        nargs="?",
        type=Path,
        default=PROJECT_ROOT / "war_of_rights_ballistic_ranges.csv",
        help="CSV with elevation_deg and range_yards columns.",
    )
    parser.add_argument(
        "--cannon",
        choices=ARTILLERY_PHYSICS,
        default="3-inch Ordnance",
        help="Installed cannon physics profile.",
    )
    parser.add_argument(
        "--projectile",
        choices=("Shell", "Case"),
        default="Shell",
        help="Installed ammunition physics profile.",
    )
    parser.add_argument(
        "--degrees",
        type=int,
        nargs="+",
        default=(2, 3),
        help="Polynomial degrees for the least-squares curves (default: 2 3).",
    )
    parser.add_argument(
        "--angle-offset",
        type=float,
        help=(
            "Explicit bore-angle offset. By default it is calibrated so the "
            "physics curve hits the first reference point."
        ),
    )
    parser.add_argument(
        "--muzzle-height-feet",
        type=float,
        default=2.5,
        help="Muzzle height above the impact plane in feet (default: 2.5).",
    )
    parser.add_argument(
        "--gravity",
        type=float,
        default=ARTILLERY_GRAVITY_METRES_PER_SECOND_SQUARED,
        help=(
            "Gravity in m/s² "
            f"(installed ammo value: {ARTILLERY_GRAVITY_METRES_PER_SECOND_SQUARED:g})."
        ),
    )
    parser.add_argument(
        "--samples",
        type=int,
        default=800,
        help="Number of samples per curve (default: 800).",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Save the figure as PNG, SVG, PDF, or another Matplotlib format.",
    )
    parser.add_argument(
        "--no-show",
        action="store_true",
        help="Do not open the interactive plot window.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.samples < 2:
        raise SystemExit("--samples must be at least 2")
    if any(degree < 1 for degree in args.degrees):
        raise SystemExit("--degrees values must be positive")

    try:
        import matplotlib
        if args.no_show:
            matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as error:
        raise SystemExit(
            "Matplotlib is required. Install the project requirements first."
        ) from error

    points = load_reference_points(args.csv.resolve())
    speed, drag = ARTILLERY_PHYSICS[args.cannon][args.projectile]
    muzzle_height_metres = args.muzzle_height_feet * 0.3048
    angle_offset = args.angle_offset
    if angle_offset is None:
        angle_offset = boresight_angle_offset(
            speed,
            drag,
            args.gravity,
            muzzle_height_metres,
            points[0].elevation_deg,
            points[0].range_yards,
        )
    interpolations = [LinearModel(points), PchipModel(points)]
    least_squares = [PolynomialModel(points, degree) for degree in args.degrees]
    theoretical = LinearDragTrajectoryModel(
        speed,
        drag,
        gravity_metres_per_second_squared=args.gravity,
        angle_offset_deg=angle_offset,
        muzzle_height_metres=muzzle_height_metres,
    )
    models = [*interpolations, *least_squares, theoretical]

    minimum = points[0].elevation_deg
    maximum = points[-1].elevation_deg
    elevations = [
        minimum + (maximum - minimum) * index / (args.samples - 1)
        for index in range(args.samples)
    ]
    reference_elevations = [point.elevation_deg for point in points]
    reference_ranges = [point.range_yards for point in points]

    plt.style.use("seaborn-v0_8-darkgrid")
    figure, (curve_axis, residual_axis) = plt.subplots(
        2,
        1,
        figsize=(12, 9),
        sharex=True,
        gridspec_kw={"height_ratios": (3, 1)},
        constrained_layout=True,
    )
    curve_axis.scatter(
        reference_elevations,
        reference_ranges,
        color="black",
        edgecolor="white",
        linewidth=0.7,
        s=48,
        zorder=10,
        label="Reference data",
    )

    colors = ("#4c78a8", "#54a24b", "#e45756", "#b279a2", "#f58518", "#72b7b2")
    for index, model in enumerate(models):
        color = colors[index % len(colors)]
        if model is theoretical:
            family = "physics"
            linestyle = "--"
            linewidth = 2.6
        elif isinstance(model, PolynomialModel):
            family = "least squares"
            linestyle = "-."
            linewidth = 2.0
        else:
            family = "interpolation"
            linestyle = "-"
            linewidth = 1.8
        curve_axis.plot(
            elevations,
            [model.evaluate(value) for value in elevations],
            color=color,
            linestyle=linestyle,
            linewidth=linewidth,
            label=f"{model.name} [{family}] · RMSE {rmse(model, points):.1f} yd",
        )
        residual_axis.plot(
            reference_elevations,
            [
                model.evaluate(point.elevation_deg) - point.range_yards
                for point in points
            ],
            marker="o",
            markersize=3.5,
            color=color,
            linestyle=linestyle,
            linewidth=1.4,
            label=model.name,
        )

    curve_axis.set_title(
        f"Ballistic model comparison — {args.cannon} / {args.projectile}\n"
        f"installed physics: {speed:g} m/s, drag {drag:g} 1/s, "
        f"gravity {args.gravity:g} m/s², muzzle {args.muzzle_height_feet:g} ft, "
        f"bore offset {angle_offset:+.3f}°"
    )
    curve_axis.set_ylabel("Range (yards)")
    curve_axis.legend(loc="best", fontsize=8.5)
    curve_axis.margins(x=0)
    residual_axis.axhline(0, color="black", linewidth=1)
    residual_axis.set_xlabel("Elevation (degrees)")
    residual_axis.set_ylabel("Error (yards)")
    residual_axis.margins(x=0)

    if args.output is not None:
        output = args.output.resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        figure.savefig(output, dpi=180)
        print(f"Saved {output}")
    if not args.no_show:
        plt.show()
    plt.close(figure)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
