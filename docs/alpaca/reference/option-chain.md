# Option Chain (Snapshots)

> **Source:** https://docs.alpaca.markets/reference/optionchain
> **Last scraped:** 2026-03-06
> **Relevance:** Primary endpoint for building an options chain — returns latest trade, quote, and Greeks for every contract on an underlying. Used for strike selection, IV filtering, and delta targeting.

---

## Endpoint

```
GET /v1beta1/options/snapshots/{underlying_symbol}
```

Base URL: `https://data.alpaca.markets`

---

## Path Parameters

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `underlying_symbol` | string | Yes | Ticker of the underlying (e.g. `AAPL`, `SPY`) |

---

## Query Parameters

| Parameter | Type | Default | Description |
| --- | --- | --- | --- |
| `feed` | string | `opra` | Data feed: `opra` (official) or `indicative` (free, quotes delayed) |
| `limit` | integer | 100 | Max contracts returned. Range: 1–1000 |
| `page_token` | string | — | Pagination cursor from prior response |
| `updated_since` | timestamp | — | Only return contracts updated since this time (ISO 8601) |
| `type` | string | — | Filter by option type: `call` or `put` |
| `strike_price_gte` | number | — | Minimum strike price (inclusive) |
| `strike_price_lte` | number | — | Maximum strike price (inclusive) |
| `expiration_date` | date | — | Exact expiration date (YYYY-MM-DD) |
| `expiration_date_gte` | date | — | Minimum expiration date |
| `expiration_date_lte` | date | — | Maximum expiration date |
| `root_symbol` | string | — | Filter by root symbol (e.g. `SPXW`) |

---

## Response

Returns a `snapshots` object keyed by OCC contract symbol:

```json
{
  "snapshots": {
    "AAPL250117C00150000": {
      "latestTrade": {
        "t": "2025-01-10T15:59:00Z",
        "x": "C",
        "p": 12.50,
        "s": 1,
        "c": ["I"]
      },
      "latestQuote": {
        "t": "2025-01-10T15:59:59Z",
        "ax": "C",
        "ap": 12.65,
        "as": 10,
        "bx": "C",
        "bp": 12.45,
        "bs": 10,
        "c": ["R"]
      },
      "greeks": {
        "delta": 0.65,
        "gamma": 0.03,
        "theta": -0.05,
        "vega": 0.10,
        "rho": 0.04
      },
      "impliedVolatility": 0.28,
      "openInterest": 1500
    }
  },
  "next_page_token": "abc123..."
}
```

### Greeks Fields

| Field | Description |
| --- | --- |
| `delta` | Rate of change of option price vs. underlying (–1 to 1) |
| `gamma` | Rate of change of delta (always positive) |
| `theta` | Daily time decay (negative for long options) |
| `vega` | Sensitivity to 1% change in IV |
| `rho` | Sensitivity to 1% change in interest rate |
| `impliedVolatility` | IV as a decimal (0.28 = 28%) |
| `openInterest` | Number of outstanding contracts |

---

## Python SDK

```python
from alpaca.data.historical import OptionHistoricalDataClient
from alpaca.data.requests import OptionSnapshotRequest

client = OptionHistoricalDataClient('APCA-API-KEY-ID', 'APCA-API-SECRET-KEY')

request = OptionSnapshotRequest(
    underlying_symbol='AAPL',
    feed='indicative',       # use 'opra' for live trading
    limit=50,
    type='call',
    expiration_date_gte='2025-02-01',
    expiration_date_lte='2025-03-31',
    strike_price_gte=145,
    strike_price_lte=175
)

snapshots = client.get_option_snapshot(request)
```

---

## Bot Usage Notes

- Use `indicative` feed for strategy development and paper trading (free)
- Use `opra` for live trading (requires OPRA subscription)
- Use `strike_price_gte/lte` and `expiration_date_gte/lte` to pre-filter before iterating
- `delta` target: 0.3–0.4 for OTM options; 0.5+ for ATM; 0.7+ for deep ITM
- `impliedVolatility` is a key signal — high IV = expensive options (sell bias), low IV = cheap options (buy bias)
- Paginate using `next_page_token` for underlyings with many contracts (e.g. SPX, AAPL)
- Wrapped in `integrations/alpaca/options_data.py` via `get_options_chain()`
