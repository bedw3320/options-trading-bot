"""IB execution timestamps are UTC; persist America/New_York (ET)."""

from __future__ import annotations

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
UTC = timezone.utc


def ib_exec_time_to_et(value: datetime | date | str | None) -> datetime | None:
    """Convert an IB fill/execution time to aware ET.

    Naive datetimes and IB strings without a zone are treated as UTC.
    Unset / epoch values return None.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        if dt.year < 1980:
            return None
        return dt.astimezone(ET)
    if isinstance(value, date) and not isinstance(value, datetime):
        if value.year < 1980:
            return None
        return datetime(value.year, value.month, value.day, tzinfo=UTC).astimezone(ET)

    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + " UTC"

    dt: datetime
    if text.count(" ") >= 2 and "  " not in text:
        day, clock, zone = text.split(" ", 2)
        dt = datetime.strptime(day + clock, "%Y%m%d%H:%M:%S")
        tz_name = "UTC" if zone.upper() == "UTC" else zone
        dt = dt.replace(tzinfo=ZoneInfo(tz_name))
    elif "T" in text:
        iso = text.replace("Z", "+00:00")
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
    else:
        compact = text.replace("-", "").replace(" ", "")
        if len(compact) >= 15 and ":" in compact:
            dt = datetime.strptime(compact[:16], "%Y%m%d%H:%M:%S").replace(tzinfo=UTC)
        elif len(compact) == 8 and compact.isdigit():
            dt = datetime.strptime(compact, "%Y%m%d").replace(tzinfo=UTC)
        else:
            raise ValueError(f"unrecognized IB datetime: {value!r}")
    if dt.year < 1980:
        return None
    return dt.astimezone(ET)


def format_time_et(value: datetime | date | str | None) -> str | None:
    et = ib_exec_time_to_et(value)
    return et.isoformat() if et else None
