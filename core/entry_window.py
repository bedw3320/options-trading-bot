"""Entry-window checks use America/Toronto wall clock, never a quote as_of.

Live bug 2026-11-12: 10:00 and 10:15 ET cycles abstained as outside the
entry window because CBOE delayed as_of was 9:44 / 9:59 ET.
"""

from __future__ import annotations

from datetime import datetime, time as dtime, timedelta
from zoneinfo import ZoneInfo

from schemas.strategy import DeterministicRules

WALL_TZ_NAME = "America/Toronto"
WALL_TZ = ZoneInfo(WALL_TZ_NAME)

# Deterministic dry-run clock: Monday 2026-10-19 10:00 America/Toronto (EDT).
DRY_RUN_NOW = datetime(2026, 10, 19, 14, 0, tzinfo=ZoneInfo("UTC"))


def wall_now(now: datetime, tz_name: str = WALL_TZ_NAME) -> datetime:
    if now.tzinfo is None:
        now = now.replace(tzinfo=ZoneInfo("UTC"))
    return now.astimezone(ZoneInfo(tz_name))


def in_entry_slot(now: datetime, rules: DeterministicRules) -> bool:
    """True if `now` (not a quote timestamp) falls in a configured slot."""
    tz_name = rules.execution.entry_timezone or WALL_TZ_NAME
    t = wall_now(now, tz_name)
    if t.weekday() >= 5:
        return False
    slots = tuple(rules.execution.entry_slots_et or ())
    if slots:
        grace = timedelta(minutes=int(rules.execution.entry_slot_grace_minutes))
        for slot in slots:
            hh, mm = (int(x) for x in slot.split(":", 1))
            start = t.replace(hour=hh, minute=mm, second=0, microsecond=0)
            if start <= t <= start + grace:
                return True
        return False
    window = rules.execution.entry_window_et
    if not window:
        return False
    lo, hi = (dtime.fromisoformat(x) for x in window)
    return lo <= t.time() <= hi
