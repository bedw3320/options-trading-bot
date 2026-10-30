# Options Orders

> **Source:** https://docs.alpaca.markets/docs/options-orders
> **Last scraped:** 2026-03-06
> **Relevance:** Concrete order payload examples for all Tier 1 and Tier 2 options strategies with buying power requirements.

---

## Tier 1 Orders (requires Level 1 approval)

### Sell a Covered Call
```json
{
  "symbol": "AAPL231201C00195000",
  "qty": "2",
  "side": "sell",
  "type": "limit",
  "limit_price": "1.05",
  "time_in_force": "day"
}
```
**Requirement:** Account must hold 200 shares of AAPL (100 shares per contract).

### Sell a Cash-Secured Put
```json
{
  "symbol": "AAPL231201P00175000",
  "qty": "1",
  "side": "sell",
  "type": "market",
  "time_in_force": "day"
}
```
**Requirement:** Account must have $17,500 buying power ($175 strike × 100 shares × 1 contract).

---

## Tier 2 Orders (requires Level 2 approval)

### Buy a Call
```json
{
  "symbol": "AAPL240119C00190000",
  "qty": "1",
  "side": "buy",
  "type": "market",
  "time_in_force": "day"
}
```
**Requirement:** Buying power ≥ execution_price × 100 × contracts. Example: $5.10 fill → $510 required.

### Buy a Put
```json
{
  "symbol": "AAPL240119P00170000",
  "qty": "1",
  "side": "buy",
  "type": "market",
  "time_in_force": "day"
}
```
**Requirement:** Buying power ≥ execution_price × 100 × contracts. Example: $1.04 fill → $104 required.

---

## Key Rules
- Options use `time_in_force: "day"` only (no GTC, IOC, etc.)
- Order types: `market` or `limit` only (no stop, trailing_stop)
- `qty` is in contracts (1 contract = 100 shares of underlying)
- For multi-leg strategies (spreads, iron condors), see `guides/options-level-3-multi-leg.md`
