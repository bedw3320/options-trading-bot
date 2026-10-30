# Get Orders

> **Source:** https://docs.alpaca.markets/reference/getallorders-1
> **Last scraped:** 2026-03-06
> **Relevance:** Retrieve open/closed orders with filtering by status, symbol, asset class, and date range. Used for trade reconciliation, strategy state tracking, and fill confirmation.

---

## Endpoint

```
GET /v2/orders
```

Base URL: `https://api.alpaca.markets` (or `https://paper-api.alpaca.markets`)

Also: `GET /v2/orders/{order_id}` to retrieve a single order by Alpaca order ID.

```
GET /v2/orders/{client_order_id}?by_client_order_id=true
```
to retrieve by your custom `client_order_id`.

---

## Query Parameters

| Parameter | Type | Default | Description |
| --- | --- | --- | --- |
| `status` | string | `open` | Filter by order status: `open`, `closed`, or `all` |
| `limit` | integer | 50 | Max orders returned. Range: 1–500 |
| `after` | timestamp | — | Return orders submitted after this time (ISO 8601) |
| `until` | timestamp | — | Return orders submitted before this time (ISO 8601) |
| `direction` | string | `desc` | Sort direction: `asc` (oldest first) or `desc` (newest first) |
| `nested` | boolean | false | Include nested leg orders for bracket/MLeg orders |
| `symbols` | string | — | Comma-separated symbols to filter by |
| `side` | string | — | Filter by `buy` or `sell` |
| `asset_class` | string | — | Filter by asset class: `us_equity`, `crypto`, `us_option` |
| `before_order_id` | string | — | Return orders submitted before this order ID (pagination) |
| `after_order_id` | string | — | Return orders submitted after this order ID (pagination) |

---

## Response

Returns an array of order objects:

```json
[
  {
    "id": "61e69015-8549-4bfd-b9c3-01e75843f47d",
    "client_order_id": "strategy_1_entry_001",
    "created_at": "2025-01-10T14:30:00Z",
    "updated_at": "2025-01-10T14:31:00Z",
    "submitted_at": "2025-01-10T14:30:00Z",
    "filled_at": "2025-01-10T14:30:45Z",
    "expired_at": null,
    "canceled_at": null,
    "status": "filled",
    "symbol": "AAPL250117C00150000",
    "asset_class": "us_option",
    "qty": "1",
    "filled_qty": "1",
    "type": "limit",
    "side": "buy",
    "time_in_force": "day",
    "limit_price": "12.50",
    "filled_avg_price": "12.45",
    "order_class": "simple",
    "legs": null
  }
]
```

### Key Order Status Values

| Status | Description |
| --- | --- |
| `new` | Submitted, awaiting routing |
| `partially_filled` | Some quantity filled |
| `filled` | Fully filled |
| `canceled` | Cancelled (by user or end of day) |
| `expired` | Expired at close (day orders) |
| `pending_cancel` | Cancel submitted, not confirmed |
| `rejected` | Rejected (e.g. insufficient buying power) |
| `accepted` | Accepted for routing |

---

## Python SDK

```python
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import GetOrdersRequest
from alpaca.trading.enums import QueryOrderStatus

trading_client = TradingClient('api-key', 'secret-key', paper=True)

# Get all open orders
open_orders = trading_client.get_orders()

# Get closed options orders from today
request = GetOrdersRequest(
    status=QueryOrderStatus.CLOSED,
    asset_class='us_option',
    limit=100,
    nested=True
)
closed_orders = trading_client.get_orders(filter=request)

# Get specific order by client ID
my_order = trading_client.get_order_by_client_id('strategy_1_entry_001')

# Cancel an order
trading_client.cancel_order_by_id(order_id='61e69015-...')
```

---

## Bot Usage Notes

- Use `asset_class=us_option` to filter options-only orders
- Use `nested=True` to see legs of bracket/MLeg orders
- Use `client_order_id` convention for strategy-level tracking
- `filled_avg_price` is the actual execution price — compare to `limit_price` for slippage analysis
- `status=all` is useful for end-of-day reconciliation
- Wrapped in `integrations/alpaca/orders.py`
