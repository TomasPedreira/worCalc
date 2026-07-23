"""Download and organize the public WarTool map catalogue."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from urllib.request import Request, urlopen

from PySide6.QtGui import QImage

API_URL = "https://api.wortool.com/v2/maps/verbose/"
INVALID_WINDOWS_CHARS = re.compile(r'[<>:"/\\|?*]')


def safe_name(value: str) -> str:
    cleaned = INVALID_WINDOWS_CHARS.sub("-", value)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    return cleaned or "Unnamed Map"


def general_map(record: dict) -> str:
    campaign = record.get("campaign", "").strip()
    name = record.get("name", "").lower()
    if campaign.startswith("Antietam") or "antietam" in name:
        return "Antietam"
    if campaign.startswith("Harpers Ferry") or "harpers ferry" in name:
        return "Harpers Ferry"
    if campaign.startswith("South Mountain") or "south mountain" in name:
        return "South Mountain"
    if campaign.startswith("Drill Camp") or "drill camp" in name:
        return "CSADrillCamp"
    return safe_name(campaign or "Other")


def expanded_images(record: dict) -> list[tuple[str, str]]:
    urls = [url.strip() for url in record.get("map_image", "").split(",") if url.strip()]
    if len(urls) <= 1:
        return [(safe_name(record["name"]), urls[0])] if urls else []
    base = safe_name(record["name"])
    return [(f"{base} Overview", urls[0])] + [
        (f"{base} {index:02d}", url) for index, url in enumerate(urls[1:], start=1)
    ]


def fetch_json(url: str) -> list[dict]:
    request = Request(url, headers={"User-Agent": "worCalc map importer/1.0"})
    with urlopen(request, timeout=30) as response:
        return json.load(response)


def fetch_bytes(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": "worCalc map importer/1.0"})
    with urlopen(request, timeout=30) as response:
        return response.read()


def import_maps(maps_dir: Path, force: bool = False) -> tuple[int, int]:
    downloaded = 0
    skipped = 0
    for record in fetch_json(API_URL):
        parent = maps_dir / general_map(record)
        for map_name, image_url in expanded_images(record):
            map_dir = parent / map_name
            image_path = map_dir / f"{map_name}.png"
            source_path = map_dir / "source.json"
            if image_path.exists() and not force:
                skipped += 1
                continue
            image = QImage.fromData(fetch_bytes(image_url))
            if image.isNull():
                raise RuntimeError(f"WarTool returned an unsupported image for {map_name}: {image_url}")
            map_dir.mkdir(parents=True, exist_ok=True)
            if not image.save(str(image_path), "PNG"):
                raise RuntimeError(f"Could not save {image_path}")
            source_path.write_text(
                json.dumps(
                    {
                        "provider": "WarTool",
                        "api": API_URL,
                        "id": record.get("id"),
                        "name": record.get("name"),
                        "campaign": record.get("campaign"),
                        "image_url": image_url,
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            downloaded += 1
            print(f"Downloaded {parent.name} / {map_name}")
    return downloaded, skipped


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--maps-dir",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "maps",
    )
    parser.add_argument("--force", action="store_true", help="Replace existing downloaded maps")
    args = parser.parse_args()
    downloaded, skipped = import_maps(args.maps_dir, args.force)
    print(f"Finished: {downloaded} downloaded, {skipped} already present")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
