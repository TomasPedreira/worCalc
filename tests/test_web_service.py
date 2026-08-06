import json
import struct
import tempfile
import unittest
import zipfile
from io import BytesIO
from pathlib import Path

from PIL import Image

from worcalc.domain.calibration import METRES_TO_YARDS, Point
from worcalc.web.service import FireMissionCalculator, MapNotFoundError


ROOT = Path(__file__).resolve().parent.parent


def make_test_calculator(root: Path) -> FireMissionCalculator:
    paks = root / "paks"
    maps_dir = paks / "converted_minimaps"
    maps_dir.mkdir(parents=True)
    image_path = maps_dir / "test.png"
    Image.new("L", (200, 150), 128).save(image_path)
    catalog = [{
        "battlefield": "TestField",
        "mode": "Conquest",
        "gameplay_area": 0,
        "name": "Test Map",
        "width_m": 200,
        "height_m": 150,
        "rotation_degrees": 0,
        "pak_path": str(image_path),
        "pak_pixel_x_to_world_x_m": 1,
        "pak_pixel_x_to_world_y_m": 0,
        "pak_pixel_y_to_world_x_m": 0,
        "pak_pixel_y_to_world_y_m": 1,
    }]
    (paks / "gameplay_area_calibrations.json").write_text(
        json.dumps(catalog), encoding="utf-8"
    )
    return FireMissionCalculator(
        maps_dir,
        ROOT / "war_of_rights_ballistic_ranges.csv",
        paks,
    )


def add_test_locations(root: Path) -> None:
    level_pak = root / "paks" / "TestField" / "level.pak"
    level_pak.parent.mkdir(parents=True, exist_ok=True)

    def entity(name: str, elevation: float, x: float, y: float) -> bytes:
        return (
            b"\xaf\x77\xd2\x62" + struct.pack("<f", elevation)
            + b"\x83\x16\xdc\x8c" + struct.pack("<f", x)
            + b"\x15\x26\xdb\xfb" + struct.pack("<f", y)
            + name.encode("ascii") + b"\x00"
        )

    data = entity("Spawnpoint_USA_Artillery_Test", 50, 40, 50)
    data += entity("Victory_Test", 52, 120, 80)
    with zipfile.ZipFile(level_pak, "w") as archive:
        archive.writestr("objects.cgb", data)


class FireMissionCalculatorTests(unittest.TestCase):
    def test_lists_catalog_maps_with_image_dimensions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            calculator = make_test_calculator(Path(directory))

            maps = calculator.list_maps()

            self.assertEqual(len(maps), 1)
            self.assertEqual(maps[0].identifier, "map-1")
            self.assertEqual((maps[0].width_pixels, maps[0].height_pixels), (200, 150))

    def test_calculates_one_gun_to_target_solution(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            calculator = make_test_calculator(Path(directory))

            result = calculator.calculate(
                "map-1",
                Point(10, 20),
                Point(110, 20),
                "3-inch Ordnance",
                "Shell",
                calculator.default_method,
            )

            self.assertAlmostEqual(result.horizontal_range_yards, 100 * METRES_TO_YARDS)
            self.assertEqual(result.slant_range_yards, result.horizontal_range_yards)
            self.assertAlmostEqual(result.bearing_degrees, 90)
            self.assertEqual(result.bearing_direction, "E")
            self.assertIsNone(result.height_difference_metres)
            self.assertIsNotNone(result.elevation_degrees)
            self.assertIsNotNone(result.fuze_seconds)

    def test_renders_map_with_desktop_parchment_palette(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            calculator = make_test_calculator(Path(directory))

            with Image.open(BytesIO(calculator.parchment_image_bytes("map-1"))) as image:
                self.assertEqual(image.mode, "RGB")
                self.assertEqual(image.getpixel((0, 0)), (133, 120, 86))

    def test_renders_compact_webp_map_thumbnail(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            calculator = make_test_calculator(Path(directory))

            content = calculator.parchment_thumbnail_bytes("map-1", max_size=80)

            with Image.open(BytesIO(content)) as image:
                self.assertEqual(image.format, "WEBP")
                self.assertEqual(image.mode, "RGB")
                self.assertEqual(image.size, (80, 60))

    def test_renders_full_webp_map_without_changing_dimensions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            calculator = make_test_calculator(Path(directory))

            content = calculator.parchment_webp_image_bytes("map-1")

            with Image.open(BytesIO(content)) as image:
                self.assertEqual(image.format, "WEBP")
                self.assertEqual(image.mode, "RGB")
                self.assertEqual(image.size, (200, 150))

    def test_returns_projected_game_file_locations(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            calculator = make_test_calculator(root)
            add_test_locations(root)

            locations = calculator.map_locations("map-1")

            self.assertEqual([item.kind for item in locations], ["battery", "objective"])
            self.assertEqual((locations[0].pixel_x, locations[0].pixel_y), (40, 50))

    def test_rejects_unknown_maps_and_out_of_bounds_points(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            calculator = make_test_calculator(Path(directory))
            with self.assertRaises(MapNotFoundError):
                calculator.map_info("missing")
            with self.assertRaisesRegex(ValueError, "outside"):
                calculator.calculate(
                    "map-1",
                    Point(-1, 20),
                    Point(110, 20),
                    "3-inch Ordnance",
                    "Shell",
                    calculator.default_method,
                )


if __name__ == "__main__":
    unittest.main()
