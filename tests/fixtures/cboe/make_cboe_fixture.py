"""Regenerate cboe_spy.json from spy_snapshot_entry.json.

    uv run python tests/fixtures/cboe/make_cboe_fixture.py
"""
import json
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).parent
src = json.loads((HERE.parent / "spy_snapshot_entry.json").read_text())
# CBOE quote page timestamps are naive ET. Fixture as_of 15:00 UTC = 11:00 ET.
options = []
for o in src["options"]:
    options.append({
        "option": o["occ"],
        "bid": o["bid"],
        "ask": o["ask"],
        "iv": round(o["iv"] * 100.0, 4),  # CBOE sends percent
        "delta": o["delta"],
        "gamma": 0.01,
        "vega": 0.12,
        "theta": -0.04,
        "open_interest": o["open_interest"],
    })
options.append({
    "option": "SPY261218C00800000", "bid": 1.0, "ask": 1.1, "iv": 20.0, "delta": 0.2,
    "gamma": 0.01, "vega": 0.1, "theta": -0.02, "open_interest": 10,
})
# Last completed session before fixture today (2026-10-19 Mon) is 2026-10-16 Fri.
rows = ["Date,Open,High,Low,Close,Volume"]
end = date(2026, 10, 16)
n = len(src["daily_closes"])
for i, c in enumerate(src["daily_closes"]):
    d = end - timedelta(days=n - 1 - i)
    rows.append(f"{d.isoformat()},{c},{c},{c},{c},1")
out = {
    "options": {
        "timestamp": "2026-10-19T11:00:00",
        "data": {
            "symbol": "SPY",
            "current_price": src["underlying_price"],
            "last_trade_time": "2026-10-19T11:00:00",
            "prev_day_close": src["daily_closes"][-2],
            "options": options,
        },
    },
    "bars_csv": "\n".join(rows) + "\n",
}
(HERE / "cboe_spy.json").write_text(json.dumps(out, indent=1))
print("wrote", HERE / "cboe_spy.json", len(options), "options")
