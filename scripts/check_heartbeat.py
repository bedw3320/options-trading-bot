#!/usr/bin/env python3
"""Fail if the Mini heartbeat is stale or the Gateway is logged out.

Reads heartbeat/status.json (as pushed to the `heartbeat` branch). No network,
no secrets. Used by .github/workflows/mini-heartbeat.yml.

    python3 scripts/check_heartbeat.py path/to/status.json
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

MAX_AGE = timedelta(minutes=45)


def check(status: dict, *, now: datetime | None = None) -> list[str]:
    """Return human-readable failure reasons (empty => ok)."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    errors: list[str] = []
    if status.get("gateway_logged_in") is not True:
        errors.append(f"gateway_logged_in={status.get('gateway_logged_in')!r} (want true)")
    raw = status.get("last_check")
    if not raw:
        errors.append("last_check missing")
        return errors
    try:
        ts = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        errors.append(f"last_check not parseable: {raw!r}")
        return errors
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    age = now - ts
    if age > MAX_AGE:
        errors.append(
            f"last_check {raw} is {age.total_seconds() / 60:.1f} min old (max {int(MAX_AGE.total_seconds() / 60)})"
        )
    return errors


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if not args:
        print("usage: check_heartbeat.py path/to/status.json", file=sys.stderr)
        return 2
    path = Path(args[0])
    if not path.is_file():
        print(f"FAIL {path} does not exist (Mini has not published a heartbeat)", file=sys.stderr)
        return 1
    try:
        status = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        print(f"FAIL {path} is not JSON: {exc}", file=sys.stderr)
        return 1
    if not isinstance(status, dict):
        print(f"FAIL {path} is not a JSON object", file=sys.stderr)
        return 1
    errors = check(status)
    if errors:
        print("FAIL Mini heartbeat:")
        for e in errors:
            print(f"  - {e}")
        return 1
    print(
        f"OK last_check={status.get('last_check')} "
        f"gateway_logged_in={status.get('gateway_logged_in')} "
        f"account={status.get('account')}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
