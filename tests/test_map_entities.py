import struct
import unittest

from worcalc.maps.entities import parse_position_samples, parse_world_entities


def encoded_entity(name: str, elevation: float, world_x: float, world_y: float) -> bytes:
    return (
        b"\xaf\x77\xd2\x62"
        + struct.pack("<f", elevation)
        + b"\x83\x16\xdc\x8c"
        + struct.pack("<f", world_x)
        + b"\x15\x26\xdb\xfb"
        + struct.pack("<f", world_y)
        + name.encode("ascii")
        + b"\x00"
    )


class MapEntityTests(unittest.TestCase):
    def test_keeps_unclassified_positions_for_elevation_diagnostics(self):
        samples = parse_position_samples(
            encoded_entity("EnvironmentProbe_Farm", 70, 100, 200)
        )
        self.assertEqual(len(samples), 1)
        self.assertEqual(samples[0].elevation, 70)

    def test_decodes_and_classifies_compiled_positions(self):
        data = b"header" + encoded_entity(
            "CQ4_Spawnpoint_USA_Artillery_Forward", 58.08, 1451.65, 1901.85
        )
        entities = parse_world_entities(data)
        self.assertEqual(len(entities), 1)
        self.assertEqual(entities[0].kind, "battery")
        self.assertEqual(entities[0].faction, "USA")
        self.assertAlmostEqual(entities[0].world_x, 1451.65, places=2)

    def test_keeps_victory_point_and_ignores_unrelated_objects(self):
        data = encoded_entity("Victory_Conquest_4", 56, 1336, 1557)
        data += encoded_entity("EnvironmentProbe_Farm", 70, 100, 200)
        entities = parse_world_entities(data)
        self.assertEqual(
            [(item.name, item.kind) for item in entities],
            [("Victory_Conquest_4", "objective")],
        )

    def test_recognizes_skirmish_victory_sequence_as_objective(self):
        entities = parse_world_entities(
            encoded_entity("Skirmish_2_VictorySequence", 50, 1000, 2000)
        )
        self.assertEqual(entities[0].kind, "objective")


if __name__ == "__main__":
    unittest.main()
