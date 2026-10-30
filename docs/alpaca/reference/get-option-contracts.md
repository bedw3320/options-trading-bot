# Get Option Contracts

> **Source:** https://docs.alpaca.markets/reference/get-options-contracts
> **Last scraped:** 2026-03-06
> **Relevance:** Contract master list — metadata only (strike, expiry, OI, style). Use this to enumerate available contracts before fetching snapshots or bars. Useful for filtering by DTE, strike range, or style (American vs. European).

---

## Endpoint

```
GET /v2/options/contracts
```

Base URL: `https://api.alpaca.markets` (or `https://paper-api.alpaca.markets`)

---

## Query Parameters

| Parameter | Type | Default | Description |
| --- | --- | --- | --- |
| `underlying_symbols` | string | — | Comma-separated list of underlying tickers (e.g. `AAPL,SPY`) |
| `status` | string | `active` | Contract status: `active` or `inactive` |
| `expiration_date` | date | — | Exact expiration date (YYYY-MM-DD) |
| `expiration_date_gte` | date | — | Minimum expiration date |
| `expiration_date_lte` | date | — | Maximum expiration date |
| `root_symbol` | string | — | Filter by root symbol (e.g. `SPXW` for weekly SPX) |
| `type` | string | — | Option type: `call` or `put` |
| `style` | string | — | Exercise style: `american` or `european` |
| `strike_price_gte` | number | — | Minimum strike price |
| `strike_price_lte` | number | — | Maximum strike price |
| `limit` | integer | 100 | Max results. Range: 1–10000 |
| `page_token` | string | — | Pagination cursor from prior response |
| `ppind` | boolean | — | Filter by primary price indicator (exchange-listed) |
| `show_deliverables` | boolean | — | Include deliverable details in response |

---

## Response

```json
{
  "option_contracts": [
    {
      "id": "3c6e3acd-47ad-4d9e-87ef-4e8b29e4a5aa",
      "symbol": "AAPL250117C00150000",
      "name": "AAPL Jan 17 2025 150 Call",
      "status": "active",
      "tradable": true,
      "expiration_date": "2025-01-17",
      "root_symbol": "AAPL",
      "underlying_symbol": "AAPL",
      "underlying_asset_id": "b0b6dd9d-8b9b-48a9-ba46-b9d54906e415",
      "type": "call",
      "style": "american",
      "strike_price": "150.00",
      "deliverables": [...],
      "open_interest": "1500",
      "open_interest_date": "2025-01-09",
      "close_price": "12.50",
      "close_price_date": "2025-01-09",
      "size": "100"
    }
  ],
  "next_page_token": "abc123..."
}
```

### Key Response Fields

| Field | Description |
| --- | --- |
| `symbol` | OCC-format contract symbol |
| `expiration_date` | Expiration date (YYYY-MM-DD) |
| `type` | `call` or `put` |
| `style` | `american` (can exercise early) or `european` (exercise at expiry only) |
| `strike_price` | Strike as a decimal string |
| `open_interest` | Outstanding contracts |
| `close_price` | Previous close (for reference) |
| `size` | Contract multiplier (always 100 for standard equity options) |

---

## Python SDK

```python
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import GetOptionContractsRequest
from datetime import date

trading_client = TradingClient('api-key', 'secret-key', paper=True)

request = GetOptionContractsRequest(
    underlying_symbols=['AAPL'],
    status='active',
    expiration_date_gte=date(2025, 2, 1),
    expiration_date_lte=date(2025, 3, 31),
    type='call',
    style='american',
    strike_price_gte=145,
    strike_price_lte=175,
    limit=200
)

contracts = trading_client.get_option_contracts(request)
```

---

## Bot Usage Notes

- Use this endpoint to enumerate contracts before fetching snapshots (chain) or bars
- `open_interest` here is end-of-day; use the chain snapshot for real-time OI
- `style: "american"` for most equity options; `"european"` for index options (SPX, NDX, RUT)
- DTE calculation: `(expiration_date - today).days`
- For weekly options, filter by `root_symbol` (e.g. `SPXW` for SPX weeklies, `AAPL` for standard)
- Pagination is required for underlyings with many strikes/expirations — use `next_page_token`
