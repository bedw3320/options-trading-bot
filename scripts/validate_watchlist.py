#!/usr/bin/env python3
"""CI / local lint for strategies/watchlist.yaml.

Fails if:
  - a non-SPY entry lacks sources
  - a falsifier is a leftover string, or lacks threshold / source / expiry
  - any name is `active` without `approved_by: will` and `approved_on`
    (only Will sets this marker)
  - v0 cap is breached (>3 record_only names, or >1 theme among them)

    uv run python scripts/validate_watchlist.py
    uv run python scripts/validate_watchlist.py path/to/watchlist.yaml
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from schemas.watchlist import load_watchlist, lint_watchlist  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    path = Path(args[0] if args else "strategies/watchlist.yaml")
    try:
        wl = load_watchlist(path)
    except Exception as exc:
        print(f"FAIL {path}: {exc}", file=sys.stderr)
        return 1
    errors = lint_watchlist(wl)
    if errors:
        print(f"FAIL {path} ({len(errors)} error(s))", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        print(
            "Note: only Will may set approved_by: will (+ approved_on) to mark a name active.",
            file=sys.stderr,
        )
        return 1
    print(f"OK {path} ({len(wl.names)} names)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
