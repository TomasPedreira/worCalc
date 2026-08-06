import tempfile
import unittest
from io import BytesIO
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from worcalc.web.app import create_app
from tests.test_web_service import ROOT, add_test_locations, make_test_calculator


class WebApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        calculator = make_test_calculator(self.root)
        self.app = create_app(
            calculator.maps_dir,
            ROOT / "war_of_rights_ballistic_ranges.csv",
            calculator.paks_root,
        )
        self.client = TestClient(self.app)

    def tearDown(self) -> None:
        self.client.close()
        self.temporary_directory.cleanup()

    def test_serves_page_map_catalog_and_image(self) -> None:
        page = self.client.get("/")
        self.assertEqual(page.status_code, 200)
        self.assertIn("MOBILE FIRE DIRECTION", page.text)
        self.assertIn('id="gun-mode"', page.text)
        self.assertIn('id="target-mode"', page.text)
        self.assertIn('id="mode-pill" role="status" aria-live="polite"', page.text)
        self.assertNotIn('id="pan-mode"', page.text)
        self.assertNotIn('id="zoom-in"', page.text)
        self.assertNotIn('id="zoom-out"', page.text)
        self.assertNotIn('id="solve"', page.text)
        self.assertNotIn('id="clear"', page.text)
        self.assertEqual(page.text.count('id="elevation"'), 1)
        self.assertEqual(page.text.count('id="fuze"'), 1)
        script = self.client.get("/static/app.js")
        self.assertEqual(script.status_code, 200)
        self.assertIn("baseScale = Math.min(", script.text)
        self.assertIn("(rect.width - scaledWidth) / 2", script.text)
        self.assertIn("const MAX_ZOOM = 12", script.text)
        self.assertIn('group.className = "map-group"', script.text)
        self.assertIn("function battlefieldLabel(name)", script.text)
        self.assertIn("function rebaseRemainingPointer()", script.text)
        self.assertIn("startTranslation = {x:translateX, y:translateY}", script.text)
        self.assertIn('toggle.setAttribute("aria-expanded", String(expanded))', script.text)
        self.assertIn("modeGroups.hidden = !expanded", script.text)
        self.assertIn('modeToggle.setAttribute("aria-expanded", String(modeExpanded))', script.text)
        self.assertIn("mapCards.hidden = !modeExpanded", script.text)
        self.assertIn("function prefetchSkirmishThumbnails(battlefield)", script.text)
        self.assertIn("function loadMapImage(map)", script.text)
        self.assertIn('modePill.textContent = "LOADING SELECTED MAP..."', script.text)
        self.assertIn('modePill.textContent = "SELECTED MAP FAILED TO LOAD"', script.text)
        self.assertIn('modePill.textContent = "CALCULATING FIRE SOLUTION..."', script.text)
        self.assertIn('mapWrap.classList.add("solution-loading")', script.text)
        self.assertIn('mapWrap.classList.remove("solution-loading")', script.text)
        self.assertIn("if (loadThumbnail) image.src = map.thumbnail_url", script.text)
        self.assertIn("if (nextBattlefield) prefetchSkirmishThumbnails(nextBattlefield)", script.text)
        self.assertIn('if (gameMode.toLowerCase() !== "skirmish") cancelThumbnailPrefetch()', script.text)
        self.assertIn("if (shouldRequestSolution && gun && target) requestSolution()", script.text)
        move_marker = script.text.split("function moveMarker", 1)[1].split(
            "function locationClass", 1
        )[0]
        self.assertNotIn("clearSolution()", move_marker)
        request_solution = script.text.split("async function requestSolution", 1)[1].split(
            "window.addEventListener", 1
        )[0]
        self.assertNotIn("clearSolution()", request_solution)
        maps = self.client.get("/api/maps")
        self.assertEqual(maps.status_code, 200)
        self.assertEqual(maps.json()[0]["identifier"], "map-1")
        self.assertEqual(
            maps.json()[0]["image_url"],
            "/api/maps/map-1/image?style=parchment&format=webp",
        )
        self.assertEqual(
            maps.json()[0]["thumbnail_url"],
            "/api/maps/map-1/thumbnail",
        )

        image = self.client.get("/api/maps/map-1/image")
        self.assertEqual(image.status_code, 200)
        self.assertEqual(image.headers["content-type"], "image/png")
        with Image.open(BytesIO(image.content)) as styled:
            self.assertEqual(styled.getpixel((0, 0)), (133, 120, 86))
        self.assertEqual(image.headers["cache-control"], "private, max-age=604800")

        webp_image = self.client.get(
            "/api/maps/map-1/image?style=parchment&format=webp"
        )
        self.assertEqual(webp_image.status_code, 200)
        self.assertEqual(webp_image.headers["content-type"], "image/webp")
        with Image.open(BytesIO(webp_image.content)) as selected_map:
            self.assertEqual(selected_map.size, (200, 150))

        thumbnail = self.client.get("/api/maps/map-1/thumbnail")
        self.assertEqual(thumbnail.status_code, 200)
        self.assertEqual(thumbnail.headers["content-type"], "image/webp")
        self.assertEqual(thumbnail.headers["cache-control"], "private, max-age=604800")
        with Image.open(BytesIO(thumbnail.content)) as preview:
            self.assertEqual(preview.size, (200, 150))

        select_map = script.text.split("async function selectMap", 1)[1].split(
            "function updatePhysics", 1
        )[0]
        self.assertNotIn("expandedBattlefield = map.battlefield", select_map)
        self.assertNotIn("expandedModes.set(map.battlefield, map.mode)", select_map)

        raw_image = self.client.get("/api/maps/map-1/image?style=raw")
        with Image.open(BytesIO(raw_image.content)) as raw:
            self.assertEqual(raw.getpixel((0, 0)), 128)

    def test_exposes_options_and_calculates_solution(self) -> None:
        options = self.client.get("/api/options").json()
        self.assertEqual(
            options["physics"]["3-inch Ordnance"]["Shell"],
            {"speed": 370.0, "drag": 0.1},
        )
        response = self.client.post("/api/solutions", json={
            "map_id": "map-1",
            "gun": {"x": 10, "y": 20},
            "target": {"x": 110, "y": 20},
            "cannon": options["defaults"]["cannon"],
            "projectile": options["defaults"]["projectile"],
            "method": options["defaults"]["method"],
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["bearing_direction"], "E")
        self.assertGreater(response.json()["fuze_seconds"], 0)

    def test_exposes_projected_map_locations(self) -> None:
        add_test_locations(self.root)

        response = self.client.get("/api/maps/map-1/locations")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [item["kind"] for item in response.json()],
            ["battery", "objective"],
        )

    def test_returns_useful_errors_for_bad_requests(self) -> None:
        response = self.client.post("/api/solutions", json={
            "map_id": "missing",
            "gun": {"x": 10, "y": 20},
            "target": {"x": 110, "y": 20},
            "cannon": "3-inch Ordnance",
            "projectile": "Shell",
            "method": "Cubic fit",
        })

        self.assertEqual(response.status_code, 404)
        self.assertIn("Unknown map", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
