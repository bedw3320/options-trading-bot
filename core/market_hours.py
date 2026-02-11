"""Market session awareness.

Determines whether a given asset class is currently tradeable
based on market hours and session type.
"""

from __future__ import annotations

from datetime import datetime, time
from typing import Literal
from zoneinfo import ZoneInfo

ET = ZoneInfo("US/Eastern")

# Regular trading hours (US equities/options)
MARKET_OPEN = time(9, 30)
MARKET_CLOSE = time(16, 0)

# Extended hours
PRE_MARKET_OPEN = time(4, 0)
POST_MARKET_CLOSE = time(20, 0)


def _now_et() -> datetime:
    return datetime.now(ET)


def is_market_open() -> bool:
    """Check if US equity market is currently open (regular hours)."""
    now = _now_et()
    if now.weekday() >= 5:  # Saturday=5, Sunday=6
        return False
    return MARKET_OPEN <= now.time() < MARKET_CLOSE


def is_extended_hours() -> bool:
    """Check if pre-market or post-market is active."""
    now = _now_et()
    if now.weekday() >= 5:
        return False
    t = now.time()
    return (PRE_MARKET_OPEN <= t < MARKET_OPEN) or (MARKET_CLOSE < t <= POST_MARKET_CLOSE)


def is_session_active(
    session: str,
    asset_class: Literal["equity", "option", "crypto"] = "equity",
) -> bool:
    """Check if a given session type is active for an asset class.

    Sessions: 'market_hours', 'extended_hours', '24/7', 'pre_market', 'post_market'
    """
    if asset_class == "crypto":
        return True  # crypto trades 24/7

    if session == "24/7":
        return True
    elif session == "market_hours":
        return is_market_open()
    elif session == "extended_hours":
        return is_market_open() or is_extended_hours()
    elif session == "pre_market":
        now = _now_et()
        if now.weekday() >= 5:
            return False
        return PRE_MARKET_OPEN <= now.time() < MARKET_OPEN
    elif session == "post_market":
        now = _now_et()
        if now.weekday() >= 5:
            return False
        return MARKET_CLOSE < now.time() <= POST_MARKET_CLOSE
    else:
        return False


def should_strategy_run(
    active_sessions: list[str],
    asset_classes: list[str],
) -> bool:
    """Check if any active session is currently active for any asset class."""
    for session in active_sessions:
        for ac in asset_classes:
            if is_session_active(session, ac):
                return True
    return False
