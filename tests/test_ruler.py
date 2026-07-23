import unittest

from worcalc.ui.map_view import (
    PARCHMENT_INK,
    PARCHMENT_PAPER,
    parchment_color,
    ruler_distance,
)


class RulerTests(unittest.TestCase):
    def test_converts_fixed_screen_length_to_yards(self):
        self.assertEqual(ruler_distance(2, 2, 140), 140)
        self.assertEqual(ruler_distance(2, 4, 140), 70)

    def test_non_positive_distance_is_hidden(self):
        self.assertEqual(ruler_distance(0, 1), 0)
        self.assertEqual(ruler_distance(1, 0), 0)

    def test_parchment_palette_maps_mask_to_paper_and_ink(self):
        self.assertEqual(parchment_color(0), PARCHMENT_PAPER)
        self.assertEqual(parchment_color(255), PARCHMENT_INK)


if __name__ == "__main__":
    unittest.main()
