# Working with Positions

> **Source:** https://docs.alpaca.markets/docs/working-with-positions
> **Last scraped:** 2026-03-06
> **Relevance:** How to retrieve positions (all assets including options), price timing rules across market sessions.

---

## Get Positions

`GET /v2/positions` — all open positions
`GET /v2/positions/{symbol}` — specific symbol

```python
from alpaca.trading.client import TradingClient

trading_client = TradingClient('api-key', 'secret-key')

# Get position in AAPL
aapl_position = trading_client.get_open_position('AAPL')

# Get all positions (stocks, options, crypto)
portfolio = trading_client.get_all_positions()

for position in portfolio:
    print("{} shares of {}".format(position.qty, position.symbol))
```

Options positions use the same endpoint — filter by `asset_class == "us_option"` in your code.

---

## Current Price Timing

The `current_price` field in position objects reflects:

| Time (ET) | Price Source |
| --- | --- |
| 4:00 AM – 9:30 AM | Last premarket trade |
| 9:30 AM – 4:00 PM | Last regular hours trade |
| 4:00 PM – 10:00 PM | Last after-hours trade |
| 10:00 PM – 4:00 AM | Official closing price from primary exchange |

---

## Position Object Fields (key fields)

```json
{
  "asset_id": "...",
  "symbol": "AAPL240223C00095000",
  "asset_class": "us_option",
  "qty": "2",
  "avg_entry_price": "6.05",
  "side": "long",
  "market_value": "1068",
  "cost_basis": "1210",
  "unrealized_pl": "-142",
  "unrealized_plpc": "-0.117",
  "unrealized_intraday_pl": "-142",
  "current_price": "5.34",
  "lastday_price": "5.34",
  "change_today": "0",
  "qty_available": "2"
}
```

`qty_available` may differ from `qty` if shares are held as collateral for a covered call.

---

## Bot Usage Notes

- Options positions appear with `asset_class: "us_option"` and OCC-format symbols
- Use `qty_available` (not `qty`) when checking if you can sell/close a position
- `unrealized_pl` is in dollars, `unrealized_plpc` is a decimal percentage
- `cost_basis` for options = avg_entry_price × 100 × contracts
