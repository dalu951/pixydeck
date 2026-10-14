#!/usr/bin/env python3
"""Run the installed PixyDeck GPU benchmark from a source checkout."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pixydeck.gpu_benchmark import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
