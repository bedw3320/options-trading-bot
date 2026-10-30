# Get Positions

> **Source:** https://docs.alpaca.markets/reference/getpositionsforaccountbysymbol
> **Last scraped:** 2026-03-06
> **Relevance:** Retrieve current open positions including options. Used for P&L monitoring, risk checks, and determining whether to close or roll a position.

---

## Endpoints

```
GET /v2/positions                    — all open positions
GET /v2/positions/{symbol_or_id}     — single position by symbol or asset ID
DELETE /v2/positions                 — close all positions
DELETE /v2/positions/{symbol_or_id}  — close specific position (market order)
```

Base URL: `https://api.alpaca.markets` (or `https://paper-api.alpaca.markets`)

---

## Path Parameter

| Parameter | Description |
| --- | --- |
| `symbol_or_id` | Ticker (`AAPL`), OCC contract symbol (`AAPL250117C00150000`), or asset UUID |

---

## Response (Position Object)

```json
{
  "asset_id": "3c6e3acd-47ad-4d9e-87ef-4e8b29e4a5aa",
  "symbol": "AAPL250117C00150000",
  "asset_class": "us_option",
  "exchange": "OPT",
  "avg_entry_price": "12.50",
  "qty": "2",
  "qty_available": "2",
  "side": "long",
  "market_value": "2500.00",
  "cost_basis": "2500.00",
  "unrealized_pl": "0.00",
  "unrealized_plpc": "0.0000",
  "unrealized_intraday_pl": "0.00",
  "unrealized_intraday_plpc": "0.0000",
  "current_price": "12.50",
  "lastday_price": "12.50",
  "change_today": "0.0000"
}
```

### Key Fields

| Field | Description |
| --- | --- |
| `symbol` | OCC-format contract symbol for options |
| `asset_class` | `us_option`, `us_equity`, or `crypto` |
| `qty` | Total contracts held |
| `qty_available` | Contracts available to close/sell (may differ from `qty` for covered calls) |
| `avg_entry_price` | Average entry price per contract (×100 for dollar cost) |
| `market_value` | Current market value in dollars |
| `cost_basis` | Total cost (avg_entry_price × qty × 100 for options) |
| `unrealized_pl` | Dollar P&L: market_value − cost_basis |
| `unrealized_plpc` | Percentage P&L as a decimal (0.05 = +5%) |
| `current_price` | Most recent price |
| `lastday_price` | Price as of prior close |
| `change_today` | Intraday change as decimal |

---

## Current Price Timing

| Time (ET) | Price Source |
| --- | --- |
| 4:00 AM – 9:30 AM | Last premarket trade |
| 9:30 AM – 4:00 PM | Last regular-hours trade |
| 4:00 PM – 10:00 PM | Last after-hours trade |
| 10:00 PM – 4:00 AM | Official closing price |

---

## Python SDK

```python
from alpaca.trading.client import TradingClient

trading_client = TradingClient('api-key', 'secret-key', paper=True)

# All positions
all_positions = trading_client.get_all_positions()

# Filter for options only
option_positions = [p for p in all_positions if p.asset_class == 'us_option']

# Get specific position
aapl_call = trading_client.get_open_position('AAPL250117C00150000')

# Close all positions (use with caution)
# trading_client.close_all_positions(cancel_orders=True)

# Close specific position
# trading_client.close_position('AAPL250117C00150000')
```

---

## Bot Usage Notes

- Options positions have `asset_class: "us_option"` and OCC-format symbols
- `qty_available` may be less than `qty` when contracts are used as collateral (e.g. covered call)
- Use `qty_available` when checking if you can close a position
- `unrealized_pl` is in dollars; `unrealized_plpc` is a decimal (multiply by 100 for percent)
- For options, `cost_basis` = `avg_entry_price × qty × 100`
- Wrapped in `integrations/alpaca/positions.py`
