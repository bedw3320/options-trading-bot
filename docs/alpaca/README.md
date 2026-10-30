# Alpaca Capability Reference

A local knowledge base for the Alpaca Trading API — scraped from official docs for use in strategy design, skill writing, and agent prompt grounding.

**Last updated:** 2026-03-06

---

## Quick Answers

**What order types are supported for options?**
→ `market` and `limit` only. Time in force: `day` only. See [`guides/options-orders.md`](guides/options-orders.md) + [`reference/create-order.md`](reference/create-order.md)

**What Greeks does the option chain endpoint return?**
→ `delta`, `gamma`, `theta`, `vega`, `rho`, plus `impliedVolatility` and `openInterest`. See [`reference/option-chain.md`](reference/option-chain.md)

**How do multi-leg options orders work?**
→ `order_class: "mleg"`, up to 4 legs, each with `symbol`, `side`, `ratio_qty`, `position_intent`. Day TIF only. See [`guides/options-level-3-multi-leg.md`](guides/options-level-3-multi-leg.md)

**Can I stream real-time options quotes?**
→ Yes, via `wss://stream.data.alpaca.markets/v1beta1/options`. Supports `trades` and `quotes` channels (no `bars`). Requires OPRA subscription for live data. See [`guides/streaming-market-data.md`](guides/streaming-market-data.md)

**What trading levels are required for different strategies?**
→ Level 1: covered calls, CSPs. Level 2: long calls/puts. Level 3: spreads, iron condors, multi-leg. See [`guides/options-trading-overview.md`](guides/options-trading-overview.md)

**Is historical options data available for backtesting?**
→ Yes, but only since February 2024. See [`guides/historical-market-data.md`](guides/historical-market-data.md) + [`reference/option-historical-bars.md`](reference/option-historical-bars.md)

**How do I check if a ticker has listed options?**
→ GET /v2/assets with `attributes=has_options`. See [`reference/get-assets.md`](reference/get-assets.md)

**How does options expiration work automatically?**
→ ITM options auto-exercise at expiry; OTM expire worthless. 3:30 PM ET cutoff. See [`guides/options-trading-overview.md`](guides/options-trading-overview.md)

**What's the difference between OPRA and indicative feeds?**
→ OPRA = official real-time data (subscription required). Indicative = free, quotes delayed. See [`guides/historical-market-data.md`](guides/historical-market-data.md)

**How do I track orders across strategies?**
→ Use `client_order_id` (≤128 chars). Retrieve by `trading_client.get_order_by_client_id()`. See [`reference/create-order.md`](reference/create-order.md)

**What happens when an option gets assigned overnight?**
→ Activity type `OPASN` appears in account history. Monitor this. See [`guides/options-events.md`](guides/options-events.md)

**What's the margin calculation for spreads?**
→ Universal Spread Rule: max(leg payoffs) minus min(leg payoffs). See [`guides/options-level-3-multi-leg.md`](guides/options-level-3-multi-leg.md)

---

## Directory Structure

```
docs/alpaca/
  README.md                          ← you are here (capability index)
  guides/                            ← conceptual: what/why
    options-trading-overview.md      ← lifecycle, levels, order constraints, auto-exercise
    options-orders.md                ← order types with concrete JSON examples
    options-level-3-multi-leg.md     ← MLeg structure, spread types, margin rules
    options-events.md                ← exercise, assignment, expiry activity events
    working-with-orders.md           ← order management, bracket, trailing stop, streaming
    working-with-positions.md        ← position object fields, P&L, price timing
    historical-market-data.md        ← data availability, feed types, existing bot integration
    streaming-market-data.md         ← WebSocket setup, auth, channels, error codes
    getting-started.md               ← API endpoints, auth, SDK setup, env vars
  reference/                         ← endpoint specs: params, response shapes
    option-chain.md                  ← GET /v1beta1/options/snapshots (Greeks, IV, OI)
    get-option-contracts.md          ← GET /v2/options/contracts (contract master list)
    option-historical-bars.md        ← GET /v1beta1/options/bars (OHLCV)
    option-latest-trades.md          ← GET /v1beta1/options/trades/latest
    create-order.md                  ← POST /v2/orders (all order types)
    get-orders.md                    ← GET /v2/orders (retrieval + cancellation)
    get-positions.md                 ← GET /v2/positions (P&L, qty_available)
    get-assets.md                    ← GET /v2/assets (tradability flags)
    option-exercise.md               ← POST /positions/{symbol}/exercise
```

