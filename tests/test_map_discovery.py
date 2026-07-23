import json
import tempfile
import unittest
from pathlib import Path

from paks.extract_gameplay_calibrations import should_include_map_group
from worcalc.app import discover_maps


class MapDiscoveryTests(unittest.TestCase):
    def test_excludes_harpers_ferry_drill_camp_asset_group(self):
        self.assertFalse(should_include_map_group("HarpersFerry", "DrillCamp"))
        self.assertTrue(should_include_map_group("DrillCamp", "DrillCamp"))
        self.assertTrue(should_include_map_group("HarpersFerry", "Skirmish"))

    def test_loads_named_maps_and_transforms_from_pak_catalog(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            maps_dir = root / "paks" / "converted_minimaps"
            maps_dir.mkdir(parents=True)
            image = maps_dir / "alpha.png"
            image.touch()
            row = {
                "battlefield": "Antietam",
                "mode": "Conquest",
                "gameplay_area": 0,
                "name": "Smokestacks",
                "width_m": 1000,
                "height_m": 900,
                "rotation_degrees": -52.5,
                "pak_path": str(image),
                "pak_pixel_x_to_world_x_m": 0.4,
                "pak_pixel_x_to_world_y_m": -0.5,
                "pak_pixel_y_to_world_x_m": -0.5,
                "pak_pixel_y_to_world_y_m": -0.4,
            }
            (root / "paks" / "gameplay_area_calibrations.json").write_text(
                json.dumps([row]), encoding="utf-8"
            )

            records = discover_maps(maps_dir)

            self.assertEqual([record.name for record in records], ["Smokestacks"])
            self.assertEqual(records[0].tree_parts, ("Antietam", "Conquest", "Smokestacks"))
            self.assertAlmostEqual(records[0].calibration.pixel_x_world_x, 0.4)


if __name__ == "__main__":
    unittest.main()
