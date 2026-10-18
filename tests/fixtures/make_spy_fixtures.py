"""Generate SYNTHETIC SPY snapshots for dry-run and tests (Black-Scholes + a skew curve).

Not market data. Numbers are shaped to look like SPY, so the cycle can be exercised
end to end while IB data is blocked. Regenerate:

    uv run python tests/fixtures/make_spy_fixtures.py
"""

from __future__ import annotations

import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
AS_OF = "2026-10-19T15:00:00+00:00"  # 11:00 ET Monday
EXPIRY = "20261120"
DTE = 32
SPOT = 778.0
RATE = 0.04


def ncdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def bs(spot: float, k: float, t: float, iv: float, right: str) -> tuple[float, float]:
    d1 = (math.log(spot / k) + (RATE + iv * iv / 2) * t) / (iv * math.sqrt(t))
    d2 = d1 - iv * math.sqrt(t)
    if right == "C":
        return spot * ncdf(d1) - k * math.exp(-RATE * t) * ncdf(d2), ncdf(d1)
    return k * math.exp(-RATE * t) * ncdf(-d2) - spot * ncdf(-d1), ncdf(d1) - 1


def iv_curve(k: float, slope: float, base: float = 0.14) -> float:
    m = math.log(k / SPOT)
    return max(0.06, base + slope * m + 1.5 * m * m)


def closes(n: int = 25, daily: float = 0.006) -> list[float]:
    out, px = [], SPOT / (1 + 0.0004) ** n
    for i in range(n):
        px *= 1 + 0.0004 + daily * (1 if i % 2 else -1)
        out.append(round(px, 2))
    out[-1] = SPOT
    return out


def snapshot(slope: float) -> dict:
    t = DTE / 365.0
    rows = []
    for k in range(580, 875, 5):
        for right in ("P", "C"):
            if (right == "P" and k > SPOT) or (right == "C" and k < SPOT):
                continue
            iv = iv_curve(k, slope)
            px, delta = bs(SPOT, k, t, iv, right)
            if px < 0.05:
                continue
            half = max(0.01, round(px * 0.015, 2))
            rows.append({
                "occ": f"SPY{EXPIRY[2:]}{right}{int(k * 1000):08d}", "con_id": None, "expiry": EXPIRY,
                "right": right, "strike": float(k), "bid": round(px - half, 2), "ask": round(px + half, 2),
                "delta": round(delta, 4), "iv": round(iv, 4), "open_interest": 5000.0, "status": "ok",
            })
    return {"as_of": AS_OF, "source": "fixture", "underlying": "SPY", "status": "ok",
            "underlying_price": SPOT, "daily_closes": closes(), "expiry": EXPIRY, "options": rows,
            "_note": "SYNTHETIC. Black-Scholes with a skew curve; not market data."}


def main() -> None:
    (HERE / "spy_snapshot_entry.json").write_text(json.dumps(snapshot(-1.0), indent=1))
    (HERE / "spy_snapshot_flat_skew.json").write_text(json.dumps(snapshot(0.0), indent=1))
    (HERE / "spy_snapshot_unavailable.json").write_text(json.dumps({
        "as_of": AS_OF, "source": "fixture", "underlying": "SPY", "status": "unavailable",
        "reason": "ib_10197_competing_live_session",
        "errors": [{"code": 10197, "message": "No market data during competing live session"}],
    }, indent=1))


if __name__ == "__main__":
    main()
