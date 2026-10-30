# WebSocket Streaming Market Data

> **Source:** https://docs.alpaca.markets/docs/streaming-market-data
> **Last scraped:** 2026-03-06
> **Relevance:** Real-time data streaming for options, stocks, crypto, and news via WebSocket — useful for intraday strategies and live monitoring.

---

## Stream URLs

```
wss://stream.data.alpaca.markets/{version}/{feed}
```

| Feed | URL path |
| --- | --- |
| Stocks (IEX) | `/v2/iex` |
| Stocks (SIP) | `/v2/sip` |
| Crypto | `/v1beta3/crypto/us` |
| Options | `/v1beta1/options` |
| News | `/v1beta1/news` |
| Test (always available) | `/v2/test` — use symbol `FAKEPACA` |

**Sandbox:** `wss://stream.data.sandbox.alpaca.markets/{version}/{feed}`

---

## Authentication

**Option 1 — HTTP headers (Trading API):**
```
APCA-API-KEY-ID: {KEY_ID}
APCA-API-SECRET-KEY: {SECRET}
```

**Option 2 — Auth message (both Trading & Broker API):**
```json
{"action": "auth", "key": "{KEY_ID}", "secret": "{SECRET}"}
```
Must authenticate within **10 seconds** of connecting.

Success response:
```json
[{"T": "success", "msg": "authenticated"}]
```

---

## Subscribing to Channels

```json
{
  "action": "subscribe",
  "trades": ["AAPL"],
  "quotes": ["AMD", "CLDR"],
  "bars": ["*"]
}
```

Use `"*"` wildcard to subscribe to all symbols. Unsubscribe with:
```json
{"action": "unsubscribe", "quotes": ["FAKEPACA"]}
```

Confirmation echoes current full subscription list:
```json
[{"T": "subscription", "trades": ["AAPL"], "quotes": ["AMD", "CLDR"], "bars": ["*"]}]
```

---

## Message Format

All messages arrive in arrays:
```json
[{"T": "{message_type}", ...}]
```

| `T` value | Meaning |
| --- | --- |
| `success` | Connection/auth success |
| `error` | Error (see code) |
| `subscription` | Subscription confirmation |
| `t` | Trade |
| `q` | Quote |
| `b` | Bar |

---

## Connection Limits

Most subscriptions (including Algo Trader Plus): **1 connection per endpoint**.

Exceeding limit:
```json
[{"T": "error", "code": 406, "msg": "connection limit exceeded"}]
```

---

## Error Codes

| Code | Message | Cause |
| --- | --- | --- |
| 400 | invalid syntax | Malformed message or invalid symbol format |
| 401 | not authenticated | Subscribe before auth |
| 402 | auth failed | Bad credentials |
| 404 | auth timeout | Didn't authenticate within 10s |
| 405 | symbol limit exceeded | Too many symbols for subscription tier |
| 406 | connection limit exceeded | Already at max connections |
| 407 | slow client | Buffer full, may be disconnected |
| 409 | insufficient subscription | Data source not in your plan |
| 410 | invalid subscribe action | Subscribed to unsupported channel for this feed |

---

## Encoding and Compression

- Text: `Content-Type: application/json`
- Binary: `Content-Type: application/msgpack`
- Compression: RFC-7692 (SDKs handle automatically)

---

## Test Stream Example

```bash
wscat -c wss://stream.data.alpaca.markets/v2/test
> {"action":"auth","key":"<KEY>","secret":"<SECRET>"}
< [{"T":"success","msg":"authenticated"}]
> {"action":"subscribe","bars":["FAKEPACA"],"quotes":["FAKEPACA"]}
< [{"T":"subscription","trades":[],"quotes":["FAKEPACA"],"bars":["FAKEPACA"]}]
< [{"T":"q","S":"FAKEPACA","bp":133.85,"bs":4,"ap":135.77,"as":5,...}]
```

---

## Options-Specific Notes

- Options stream: `wss://stream.data.alpaca.markets/v1beta1/options`
- Available channels in options stream: `trades`, `quotes` (no `bars` channel)
- Options stream requires OPRA subscription for live data
