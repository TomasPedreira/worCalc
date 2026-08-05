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
    ARTILLERY_MUZZLE_HEIGHT_METRES,
    ARTILLERY_PHYSICS,
)


def curve_samples_to_zero(
    model,
    minimum_elevation: float,
    maximum_elevation: float,
    sample_count: int,
) -> tuple[list[float], list[float]]:
    """Return plot-only samples extended from the fitted curve to 0 yards."""

    start_range = model.evaluate(minimum_elevation)
    derivative_step = max(
        (maximum_elevation - minimum_elevation) / 10_000,
        1e-6,
    )
    start_slope = (
        model.evaluate(minimum_elevation + derivative_step) - start_range
    ) / derivative_step
    plot_minimum = minimum_elevation
    if start_range > 0 and start_slope > 0:
        plot_minimum -= start_range / start_slope

    elevations = [
        plot_minimum
        + (maximum_elevation - plot_minimum) * index / (sample_count - 1)
        for index in range(sample_count)
    ]
    ranges = [
        max(
            0.0,
            start_range + start_slope * (elevation - minimum_elevation),
        )
        if elevation < minimum_elevation
        else model.evaluate(elevation)
        for elevation in elevations
    ]
    return elevations, ranges


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
        default=ARTILLERY_MUZZLE_HEIGHT_METRES / 0.3048,
        help="Muzzle height above the impact plane in feet (default: 1.2 m / 3.94 ft).",
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
        from matplotlib.ticker import MultipleLocator
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
    reference_elevations = [point.elevation_deg for point in points]
    reference_ranges = [point.range_yards for point in points]

    plt.style.use("seaborn-v0_8-darkgrid")
    figure, (curve_axis, residual_axis) = plt.subplots(
        2,
        1,
        figsize=(14, 8.5),
        sharex=True,
        gridspec_kw={"height_ratios": (3.2, 1)},
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

    colors = ("#3478bf", "#2f9e44", "#d94841", "#8e5bb7", "#ed7d00")
    plot_minimum = minimum
    for index, model in enumerate(models):
        color = colors[index % len(colors)]
        curve_elevations, curve_ranges = curve_samples_to_zero(
            model,
            minimum,
            maximum,
            args.samples,
        )
        plot_minimum = min(plot_minimum, curve_elevations[0])
        if model is theoretical:
            display_name = "Theoretical physics"
            linestyle = "--"
            linewidth = 2.6
        elif isinstance(model, PolynomialModel):
            display_name = model.name
            linestyle = "-."
            linewidth = 2.0
        else:
            display_name = model.name
            linestyle = "-"
            linewidth = 1.8
        curve_axis.plot(
            curve_elevations,
            curve_ranges,
            color=color,
            linestyle=linestyle,
            linewidth=linewidth,
            label=f"{display_name}  ·  RMSE {rmse(model, points):.1f} yd",
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

    figure.suptitle(
        f"Ballistic model comparison — {args.cannon} / {args.projectile}",
        fontsize=16,
        fontweight="bold",
    )
    curve_axis.set_title(
        f"Range prediction  |  {speed:g} m/s  ·  drag {drag:g} 1/s  ·  "
        f"gravity {args.gravity:g} m/s²  ·  muzzle {args.muzzle_height_feet:g} ft  ·  "
        f"bore offset {angle_offset:+.3f}°",
        loc="left",
        fontsize=10,
    )
    curve_axis.set_ylabel("Range (yards)")
    curve_axis.set_ylim(bottom=0)
    curve_axis.yaxis.set_major_locator(MultipleLocator(500))
    curve_axis.legend(
        loc="upper left",
        bbox_to_anchor=(1.01, 1),
        borderaxespad=0,
        fontsize=9,
        title="MODELS",
        title_fontsize=9,
        frameon=True,
    )
    curve_axis.annotate(
        f"First reference\n0°  ·  {points[0].range_yards:,.0f} yd",
        xy=(points[0].elevation_deg, points[0].range_yards),
        xytext=(18, 24),
        textcoords="offset points",
        fontsize=8.5,
        arrowprops={"arrowstyle": "->", "color": "#333333", "linewidth": 0.8},
    )
    residual_axis.set_title(
        "Error at official reference points (predicted − reference)",
        loc="left",
        fontsize=10,
    )
    residual_axis.axhline(0, color="black", linewidth=1.2)
    residual_axis.set_xlabel("Elevation (degrees)")
    residual_axis.set_ylabel("Error (yards)")
    residual_axis.xaxis.set_major_locator(MultipleLocator(1))

    for axis in (curve_axis, residual_axis):
        axis.set_xlim(plot_minimum, maximum)
        axis.axvspan(
            plot_minimum,
            minimum,
            color="#f2c94c",
            alpha=0.12,
            zorder=0,
        )
        axis.axvline(minimum, color="#6b6250", linewidth=1, linestyle=":")
    curve_axis.text(
        (plot_minimum + minimum) / 2,
        0.025,
        "PLOT-ONLY\nEXTRAPOLATION",
        transform=curve_axis.get_xaxis_transform(),
        ha="center",
        va="bottom",
        fontsize=7.5,
        color="#6b5928",
        fontweight="bold",
    )

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
