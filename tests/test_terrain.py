import struct
import tempfile
import unittest
import zipfile
from dataclasses import replace
from pathlib import Path

from worcalc.domain.calibration import AffineCalibration, METRES_TO_YARDS, Point
from worcalc.maps.elevation import TerrainElevationField, elevation_field_for_map
from worcalc.maps.terrain import TerrainFormatError, decode_terrain, terrain_for_battlefield
from tests.test_web_service import make_test_calculator


def terrain_bytes(size=4, sector=2, coarse=False, hole=False):
    """Small version-28 asset: asymmetric plane z = 10 + 2*x + 3*y."""
    payload = bytearray(struct.pack('<3i', 0, 0, 0))

    def align():
        payload.extend(b'\xde' * (-len(payload) % 4))

    def node(x, y, width):
        leaf = width == sector
        n = (2 if coarse else sector + 1) if leaf else 0
        payload.extend(struct.pack('<2h8f2i', 7, int(hole), x, y, 0, x+width, y+width,
                                   100, 10.03, 100/65520, n, 1))
        if leaf:
            for ix in range(n):
                for iy in range(n):
                    wx, wy = x + ix*width/(n-1), y + iy*width/(n-1)
                    height_steps = round((2*wx + 3*wy)*20)
                    surface = 15 if hole and ix == 0 and iy == 0 else 3
                    payload.extend(struct.pack('<H', height_steps << 4 | surface))
        align()
        payload.extend(b'\0' * ((sector.bit_length()-1)*4))
        payload.append(3)
        align()
        if not leaf:
            half = width//2
            for dx, dy in ((0,0),(half,0),(0,half),(half,half)):
                node(x+dx,y+dy,half)

    node(0,0,size)
    return struct.pack('<4B5i2f',28,0,6,0,32+len(payload),size,1,sector,size//sector,1,0)+payload


class TerrainTests(unittest.TestCase):
    def test_sector_order_axis_order_and_height_quantization(self):
        terrain = decode_terrain(terrain_bytes())
        self.assertEqual(len(terrain.tiles),4)
        for x,y in ((0,0),(1,0),(0,1),(2,0),(0,2),(2,2),(3.75,3.5)):
            self.assertAlmostEqual(terrain.elevation_at(x,y),10+2*x+3*y)
        self.assertAlmostEqual(terrain.elevation_at(1.999999,1),terrain.elevation_at(2,1),places=5)

    def test_coarse_sectors_expand_to_unit_grid(self):
        terrain = decode_terrain(terrain_bytes(coarse=True))
        self.assertAlmostEqual(terrain.elevation_at(.25,1.25),14.25)

    def test_uses_triangles_instead_of_bilinear_smoothing(self):
        data = bytearray(terrain_bytes(size=2))
        # Single raised vertex in a saddle cell. Heights are X-major.
        start = 32+12+44
        for index in range(9):
            struct.pack_into('<H',data,start+2*index,3)
        struct.pack_into('<H',data,start+2*4,200 << 4 | 3)
        terrain=decode_terrain(bytes(data))
        self.assertAlmostEqual(terrain.elevation_at(.25,.25),10)
        self.assertAlmostEqual(terrain.elevation_at(.75,.75),15)

    def test_holes_and_outside_coordinates_are_unknown(self):
        terrain=decode_terrain(terrain_bytes(hole=True))
        for x,y in ((.2,.2),(-1,1),(4,1),(1,4),(float('nan'),1)):
            self.assertIsNone(terrain.elevation_at(x,y))
        self.assertIsNotNone(terrain.elevation_at(1,1))

    def test_rejects_corrupt_and_unsupported_data(self):
        original=terrain_bytes()
        cases=[b'', original[:-1]]
        for offset,fmt,value in ((0,'B',29),(2,'B',7),(12,'i',0),
                                  (32,'i',-1),(44,'h',8),(44+36,'i',100000)):
            data=bytearray(original);struct.pack_into('<'+fmt,data,offset,value);cases.append(bytes(data))
        for data in cases:
            with self.subTest(data=data[:16]):
                with self.assertRaises(TerrainFormatError):decode_terrain(data)

    def test_archive_loader_and_map_projection_prefer_native_terrain(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            calculator=make_test_calculator(root)
            record=replace(calculator.map_record('map-1'),
                           calibration=AffineCalibration(0,.01,-.01,0),
                           top_left_x_metres=3,top_left_y_metres=.5)
            archive=root/'paks'/'TestField'/'level.pak';archive.parent.mkdir()
            with zipfile.ZipFile(archive,'w') as z:z.writestr('terrain/terrain.dat',terrain_bytes())
            field=elevation_field_for_map(record,200,150,root/'paks')
            self.assertIsInstance(field,TerrainElevationField)
            self.assertTrue(field.samples)
            self.assertEqual(field.source,'compiled terrain')
            self.assertAlmostEqual(field.elevation_at(Point(50,100)),17)
            self.assertIs(field.terrain,terrain_for_battlefield(root/'paks','TestField'))
            profile=field.profile_along_line(Point(0,0),Point(100,100),2**.5*METRES_TO_YARDS)
            self.assertEqual(len(profile),3)
            self.assertAlmostEqual(profile[-1].elevation_metres,18.5)

    def test_missing_terrain_preserves_legacy_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            calculator=make_test_calculator(Path(directory))
            field=elevation_field_for_map(calculator.map_record('map-1'),200,150,calculator.paks_root)
            self.assertEqual(field.source,'object anchors')
            self.assertIsNone(field.elevation_at(Point(1,1)))

    def test_real_battlefields_decode_when_assets_available(self):
        root=Path(__file__).resolve().parents[1]/'paks'
        if not (root/'Antietam'/'level.pak').exists():self.skipTest('Local game assets not installed')
        for name in ('Antietam','DrillCamp','HarpersFerry','SouthMountain'):
            with self.subTest(battlefield=name):
                terrain=terrain_for_battlefield(root,name)
                self.assertEqual(len(terrain.tiles),16384)
                self.assertEqual(terrain.width_metres,4096)
                self.assertEqual(terrain.unit_metres,1)
                self.assertTrue(0 < terrain.elevation_at(1000,1000) < 500)
