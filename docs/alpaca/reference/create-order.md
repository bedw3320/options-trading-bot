# Create Order

> **Source:** https://docs.alpaca.markets/reference/postorder
> **Last scraped:** 2026-03-06
> **Relevance:** Full parameter reference for placing any order type — market, limit, bracket, trailing stop, multi-leg options. This is the core execution endpoint.

---

## Endpoint

```
POST /v2/orders
```

Base URL: `https://api.alpaca.markets` (or `https://paper-api.alpaca.markets`)

---

## Request Body

```json
{
  "symbol": "AAPL250117C00150000",
  "qty": "1",
  "notional": null,
  "side": "buy",
  "type": "limit",
  "time_in_force": "day",
  "limit_price": "12.50",
  "stop_price": null,
  "trail_price": null,
  "trail_percent": null,
  "extended_hours": false,
  "client_order_id": "strategy_1_entry_001",
  "order_class": "simple",
  "take_profit": null,
  "stop_loss": null,
  "position_intent": "buy_to_open"
}
```

---

## Parameters

### Core Fields

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `symbol` | string | Yes* | Ticker or OCC contract symbol. Not required for `mleg` orders (use `legs` instead). |
| `qty` | string | Yes* | Number of shares/contracts. Use with `side`. Either `qty` or `notional` required. |
| `notional` | string | No | Dollar amount for fractional orders. Cannot be used with options. |
| `side` | string | Yes | `buy` or `sell`. For MLeg orders, specify per-leg. |
| `type` | string | Yes | Order type. See Order Types below. |
| `time_in_force` | string | Yes | Time in force. See TIF below. |
| `client_order_id` | string | No | Custom ID for tracking (≤128 chars, alphanumeric + `_`). Must be unique. |

### Price Fields

| Parameter | Used With | Description |
| --- | --- | --- |
| `limit_price` | `limit`, `stop_limit` | Limit price for execution |
| `stop_price` | `stop`, `stop_limit` | Stop trigger price |
| `trail_price` | `trailing_stop` | Trail distance in dollars (stop = HWM - trail_price) |
| `trail_percent` | `trailing_stop` | Trail distance as % (stop = HWM × (1 - trail_percent/100)) |

### Advanced Fields

| Parameter | Type | Description |
| --- | --- | --- |
| `order_class` | string | `simple` (default), `bracket`, `oco`, `oto`, `mleg` |
| `legs` | array | Multi-leg legs array (MLeg orders only). See MLeg section. |
| `take_profit` | object | `{"limit_price": "..."}` — used with `bracket` |
| `stop_loss` | object | `{"stop_price": "...", "limit_price": "..."}` — used with `bracket`/`oto` |
| `position_intent` | string | `buy_to_open`, `buy_to_close`, `sell_to_open`, `sell_to_close` |
| `extended_hours` | boolean | Allow execution in pre/after-market (equities only, limit orders) |
| `advanced_instructions` | object | Advanced routing instructions (rarely needed) |

---

## Order Types

| Type | Description | Supported Assets |
| --- | --- | --- |
| `market` | Execute at best available price | Stocks, options, crypto |
| `limit` | Execute at limit price or better | Stocks, options, crypto |
| `stop` | Triggers market order at stop price | Stocks only |
| `stop_limit` | Triggers limit order at stop price | Stocks, crypto |
| `trailing_stop` | Stop adjusts with HWM | Stocks only |

**Options only support `market` and `limit` orders.**

---

## Time in Force

| TIF | Description | Supported Assets |
| --- | --- | --- |
| `day` | Cancel at market close | All — only supported TIF for options |
| `gtc` | Good till cancelled | Stocks, crypto |
| `opg` | Execute at open | Stocks only |
| `cls` | Execute at close | Stocks only |
| `ioc` | Immediate or cancel | Stocks, crypto |
| `fok` | Fill or kill | Stocks, crypto |

**Options orders: `day` only.**

---

## Order Classes

### Bracket Order (entry + stop + take profit)

```json
{
  "symbol": "SPY",
  "qty": "5",
  "side": "buy",
  "type": "market",
  "time_in_force": "day",
  "order_class": "bracket",
  "take_profit": {"limit_price": "520"},
  "stop_loss": {"stop_price": "480", "limit_price": "478"}
}
```

### OTO (One-triggers-other — entry + stop loss)

```json
{
  "order_class": "oto",
  "stop_loss": {"stop_price": "480"}
}
```

### OCO (One-cancels-other — stop loss + take profit for existing position)

```json
{
  "order_class": "oco",
  "take_profit": {"limit_price": "520"},
  "stop_loss": {"stop_price": "480"}
}
```

### MLeg (Multi-leg options)

```json
{
  "type": "limit",
  "time_in_force": "day",
  "order_class": "mleg",
  "limit_price": "1.50",
  "legs": [
    {
      "symbol": "AAPL250117C00150000",
      "side": "buy",
      "ratio_qty": 1,
      "position_intent": "buy_to_open"
    },
    {
      "symbol": "AAPL250117C00160000",
      "side": "sell",
      "ratio_qty": 1,
      "position_intent": "sell_to_open"
    }
  ]
}
```

---

## Response (Order Object)

```json
{
  "id": "61e69015-8549-4bfd-b9c3-01e75843f47d",
  "client_order_id": "strategy_1_entry_001",
  "status": "new",
  "symbol": "AAPL250117C00150000",
  "qty": "1",
  "side": "buy",
  "type": "limit",
  "time_in_force": "day",
  "limit_price": "12.50",
  "filled_qty": "0",
  "filled_avg_price": null,
  "order_class": "simple",
  "created_at": "2025-01-10T14:30:00Z",
  "updated_at": "2025-01-10T14:30:00Z"
}
```

---

## Python SDK

```python
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import LimitOrderRequest, MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce

trading_client = TradingClient('api-key', 'secret-key', paper=True)

# Buy to open a call
order = trading_client.submit_order(
    LimitOrderRequest(
        symbol='AAPL250117C00150000',
        qty=1,
        side=OrderSide.BUY,
        time_in_force=TimeInForce.DAY,
        limit_price=12.50,
        client_order_id='strategy_bull_call_001'
    )
)
```

---

## Bot Usage Notes

- Always use `client_order_id` for strategy tracking — format: `{strategy_name}_{ticker}_{timestamp}`
- Options orders: `type=limit` preferred over `market` to control fill price
- Options orders: `time_in_force=day` always — no GTC support
- `position_intent` is optional but helps Alpaca with margin calculation
- Do NOT retry on timeout — the order may have been routed. Check dashboard first.
- Wrapped in `integrations/alpaca/orders.py`
