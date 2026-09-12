#!/usr/bin/env python3
"""Thin wrapper: uv run python scripts/paper_readiness.py"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.paper_readiness import main

if __name__ == "__main__":
    raise SystemExit(main())
