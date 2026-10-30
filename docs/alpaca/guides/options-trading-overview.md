# Options Trading Overview

> **Source:** https://docs.alpaca.markets/docs/options-trading-overview
> **Last scraped:** 2026-03-06
> **Relevance:** Full lifecycle of options on Alpaca — what's supported, trading levels, buying power rules, positions, exercise/assignment, expiration handling.

---

## Initial Options Offering

### Supported
- US listed equities options, all American style
- Level 1–3 options trading
- Fully Disclosed partner relationships
- Automatic account approval process via the API + SSE events
- Ability to exercise options via the API
- DNE (do not exercise) via API
- New options-specific activities
- Access to options market data (at a cost)

### Not Supported
- LCT (local currency trading)
- Fractional options
- Extended hours

---

## Trading Levels

| Level | Supported Trades | Validation |
| --- | --- | --- |
| 0 | Options trading is disabled | NA |
| 1 | Sell a covered call; Sell cash-secured put | Must own sufficient underlying shares; Must have sufficient options buying power |
| 2 | Level 1 + Buy a call; Buy a put | Must have sufficient options buying power |

Level 3 (multi-leg) is also supported — see `guides/options-level-3-multi-leg.md`.

If a user tries to trade above their level:
```json
{"code": 40310000, "message": "account not eligible for level2 options trading"}
```

---

## Order Types Supported
- Options symbol (e.g. `AAPL240223C00095000`)
- Time in force: **day only**
- Order types: **market and limit**
- Replace and cancel orders supported

**Not supported for options:**
- Extended hours
- Fractional or notional order support

---

## Option Symbol Format

`{UNDERLYING}{YYMMDD}{C/P}{STRIKE × 1000 padded to 8 digits}`

Example: `AAPL240223C00095000` = AAPL Feb 23 2024 $95 Call

---

## Asset Master / Contract Object

```json
{
  "id": "1fb904df-961a-4a07-a924-53a437626db2",
  "symbol": "AAPL240223C00095000",
  "name": "AAPL Feb 23 2024 95 Call",
  "status": "active",
  "tradable": true,
  "expiration_date": "2024-02-23",
  "root_symbol": "AAPL",
  "underlying_symbol": "AAPL",
  "underlying_asset_id": "b0b6dd9d-8b9b-48a9-ba46-b9d54906e415",
  "type": "call",
  "style": "american",
  "strike_price": "95",
  "size": "100",
  "open_interest": "12",
  "open_interest_date": "2024-02-22",
  "close_price": "89.35",
  "close_price_date": "2024-02-22"
}
```

---

## Order Examples

**Buying a call:**
```json
{"symbol": "PTON240126C00000500", "qty": "1", "side": "buy", "type": "market", "time_in_force": "day"}
```

**Buying a put:**
```json
{"symbol": "TSLA240126P00210000", "qty": "1", "side": "buy", "type": "market", "time_in_force": "day"}
```

**Selling a covered call:**
```json
{"symbol": "AAPL240126C00050000", "qty": "1", "side": "sell", "type": "market", "time_in_force": "day"}
```

**Selling a cash-secured put:**
```json
{"symbol": "QS240126P00006500", "qty": "1", "side": "sell", "type": "market", "time_in_force": "day"}
```

---

## Buying Power Rules

- **Buying a call or put:** Must have `options_buying_power` ≥ premium × 100 × contracts
- **Selling a covered call:** Must own 100 shares per contract
- **Selling a cash-secured put:** Must have buying power ≥ (strike × 100) − premium

Error format:
```json
{"options_buying_power": "7267.84", "code": 40310000, "cost_basis": "38000", "message": "insufficient options buying power"}
```

---

## Option Positions

Options show up in the same `/positions` endpoint with `asset_class: "us_option"`:

```json
{
  "asset_id": "fe4f43e5-60a4-4269-ba4c-3d304444d58b",
  "symbol": "PTON240126C00000500",
  "asset_class": "us_option",
  "qty": "2",
  "avg_entry_price": "6.05",
  "side": "long",
  "market_value": "1068",
  "cost_basis": "1210",
  "unrealized_pl": "-142",
  "current_price": "5.34",
  "qty_available": "2"
}
```

---

## Exercise and Assignment

### Exercising
- Call exercise → buy underlying at strike price
- Put exercise → sell underlying at strike price
- Activity types generated: `OPEXC` (removes option position) + `OPTRD` (underlying trade)
- Exercise requests outside market hours are **rejected**

### Assignment (for sellers)
- The OCC randomly assigns; can happen **overnight**
- Activity types: `OPASN` (removes option position) + `OPTRD` (underlying trade)
- Call assignment → obligation to **sell** stock at strike
- Put assignment → obligation to **buy** stock at strike

---

## Expiration Handling (Alpaca manages automatically)

Starting **3:30 PM ET** on expiration day:
- ITM by ≥ $0.01 with sufficient BP → auto-exercise
- ITM by ≥ $0.01 without sufficient BP → **Alpaca liquidates**
- Covered calls / cash-secured puts ITM → **Alpaca auto-assigns after close**
- ATM or OTM → expires worthless (`OPEXP` activity)

---

## Market Data Endpoints

| Endpoint | Description |
| --- | --- |
| Latest Quotes | Latest quotes, multi-symbol |
| Latest Trades | Latest trades, multi-symbol |
| Historical Trades | Historical trades, multi-symbol |
| Snapshots (Option Chain) | Quotes + trades + Greeks for all contracts |
| Historical Bars | OHLCV bars, multi-symbol |