---

## Capability Map

### Options Trading

| Capability | Guide | Reference |
| --- | --- | --- |
| Options overview & lifecycle | [options-trading-overview](guides/options-trading-overview.md) | — |
| Place options orders | [options-orders](guides/options-orders.md) | [create-order](reference/create-order.md) |
| Multi-leg spreads & iron condors | [options-level-3-multi-leg](guides/options-level-3-multi-leg.md) | [create-order](reference/create-order.md) |
| Exercise & assignment events | [options-events](guides/options-events.md) | [option-exercise](reference/option-exercise.md) |
| Options chain (Greeks, IV, OI) | — | [option-chain](reference/option-chain.md) |
| Contract metadata & filtering | — | [get-option-contracts](reference/get-option-contracts.md) |
| Historical bars (OHLCV) | [historical-market-data](guides/historical-market-data.md) | [option-historical-bars](reference/option-historical-bars.md) |
| Latest trade price | — | [option-latest-trades](reference/option-latest-trades.md) |
| Real-time streaming | [streaming-market-data](guides/streaming-market-data.md) | — |

### Order Management

| Capability | Guide | Reference |
| --- | --- | --- |
| Place any order type | [working-with-orders](guides/working-with-orders.md) | [create-order](reference/create-order.md) |
| Bracket / OTO / OCO orders | [working-with-orders](guides/working-with-orders.md) | [create-order](reference/create-order.md) |
| Retrieve & cancel orders | — | [get-orders](reference/get-orders.md) |
| Stream trade updates (WebSocket) | [working-with-orders](guides/working-with-orders.md) | — |

### Positions & Portfolio

| Capability | Guide | Reference |
| --- | --- | --- |
| List & inspect positions | [working-with-positions](guides/working-with-positions.md) | [get-positions](reference/get-positions.md) |
| Close positions | — | [get-positions](reference/get-positions.md) |
| Asset eligibility check | — | [get-assets](reference/get-assets.md) |

### Setup & Auth

| Capability | Guide | Reference |
| --- | --- | --- |
| API endpoints & authentication | [getting-started](guides/getting-started.md) | — |
| Python SDK setup | [getting-started](guides/getting-started.md) | — |
| Stream authentication | [streaming-market-data](guides/streaming-market-data.md) | — |

---

## Key Constants

### OCC Symbol Format
```
{UNDERLYING}{YYMMDD}{C/P}{STRIKE × 1000, 8-digit padded}

Examples:
  AAPL250117C00150000  →  AAPL, Jan 17 2025, Call, $150 strike
  SPY250321P00480000   →  SPY, Mar 21 2025, Put, $480 strike
```

### Data Feed Decision
- **Paper trading / dev:** use `feed=indicative` (free)
- **Live trading:** use `feed=opra` (requires OPRA subscription, real-time)

### Options Order Constraints
- Order types: `market`, `limit` only
- Time in force: `day` only
- Max MLeg legs: 4
- No GTC, no extended hours, no stop or trailing stop

### Data Availability
- Options historical bars: **available since February 2024 only**
- Stock historical bars: 6+ years

---

## Bot Integration Points

| Task | Module |
| --- | --- |
| Options chain (Greeks, snapshots) | `integrations/alpaca/options_data.py` |
| Order placement | `integrations/alpaca/orders.py` |
| Position management | `integrations/alpaca/positions.py` |
| Stock/crypto market data | `integrations/alpaca/market_data.py` |
| Account info (buying power) | `integrations/alpaca/account.py` |
| Asset eligibility | `integrations/alpaca/assets.py` |
| Client factory (paper/live) | `integrations/alpaca/client.py` |
