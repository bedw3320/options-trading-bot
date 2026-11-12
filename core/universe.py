"""US large-cap universe for the in-force standard RR.

Source is the S&P 500 list in data/sp500.txt plus an optional YAML overlay.
Never reads strategies/watchlist.yaml (theme watchlist is a later PR).
"""

from __future__ import annotations

from pathlib import Path

from schemas.strategy import DeterministicRules

ROOT = Path(__file__).resolve().parents[1]
SP500_PATH = ROOT / "data" / "sp500.txt"
WATCHLIST_FORBIDDEN = ROOT / "strategies" / "watchlist.yaml"


def load_sp500(path: Path | None = None) -> list[str]:
    text = (path or SP500_PATH).read_text()
    out: list[str] = []
    seen: set[str] = set()
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip().upper()
        if not line or line in seen:
            continue
        seen.add(line)
        out.append(line)
    if not out:
        raise ValueError(f"empty S&P 500 universe file: {path or SP500_PATH}")
    return out


def occ_root(occ: str) -> str:
    if len(occ) > 15:
        return occ[:-15]
    return occ


def name_key(ticker: str) -> str:
    """Compare underlyings across Yahoo (BRK.B), IB (BRK B), and OCC (BRKB)."""
    return (ticker or "").replace(".", "").replace(" ", "").upper()


def position_underlying(position: dict) -> str:
    legs = position.get("legs") or []
    if not legs:
        return ""
    occ = str(legs[0].get("occ") or "")
    return occ_root(occ)


def open_underlyings(positions: list[dict]) -> set[str]:
    return {position_underlying(p) for p in positions if position_underlying(p)}


def vendor_symbol(ticker: str, *, vendor: str) -> str:
    """Map Yahoo-style tickers to vendor roots (BRK.B → BRK B / BRKB)."""
    t = ticker.strip().upper()
    if vendor == "ib":
        return t.replace(".", " ")
    if vendor in ("cboe", "alpaca"):
        return t.replace(".", "")
    return t


def resolve_universe(rules: DeterministicRules, provider: object | None = None) -> list[str]:
    """Tickers to scan. Fixture providers may narrow to snapshots they actually have."""
    if rules.universe is None and rules.underlying:
        wanted = [rules.underlying.strip().upper()]
    else:
        overlay = [t.strip().upper() for t in (rules.universe.tickers if rules.universe else []) if t.strip()]
        wanted = overlay or load_sp500()
    listed = None
    fn = getattr(provider, "listed_underlyings", None)
    if callable(fn):
        listed = fn()
    if listed:
        listed_u = [str(t).strip().upper() for t in listed if str(t).strip()]
        inter = [t for t in wanted if t in listed_u]
        return inter if inter else listed_u
    return wanted
