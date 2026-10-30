# Working with Orders

> **Source:** https://docs.alpaca.markets/docs/working-with-orders
> **Last scraped:** 2026-03-06
> **Relevance:** All order types available (market, limit, bracket, trailing stop), Python SDK examples, order retrieval, and WebSocket trade update streaming.

---

## Place a New Order

`POST /v2/orders`

```python
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest, LimitOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce

trading_client = TradingClient('api-key', 'secret-key', paper=True)

# Market order
market_order = trading_client.submit_order(
    MarketOrderRequest(symbol="SPY", qty=0.023, side=OrderSide.BUY, time_in_force=TimeInForce.DAY)
)

# Limit order
limit_order = trading_client.submit_order(
    LimitOrderRequest(symbol="BTC/USD", limit_price=17000, notional=4000, side=OrderSide.SELL, time_in_force=TimeInForce.FOK)
)
```

---

## Short Selling

Submit a sell order for a security you don't hold a long position in:

```python
market_order = trading_client.submit_order(
    MarketOrderRequest(symbol="SPY", qty=1, side=OrderSide.SELL, time_in_force=TimeInForce.GTC)
)
```

---

## Client Order IDs

Use `client_order_id` to track orders across strategies. Unique IDs per strategy enable parallel algo management:

```python
MarketOrderRequest(symbol="SPY", qty=0.023, side=OrderSide.BUY, time_in_force=TimeInForce.DAY, client_order_id='strategy_1_entry')
my_order = trading_client.get_order_by_client_id('strategy_1_entry')
```

---

## Bracket Orders

Chain entry + stop-loss + take-profit as a single order:

```python
from alpaca.trading.requests import MarketOrderRequest, TakeProfitRequest, StopLossRequest
from alpaca.trading.enums import OrderClass

bracket_order = trading_client.submit_order(
    MarketOrderRequest(
        symbol="SPY",
        qty=5,
        side=OrderSide.BUY,
        time_in_force=TimeInForce.DAY,
        order_class=OrderClass.BRACKET,
        take_profit=TakeProfitRequest(limit_price=400),
        stop_loss=StopLossRequest(stop_price=300)
    )
)
```

Order classes:
- `bracket` — entry + stop loss + take profit
- `oto` (one-triggers-other) — entry + stop loss only
- `oco` (one-cancels-other) — stop loss + take profit for existing position

---

## Trailing Stop Orders

Stop price adjusts upward as price rises:

```python
from alpaca.trading.requests import TrailingStopOrderRequest

# Trailing by % (stop = HWM × 0.99)
trailing_order = trading_client.submit_order(
    TrailingStopOrderRequest(symbol="SPY", qty=1, side=OrderSide.SELL, time_in_force=TimeInForce.GTC, trail_percent=1.00)
)

# Trailing by $ (stop = HWM - $1.00)
trailing_order = trading_client.submit_order(
    TrailingStopOrderRequest(symbol="SPY", qty=1, side=OrderSide.SELL, time_in_force=TimeInForce.GTC, trail_price=1.00)
)
```

---

## Retrieve Orders

```python
from alpaca.trading.requests import GetOrdersRequest
from alpaca.trading.enums import QueryOrderStatus

get_orders_data = GetOrdersRequest(
    status=QueryOrderStatus.CLOSED,
    limit=100,
    nested=True  # show nested multi-leg orders
)
orders = trading_client.get_orders(filter=get_orders_data)
```

---

## Stream Order Updates (WebSocket)

```python
from alpaca.trading.stream import TradingStream

stream = TradingStream('api-key', 'secret-key', paper=True)

async def on_msg(data):
    print("Update for {}. Event: {}.".format(data.order.client_order_id, data.event))

stream.subscribe_trade_updates(on_msg)
stream.run()
```

---

## FAQ

**Timeout on order submission:** Do NOT resend. The order may have been routed to market. Check the broker dashboard and contact support@alpaca.markets before taking any action.

---

## Order Type Summary by Asset Class

| Asset Class | Order Types | Time in Force |
| --- | --- | --- |
| Equity | market, limit, stop, stop_limit, trailing_stop | day, gtc, opg, cls, ioc, fok |
| Options | market, limit | day only |
| Crypto | market, limit, stop_limit | gtc, ioc |
| Multi-leg Options | market, limit | day only |
