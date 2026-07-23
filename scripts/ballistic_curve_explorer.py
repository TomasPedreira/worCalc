"""Development entry point for the ballistics explorer UI."""

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from worcalc.ui.ballistics_explorer import main


if __name__ == "__main__":
    raise SystemExit(main())
