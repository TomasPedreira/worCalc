"""Repository data paths shared by application entry points."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
PAKS_DIR = PROJECT_ROOT / "paks"
MAPS_DIR = PAKS_DIR / "converted_minimaps"
BALLISTICS_CSV = PROJECT_ROOT / "war_of_rights_ballistic_ranges.csv"
