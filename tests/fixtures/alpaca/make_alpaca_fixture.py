"""Regenerate alpaca_spy.json (Alpaca API response shapes) from spy_snapshot_entry.json.
    uv run python tests/fixtures/alpaca/make_alpaca_fixture.py
"""
import json
from pathlib import Path

HERE = Path(__file__).parent
src = json.loads((HERE.parent / "spy_snapshot_entry.json").read_text())
exp = src["expiry"]
iso = f"{exp[:4]}-{exp[4:6]}-{exp[6:]}"
contracts, snaps = [], {}
for o in src["options"]:
    contracts.append({"symbol": o["occ"], "expiration_date": iso, "type": "put" if o["right"] == "P" else "call",
                      "strike_price": f'{o["strike"]:.2f}', "open_interest": str(int(o["open_interest"] or 0))})
    snaps[o["occ"]] = {"latestQuote": {"bp": o["bid"], "ap": o["ask"], "t": src["as_of"]},
                       "greeks": {"delta": o["delta"]}, "impliedVolatility": o["iv"]}
# an off-grid / other-expiry contract the adapter must ignore
contracts.append({"symbol": "SPY261218C00800000", "expiration_date": "2026-12-18", "type": "call",
                  "strike_price": "800.00", "open_interest": "10"})
out = {
    "latest_trade": {"symbol": "SPY", "trade": {"p": src["underlying_price"], "t": src["as_of"]}},
    "bars": {"bars": [{"c": c, "t": f"day{i}"} for i, c in enumerate(src["daily_closes"])], "next_page_token": None},
    "contracts_page1": {"option_contracts": contracts[: len(contracts) // 2], "next_page_token": "p2"},
    "contracts_page2": {"option_contracts": contracts[len(contracts) // 2:], "next_page_token": None},
    "snapshots": {"snapshots": snaps, "next_page_token": None},
}
(HERE / "alpaca_spy.json").write_text(json.dumps(out, indent=1))
print("wrote", HERE / "alpaca_spy.json", len(contracts), "contracts")
