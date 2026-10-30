# Option Latest Trades

> **Source:** https://docs.alpaca.markets/reference/optionlatesttrades
> **Last scraped:** 2026-03-06
> **Relevance:** Get the most recent trade for one or more option contracts. Useful for last-price reference when building execution logic or checking fill quality vs. mid-market.

---

## Endpoint

```
GET /v1beta1/options/trades/latest
```

Base URL: `https://data.alpaca.markets`

---

## Query Parameters

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `symbols` | string | Yes | Comma-separated OCC contract symbols (e.g. `AAPL250117C00150000,AAPL250117P00150000`) |
| `feed` | string | No | Data feed: `opra` (official) or `indicative` (free, delayed 15 min). Default: `opra` if subscribed, else `indicative`. |

---

## Response

```json
{
  "trades": {
    "AAPL250117C00150000": {
      "t": "2025-01-10T15:59:45Z",
      "x": "C",
      "p": 12.50,
      "s": 1,
      "c": ["I"]
    }
  }
}
```

### Trade Fields

| Field | Description |
| --- | --- |
| `t` | Trade timestamp (UTC) |
| `x` | Exchange code where trade occurred |
| `p` | Trade price |
| `s` | Trade size (contracts) |
| `c` | Trade condition codes |

---

## Trade Condition Codes (common)

| Code | Meaning |
| --- | --- |
| `I` | Odd lot (< 1 contract) |
| `R` | Regular sale |
| `X` | Cross trade |

---

## Python SDK

```python
from alpaca.data.historical import OptionHistoricalDataClient
from alpaca.data.requests import OptionLatestTradeRequest

client = OptionHistoricalDataClient('APCA-API-KEY-ID', 'APCA-API-SECRET-KEY')

request = OptionLatestTradeRequest(
    symbol_or_symbols=['AAPL250117C00150000', 'AAPL250117P00150000'],
    feed='indicative'
)

trades = client.get_option_latest_trade(request)
```

---

## Bot Usage Notes

- Returns one trade per contract — this is the **last traded price**, not the current bid/ask
- For bid/ask spread, use the chain snapshot endpoint (`/v1beta1/options/snapshots`)
- `indicative` feed: trades are delayed 15 minutes — do not use for real-time execution
- `opra` feed: real-time trades, requires OPRA subscription
- Compare last trade to current bid/ask mid to estimate fill slippage
- Use alongside `latestQuote` from the snapshot for a complete picture
