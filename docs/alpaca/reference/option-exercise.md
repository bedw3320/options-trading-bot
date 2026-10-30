# Option Exercise

> **Source:** https://docs.alpaca.markets/reference/optionexercise-1
> **Last scraped:** 2026-03-06
> **Relevance:** Manually exercise an option contract before expiration. Rarely used in practice — most options are closed by selling, not exercised. Know the endpoint exists for edge cases (deep ITM, dividend capture).

---

## Endpoint

```
POST /v2/positions/{symbol_or_contract_id}/exercise
```

Base URL: `https://api.alpaca.markets` (or `https://paper-api.alpaca.markets`)

> **Note:** The Broker API uses `/v1/trading/accounts/{account_id}/positions/{symbol_or_contract_id}/exercise`. For the standard Trading API, use `/v2/positions/{symbol}/exercise`.

---

## Path Parameter

| Parameter | Description |
| --- | --- |
| `symbol_or_contract_id` | OCC contract symbol (e.g. `AAPL250117C00150000`) or contract UUID |

---

## Request Body

All parameters are optional:

| Parameter | Type | Description |
| --- | --- | --- |
| `qty` | integer | Number of contracts to exercise. If omitted, all contracts in position are exercised. |
| `commission` | number | Commission amount (Broker API only — usually omit) |

---

## Response

- `200 OK` — Exercise submitted successfully (no body)
- `403 Forbidden` — Exercise not allowed (e.g. OTM contract, insufficient qty, not an American-style option)
- `404 Not Found` — Position not found

---

## Python SDK

```python
from alpaca.trading.client import TradingClient

trading_client = TradingClient('api-key', 'secret-key', paper=True)

# Exercise all contracts in position
trading_client.exercise_options_position(
    symbol_or_contract_id='AAPL250117C00150000'
)

# Exercise specific quantity
trading_client.exercise_options_position(
    symbol_or_contract_id='AAPL250117C00150000',
    qty=1
)
```

---

## When to Exercise

| Scenario | Recommended Action |
| --- | --- |
| Contract has extrinsic value remaining | Sell to close (captures full value) |
| Contract is deep ITM near expiry | Exercise or sell (check bid/ask width) |
| Dividend capture on call option | Early exercise to collect dividend (before ex-date) |
| Spread leg needs to be exercised | Exercise one leg to settle the spread |

---

## Automatic Expiration Handling

Alpaca automatically handles expiration at market close (3:30 PM ET cutoff):

- **ITM options:** Exercised automatically (unless DNE instruction set)
- **OTM options:** Expire worthless automatically
- **Do Not Exercise (DNE):** Contact support — not API-settable

See `guides/options-trading-overview.md` for full expiration rules.

---

## Bot Usage Notes

- Manual exercise is almost never the right call — sell to close instead to capture remaining extrinsic value
- Only American-style options can be exercised early; European-style (SPX, NDX) cannot
- If a contract expires ITM and you don't want to take delivery, close before 3:30 PM ET on expiration day
- Assignment risk: if you sold options, monitor `OPASN` activity events for overnight assignment
- Exercise generates `OPEXC` activity event in account history
- See `guides/options-events.md` for activity type details
