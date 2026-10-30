# Option Historical Bars

> **Source:** https://docs.alpaca.markets/reference/optionbars
> **Last scraped:** 2026-03-06
> **Relevance:** OHLCV bar data for specific option contracts. Use for backtesting, IV trend analysis, or price history on a contract. Note: data only available since February 2024.

---

## Endpoint

```
GET /v1beta1/options/bars
```

Base URL: `https://data.alpaca.markets`

---

## Query Parameters

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `symbols` | string | Yes | Comma-separated OCC contract symbols (e.g. `AAPL250117C00150000`). Max 100. |
| `timeframe` | string | Yes | Bar size. See Timeframe Formats below. |
| `start` | timestamp | No | Start of range (ISO 8601). Defaults to the beginning of available data. |
| `end` | timestamp | No | End of range (ISO 8601). Defaults to now. |
| `limit` | integer | No | Max bars returned. Range: 1–10000. Default: 1000. |
| `page_token` | string | No | Pagination cursor from prior response |
| `sort` | string | No | Sort order: `asc` (oldest first) or `desc` (newest first). Default: `asc`. |

### Timeframe Formats

| Format | Examples |
| --- | --- |
| Minutes | `1Min`, `5Min`, `15Min`, `30Min` (any integer 1–59) |
| Hours | `1Hour`, `4Hour` (any integer 1–23) |
| Daily | `1Day` |
| Weekly | `1Week` |
| Monthly | `1Month`, `2Month`, `3Month`, `4Month`, `6Month`, `12Month` |

---

## Response

```json
{
  "bars": {
    "AAPL250117C00150000": [
      {
        "t": "2025-01-10T14:30:00Z",
        "o": 12.10,
        "h": 12.80,
        "l": 12.00,
        "c": 12.50,
        "v": 150,
        "n": 42,
        "vw": 12.42
      }
    ]
  },
  "next_page_token": "abc123..."
}
```

### Bar Fields

| Field | Description |
| --- | --- |
| `t` | Bar timestamp (UTC) |
| `o` | Open price |
| `h` | High price |
| `l` | Low price |
| `c` | Close price |
| `v` | Volume (contracts traded) |
| `n` | Number of trades |
| `vw` | Volume-weighted average price (VWAP) |

---

## Data Availability

> **⚠️ Historical options bar data is only available since February 2024.**

If `start` is set earlier than February 2024, the response will begin from the first available date.

---

## Python SDK

```python
from alpaca.data.historical import OptionHistoricalDataClient
from alpaca.data.requests import OptionBarsRequest
from alpaca.data.timeframe import TimeFrame

client = OptionHistoricalDataClient('APCA-API-KEY-ID', 'APCA-API-SECRET-KEY')

request = OptionBarsRequest(
    symbol_or_symbols=['AAPL250117C00150000'],
    timeframe=TimeFrame.Day,
    start='2024-06-01',
    end='2025-01-10',
    limit=500
)

bars = client.get_option_bars(request)
```

---

## Bot Usage Notes

- Must specify exact OCC contract symbols — not underlying tickers
- Use `get_options_chain()` first to identify target contracts, then fetch bars
- `15Min` bars are commonly used for intraday entry timing
- `1Day` bars useful for tracking contract P&L over hold period
- VWAP (`vw`) on options bars can confirm intraday price action direction
- Max 100 contracts per request; batch if needed
