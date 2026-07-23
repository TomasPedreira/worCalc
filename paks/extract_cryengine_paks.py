"""Selectively extract the CryEngine PAK files in this directory.

The default ``core`` profile extracts the useful map-analysis payload without
duplicating large AI navigation and cover caches.  Use ``--profile metadata``
for a quick inspection, or ``--profile all`` for a complete extraction.
"""

from __future__ import annotations

import argparse
import json
import shutil
import zipfile
from typing import BinaryIO
from pathlib import Path, PurePosixPath


PAK_ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT = PAK_ROOT / "extracted"
METADATA_SUFFIXES = {".cfg", ".json", ".lst", ".txt", ".xml"}


def wanted(name: str, profile: str) -> bool:
    path = PurePosixPath(name)
    suffix = path.suffix.lower()
    if profile == "all":
        return True
    if suffix in METADATA_SUFFIXES:
        return True
    if profile == "metadata":
        return False
    return name.lower() == "terrain/terrain.dat" or suffix == ".dds"


def safe_destination(root: Path, archive_name: str) -> Path:
    relative = PurePosixPath(archive_name)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"unsafe archive path: {archive_name!r}")
    destination = root.joinpath(*relative.parts)
    destination.resolve().relative_to(root.resolve())
    return destination


def open_cryengine_entry(
    archive: zipfile.ZipFile, info: zipfile.ZipInfo
) -> BinaryIO:
    """Open an entry whose local-header path may use legacy backslashes.

    CryEngine's Windows packer writes forward slashes in the central directory
    but backslashes in local headers. Python 3.12 validates the two names more
    strictly than common archive programs do, so retry with that representation.
    """
    try:
        return archive.open(info)
    except zipfile.BadZipFile as error:
        if "File name in directory" not in str(error) or "/" not in info.orig_filename:
            raise
        original_name = info.orig_filename
        info.orig_filename = original_name.replace("/", "\\")
        try:
            return archive.open(info)
        finally:
            info.orig_filename = original_name


def extract_archive(pak: Path, output: Path, profile: str) -> dict[str, object]:
    battlefield = pak.parent.name
    package = "level" if pak.name.lower() == "level.pak" else "minimaps"
    archive_output = output / battlefield / package
    extracted: list[dict[str, object]] = []
    skipped: list[str] = []

    with zipfile.ZipFile(pak) as archive:
        for info in archive.infolist():
            if info.is_dir() or not wanted(info.filename, profile):
                continue
            destination = safe_destination(archive_output, info.filename)
            if destination.is_file() and destination.stat().st_size == info.file_size:
                skipped.append(info.filename)
            else:
                destination.parent.mkdir(parents=True, exist_ok=True)
                with open_cryengine_entry(archive, info) as source, destination.open(
                    "wb"
                ) as target:
                    shutil.copyfileobj(source, target, length=1024 * 1024)
            extracted.append(
                {
                    "path": info.filename,
                    "size": info.file_size,
                    "compressed_size": info.compress_size,
                    "crc32": f"{info.CRC:08x}",
                }
            )

    return {
        "archive": str(pak.relative_to(PAK_ROOT)),
        "battlefield": battlefield,
        "package": package,
        "profile": profile,
        "files": extracted,
        "already_present": skipped,
        "total_size": sum(int(item["size"]) for item in extracted),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--profile",
        choices=("metadata", "core", "all"),
        default="core",
        help="metadata only, useful terrain/minimap data (default), or everything",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"extraction directory (default: {DEFAULT_OUTPUT})",
    )
    args = parser.parse_args()

    pak_files = sorted(
        path for path in PAK_ROOT.glob("*/*.pak") if path.is_file()
    )
    if not pak_files:
        raise SystemExit(f"No .pak files found below {PAK_ROOT}")

    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    results = [extract_archive(pak, output, args.profile) for pak in pak_files]
    manifest = {
        "format": "CryEngine ZIP-based PAK",
        "profile": args.profile,
        "archives": results,
        "total_files": sum(len(result["files"]) for result in results),
        "total_size": sum(int(result["total_size"]) for result in results),
    }
    manifest_path = output / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Extracted/verified {manifest['total_files']} files")
    print(f"Uncompressed size: {manifest['total_size']:,} bytes")
    print(f"Manifest: {manifest_path}")


if __name__ == "__main__":
    main()
