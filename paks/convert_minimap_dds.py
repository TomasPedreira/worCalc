"""Convert extracted War of Rights minimap DDS alpha channels to PNG.

The CryEngine textures are BC3/DXT5 files whose visible grayscale map is in
the alpha channel; their RGB channels are black. FFmpeg is used because it can
decode the DX10/BC3 DDS variant without adding a Python package dependency.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


PAK_ROOT = Path(__file__).resolve().parent
DEFAULT_SOURCE = PAK_ROOT / "extracted"
DEFAULT_OUTPUT = PAK_ROOT / "converted_minimaps"


def destination_for(source: Path, source_root: Path, output_root: Path) -> Path:
    relative = source.relative_to(source_root)
    parts = list(relative.parts)
    try:
        minimaps_index = parts.index("minimaps")
    except ValueError as error:
        raise ValueError(f"DDS is not below a minimaps directory: {source}") from error
    return output_root.joinpath(parts[0], *parts[minimaps_index + 1 :]).with_suffix(
        ".png"
    )


def convert(ffmpeg: str, source: Path, destination: Path, force: bool) -> str:
    if destination.is_file() and not force:
        return "skipped"
    destination.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(source),
            "-vf",
            "alphaextract",
            "-frames:v",
            "1",
            str(destination),
        ],
        check=True,
    )
    return "converted"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise SystemExit("FFmpeg is required but was not found on PATH")
    if args.jobs < 1:
        raise SystemExit("--jobs must be at least 1")

    source_root = args.source.resolve()
    output_root = args.output.resolve()
    sources = sorted(
        path
        for path in source_root.rglob("*.dds")
        if "minimaps" in path.relative_to(source_root).parts
    )
    if not sources:
        raise SystemExit(f"No extracted minimap DDS files found below {source_root}")

    counts = {"converted": 0, "skipped": 0}
    failures: list[tuple[Path, Exception]] = []
    with ThreadPoolExecutor(max_workers=args.jobs) as executor:
        futures = {
            executor.submit(
                convert,
                ffmpeg,
                source,
                destination_for(source, source_root, output_root),
                args.force,
            ): source
            for source in sources
        }
        for future in as_completed(futures):
            source = futures[future]
            try:
                counts[future.result()] += 1
            except Exception as error:  # report all bad assets after the batch
                failures.append((source, error))

    print(f"Converted: {counts['converted']}; already present: {counts['skipped']}")
    print(f"Output: {output_root}")
    if failures:
        for source, error in failures:
            print(f"FAILED: {source}: {error}")
        raise SystemExit(f"{len(failures)} conversion(s) failed")


if __name__ == "__main__":
    main()
