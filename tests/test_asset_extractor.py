import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from PIL import Image

from worcalc.maps.asset_extractor import extract_assets, resolve_assets_directory


class AssetExtractorTests(unittest.TestCase):
    def test_extracts_runtime_map_data_directly_from_assets_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            assets = root / "WarOfRights" / "Assets"
            assets.mkdir(parents=True)
            level_source = assets / "Levels" / "Antietam" / "level.pak"
            level_source.parent.mkdir(parents=True)
            level_source.write_bytes(b"synthetic level archive")

            texture_data = io.BytesIO()
            image = Image.new("RGBA", (4, 4), (0, 0, 0, 137))
            image.save(texture_data, format="DDS")
            with zipfile.ZipFile(
                assets / "Minimaps_Antietam.pak", "w"
            ) as archive:
                archive.writestr(
                    "Generated/Maps/Antietam/Conquest/GameplayArea_0.dds",
                    texture_data.getvalue(),
                )

            definition = {
                "Components": [
                    {
                        "Type": "GameplayAreaManager",
                        "GameplayAreas": [
                            {
                                "Name": "Test Map",
                                "Layer": "test",
                                "Descriptors": [
                                    {
                                        "Type": "UserInterfaceDescriptor",
                                        "Map": {
                                            "TopLeftX": 0,
                                            "TopLeftY": 100,
                                            "TopRightX": 100,
                                            "TopRightY": 100,
                                            "BottomRightX": 100,
                                            "BottomRightY": 0,
                                        },
                                    }
                                ],
                            }
                        ],
                    }
                ]
            }
            with zipfile.ZipFile(assets / "LevelsLooseFiles.pak", "w") as archive:
                archive.writestr(
                    "Levels/Antietam/Definitions/Conquest.json",
                    json.dumps(definition),
                )

            output = root / "runtime" / "paks"
            count = extract_assets(root / "WarOfRights", output)

            self.assertEqual(count, 1)
            self.assertEqual(resolve_assets_directory(assets), assets)
            converted = (
                output
                / "converted_minimaps"
                / "Antietam"
                / "Generated"
                / "Maps"
                / "Antietam"
                / "Conquest"
                / "GameplayArea_0.png"
            )
            self.assertTrue(converted.is_file())
            with Image.open(converted) as converted_image:
                self.assertEqual(converted_image.mode, "L")
                self.assertEqual(converted_image.getpixel((0, 0)), 137)
            self.assertEqual(
                (output / "Antietam" / "level.pak").read_bytes(),
                level_source.read_bytes(),
            )
            catalog = json.loads(
                (output / "gameplay_area_calibrations.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(catalog[0]["name"], "Test Map")
            self.assertEqual(
                catalog[0]["pak_path"],
                "paks/converted_minimaps/Antietam/Generated/Maps/"
                "Antietam/Conquest/GameplayArea_0.png",
            )

    def test_rejects_path_without_assets_archive(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(FileNotFoundError):
                resolve_assets_directory(Path(temporary))


if __name__ == "__main__":
    unittest.main()
