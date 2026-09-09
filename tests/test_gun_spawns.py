import struct
import tempfile
import unittest
import zipfile
import zlib
from dataclasses import replace
from pathlib import Path

from worcalc.domain.calibration import AffineCalibration
from worcalc.maps.catalog import MapRecord
from worcalc.maps.entities import locations_for_map
from worcalc.maps.gun_spawns import parse_gun_spawns


def compiled_level(layers):
    """Construct a small CGB fixture, with offsets and non-adjacent fields."""
    data = bytearray(b"CGB " + bytes(4))

    def uint(value):
        data.extend(struct.pack("<I", value))

    def write(value):
        start = len(data)
        if isinstance(value, dict):
            uint(len(value))
            uint(0)
            entries = []
            for key, child in value.items():
                target = write(child) if isinstance(child, (dict, list, str)) else None
                entries.append((key, child, target))
            struct.pack_into("<I", data, start + 4, (len(data) - start - 4) // 4)
            for key, child, target in entries:
                slot = len(data)
                uint(zlib.crc32(key.encode()))
                if target is not None:
                    uint(slot - target)
                elif isinstance(child, float):
                    data.extend(struct.pack("<f", child))
                else:
                    uint(child)
        elif isinstance(value, list):
            uint(len(value) << 10)
            uint(1)
            slots = len(data)
            data.extend(bytes(4 * len(value)))
            for index, child in enumerate(value):
                target = write(child)
                slot = slots + 4 * index
                struct.pack_into("<I", data, slot, (target - slot) // 4)
        else:
            data.extend(value.encode() + b"\0")
            while len(data) % 4:
                data.append(0)
        return start

    write({"layers": layers})
    struct.pack_into("<I", data, 4, len(data) - 8)
    return bytes(data)


def gun(name="Entity-1", archetype=3437346673, x=20.0):
    return {"name": name, "archetype_id": archetype,
            "position": {"y": 30.0, "z": 4.0, "x": x}}


class GunSpawnTests(unittest.TestCase):
    def test_archetype_identifies_generic_names_and_excludes_scenery_and_limbers(self):
        data = compiled_level([{"name": "skirmish", "children": [
            {"name": "Skirmish_Test", "entities": [
                gun(), gun("3InchOrdnanceRifle-scenery", 123),
                gun("Limber", 265807537), gun("Parrott", 2197219489)]}]}])
        result = parse_gun_spawns(data)
        self.assertEqual([g.name for g in result], ["Entity-1", "Parrott"])
        self.assertEqual(result[0].layers, ("skirmish", "Skirmish_Test"))
        self.assertEqual((result[0].world_x, result[0].world_y, result[0].elevation),
                         (20, 30, 4))

    def test_scenario_filter_projection_and_bounds(self):
        data = compiled_level([{"name": "skirmish", "children": [
            {"name": "Skirmish_Test", "entities": [gun(), gun("Outside", x=900.0)]},
            {"name": "Skirmish_Other", "entities": [gun("Other scenario")]}]}])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "Test").mkdir()
            with zipfile.ZipFile(root / "Test" / "level.pak", "w") as archive:
                archive.writestr("objects.cgb", data)
            record = MapRecord("Test", root / "map.png", "Test", "Skirmish", 0,
                               100, 100, 0, AffineCalibration(2, 0, 0, 2),
                               "Skirmish_Test", 10, 10)
            locations = locations_for_map(record, 100, 100, root)
            self.assertEqual(len(locations), 1)
            self.assertEqual(locations[0].kind, "gun_spawn")
            self.assertEqual((locations[0].pixel_x, locations[0].pixel_y), (5, 10))
            self.assertIsNone(locations[0].faction)
            self.assertEqual(locations_for_map(replace(record, layer="Unknown"), 100, 100, root), [])

    def test_real_drill_camp_has_four_starting_guns_in_each_camp(self):
        from worcalc.maps.catalog import load_map_catalog
        root = Path(__file__).resolve().parents[1] / "paks"
        if not (root / "DrillCamp" / "level.pak").exists():
            self.skipTest("Local game assets unavailable")
        records = [r for r in load_map_catalog(root / "gameplay_area_calibrations.json")
                   if r.mode == "DrillCamp"]
        self.assertEqual(len(records), 2)
        for record in records:
            markers = [m for m in locations_for_map(record, 2048, 2048, root)
                       if m.kind == "gun_spawn"]
            self.assertEqual(len(markers), 4)

    def test_bad_offsets_and_nonfinite_positions_are_rejected(self):
        valid = compiled_level([{"name": "Test", "entities": [gun()]}])
        broken = bytearray(valid)
        struct.pack_into("<I", broken, 12, 0xFFFFFFFF)
        for data in [b"not CGB", valid[:-4], bytes(broken),
                     compiled_level([{"name": "Test", "entities": [gun(x=float('nan'))]}])]:
            with self.subTest(data=data[:16]), self.assertRaises(ValueError):
                parse_gun_spawns(data)

    def test_desktop_gun_marker_is_static_square_with_clear_tooltip(self):
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QApplication, QGraphicsRectItem
        from worcalc.maps.entities import MapLocation
        from worcalc.ui.map_view import MapView
        app = QApplication.instance() or QApplication([])
        view = MapView(lambda point: None)
        try:
            view.set_location_markers([MapLocation("Parrott", 20, 30, "gun_spawn", None)])
            item = view._location_items[0]
            self.assertIsInstance(item, QGraphicsRectItem)
            self.assertEqual(item.rect().width(), 5)
            self.assertEqual(item.pen().widthF(), 1)
            self.assertEqual(item.acceptedMouseButtons(), Qt.MouseButton.NoButton)
            self.assertIn("before movement", item.toolTip())
        finally:
            view.close()


if __name__ == "__main__":
    unittest.main()
