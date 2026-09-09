import json
import struct
import tempfile
import unittest
import zipfile
from unittest.mock import Mock, patch
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
    def test_impact_links_to_exact_calculation_and_compares_prediction(self):
        with tempfile.TemporaryDirectory() as directory:
            calculator = make_test_calculator(Path(directory))
            result = calculator.calculate('map-1', Point(10,20), Point(110,20),
                                          '3-inch Ordnance','Shell',calculator.default_method)
            observation = calculator.record_impact(result.calculation_id, Point(90,20), 0.12)
            self.assertAlmostEqual(observation['distance_from_target_yards'],20*METRES_TO_YARDS)
            trace = self.trace.call_args.args[0]
            self.assertEqual(trace['event'],'observed_impact')
            self.assertEqual(trace['shot']['result']['calculation_id'],result.calculation_id)
            self.assertEqual(trace['impact_pixel'],{'x':90,'y':20})
            self.assertEqual(trace['actual_elevation_degrees'], 0.12)
            with self.assertRaises(ValueError):
                calculator.record_impact('expired',Point(90,20), 0.12)
            for point in [Point(-1,20),Point(float('nan'),20)]:
                with self.assertRaises(ValueError):
                    calculator.record_impact(result.calculation_id,point,0.12)
            for angle in [float('nan'), -90, 90]:
                with self.assertRaises(ValueError):
                    calculator.record_impact(result.calculation_id,Point(90,20),angle)

    def setUp(self):
        patcher = patch('worcalc.web.service.record_calculation')
        self.trace = patcher.start()
        self.addCleanup(patcher.stop)

    def test_unified_service_keeps_aim_and_logs_intervening_hill(self):
        from worcalc.domain.trajectory import TerrainProfilePoint as P
        with tempfile.TemporaryDirectory() as directory:
            calculator = make_test_calculator(Path(directory))
            field = Mock(samples=(1,))
            field.elevation_at.return_value = 0
            distance = 100 * METRES_TO_YARDS
            field.profile_along_line.return_value = (P(0,0),P(distance/2,5),P(distance,0))
            with patch.object(calculator, '_elevation_field', return_value=field):
                result = calculator.calculate('map-1',Point(10,20),Point(110,20),
                                              '12-pounder Napoleon','Shell',calculator.default_method)
            self.assertEqual(result.clearance_status,'obstructed')
            self.assertIsNotNone(result.elevation_degrees)
            self.assertIsNotNone(result.fuze_seconds)
            self.assertGreater(result.height_above_target_metres,0)
            trace = self.trace.call_args.args[0]
            self.assertEqual(trace['reason'], 'terrain_obstruction')
            self.assertEqual(trace['gun_pixel'], {'x': 10, 'y': 20})
            self.assertIsNotNone(trace['aim_elevation_before_terrain_deg'])
            self.assertLess(trace['clearance']['first_obstruction_yards'], distance)
            self.assertEqual(len(trace['terrain_profile']), 3)
            self.assertGreater(trace['result']['elevation_degrees'], trace['aim_elevation_before_terrain_deg'])
            self.assertEqual(result.elevation_source, 'terrain_clearance')

    def test_calibration_mode_exposes_direct_elevation_without_changing_default(self):
        from worcalc.domain.trajectory import TerrainProfilePoint as P
        with tempfile.TemporaryDirectory() as directory:
            calculator = make_test_calculator(Path(directory))
            field = Mock(samples=(1,))
            field.elevation_at.return_value = 0
            distance = 100 * METRES_TO_YARDS
            field.profile_along_line.return_value = (P(0, 0), P(distance / 2, 5), P(distance, 0))
            with patch.object(calculator, '_elevation_field', return_value=field):
                operational = calculator.calculate(
                    'map-1', Point(10, 20), Point(110, 20),
                    '12-pounder Napoleon', 'Shell', calculator.default_method,
                )
                test = calculator.calculate(
                    'map-1', Point(10, 20), Point(110, 20),
                    '12-pounder Napoleon', 'Shell', calculator.default_method,
                    calibration_mode=True,
                )

            self.assertGreater(operational.elevation_degrees, operational.physics_elevation_degrees)
            self.assertEqual(test.elevation_degrees, test.physics_elevation_degrees)
            self.assertEqual(test.elevation_source, 'calibration_test')
            self.assertTrue(test.calibration_mode)

    def test_matching_local_impacts_do_not_override_clearance_elevation(self):
        with tempfile.TemporaryDirectory() as directory:
            calculator = make_test_calculator(Path(directory))
            gun = Point(10, 20)
            target = Point(110, 20)
            events = []
            for index, (angle, shot_range) in enumerate([
                (-0.14, 83.0), (-0.12, 88.0), (-0.10, 93.0)
            ]):
                events.append({
                    'event': 'observed_impact', 'impact_id': str(index),
                    'actual_elevation_degrees': angle,
                    'observed_range_yards': shot_range,
                    'shot': {
                        'map': {'battlefield': 'TestField', 'mode': 'Conquest', 'layer': ''},
                        'gun_pixel': {'x': 10, 'y': 20},
                        'result': {'cannon': '3-inch Ordnance', 'projectile': 'Shell',
                                   'bearing_degrees': 90},
                    },
                })
            with patch('worcalc.web.service.read_observed_impacts', return_value=events):
                result = calculator.calculate(
                    'map-1', gun, target, '3-inch Ordnance', 'Shell',
                    calculator.default_method,
                )

            self.assertEqual(result.elevation_source, 'physics')
            self.assertEqual(result.calibration_sample_count, 3)
            self.assertEqual(result.elevation_degrees, result.physics_elevation_degrees)

    def test_unified_service_uses_physical_flight_time_for_uphill_target(self):
        from worcalc.domain.ballistic_solution import BallisticSolutionEngine
        with tempfile.TemporaryDirectory() as directory:
            calculator = make_test_calculator(Path(directory))
            field = Mock(samples=())
            field.elevation_at.side_effect = (100,110)
            with patch.object(calculator, '_elevation_field', return_value=field):
                result = calculator.calculate('map-1',Point(10,20),Point(110,20),
                                              '12-pounder Napoleon','Case',calculator.default_method)
            engine = BallisticSolutionEngine(calculator.ballistics_csv)
            engine.set_weapon('12-pounder Napoleon','Case')
            state = engine.physics.at_distance(result.horizontal_range_yards,result.elevation_degrees)
            self.assertAlmostEqual(state[0],10,places=6)
            self.assertAlmostEqual(result.fuze_seconds,state[1],places=8)

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
            self.assertIsNone(result.clearance_status)
            self.assertIsNone(result.height_above_target_metres)

    def test_calculates_terrain_clearance_and_height_over_target(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            calculator = make_test_calculator(root)
            add_test_locations(root)

            result = calculator.calculate(
                "map-1",
                Point(10, 20),
                Point(110, 20),
                "3-inch Ordnance",
                "Shell",
                calculator.default_method,
            )

            self.assertIn(result.clearance_status, {"clear", "obstructed"})
            self.assertIsNotNone(result.height_above_target_metres)
            self.assertIsNotNone(result.elevation_degrees)

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
