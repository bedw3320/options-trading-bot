# Options Level 3 — Multi-Leg Orders

> **Source:** https://docs.alpaca.markets/docs/options-level-3-trading
> **Last scraped:** 2026-03-06
> **Relevance:** How to place spreads, iron condors, and other multi-leg strategies as a single atomic order. Critical for risk-defined spread strategies.

---

## What are Multi-Leg (MLeg) Orders?

A multi-leg order is a **single, combined order** that includes multiple option contracts — calls, puts, or shares — on the same underlying security. All legs execute as one unit or not at all, eliminating partial fill risk.

**Use cases:** Call spreads, put spreads, iron condors, calendars, rolls.

**Key benefit:** Avoids slippage from sequential leg execution, reduces margin requirements vs. individual positions (universal spread rule).

---

## How to Submit an MLeg Order

Set `order_class: "mleg"` with a `legs` array. Each leg specifies:
- `symbol`: Option contract symbol
- `side`: `"buy"` or `"sell"`
- `ratio_qty`: Relative size (must be in simplest form — GCD of all ratios must be 1)
- `position_intent`: `buy_to_open`, `buy_to_close`, `sell_to_open`, `sell_to_close`

```json
{
  "order_class": "mleg",
  "qty": "1",
  "type": "limit",
  "limit_price": "0.6",
  "time_in_force": "day",
  "legs": [
    {"symbol": "AAPL250117P00200000", "ratio_qty": "1", "side": "buy", "position_intent": "buy_to_open"},
    {"symbol": "AAPL250117C00250000", "ratio_qty": "1", "side": "buy", "position_intent": "buy_to_open"}
  ]
}
```

**Note:** For MLeg, `limit_price` is a **net debit/credit**:
- Positive = debit (you pay)
- Negative = credit (you receive)

---

## Strategy Examples

### Long Call Spread (Debit)
Buy lower-strike call, sell higher-strike call:
```json
{
  "order_class": "mleg",
  "qty": "1",
  "type": "limit",
  "limit_price": "1.00",
  "time_in_force": "day",
  "legs": [
    {"symbol": "AAPL250117C00190000", "ratio_qty": "1", "side": "buy", "position_intent": "buy_to_open"},
    {"symbol": "AAPL250117C00210000", "ratio_qty": "1", "side": "sell", "position_intent": "sell_to_open"}
  ]
}
```

### Long Put Spread (Debit)
Buy higher-strike put, sell lower-strike put:
```json
{
  "order_class": "mleg",
  "qty": "1",
  "type": "limit",
  "limit_price": "1.25",
  "time_in_force": "day",
  "legs": [
    {"symbol": "AAPL250117P00210000", "ratio_qty": "1", "side": "buy", "position_intent": "buy_to_open"},
    {"symbol": "AAPL250117P00190000", "ratio_qty": "1", "side": "sell", "position_intent": "sell_to_open"}
  ]
}
```

### Iron Condor (Credit)
Sell put spread + sell call spread — profits if underlying stays range-bound:
```json
{
  "order_class": "mleg",
  "qty": "1",
  "type": "limit",
  "limit_price": "1.80",
  "time_in_force": "day",
  "legs": [
    {"symbol": "AAPL250117P00190000", "ratio_qty": "1", "side": "buy",  "position_intent": "buy_to_open"},
    {"symbol": "AAPL250117P00195000", "ratio_qty": "1", "side": "sell", "position_intent": "sell_to_open"},
    {"symbol": "AAPL250117C00205000", "ratio_qty": "1", "side": "sell", "position_intent": "sell_to_open"},
    {"symbol": "AAPL250117C00210000", "ratio_qty": "1", "side": "buy",  "position_intent": "buy_to_open"}
  ]
}
```

### Roll a Call Spread (strike change)
Close existing spread + open new one at different strikes in one transaction:
```json
{
  "order_class": "mleg",
  "qty": "1",
  "type": "limit",
  "limit_price": "2.05",
  "time_in_force": "day",
  "legs": [
    {"symbol": "AAPL250117C00200000", "ratio_qty": "1", "side": "buy",  "position_intent": "buy_to_close"},
    {"symbol": "AAPL250117C00205000", "ratio_qty": "1", "side": "sell", "position_intent": "sell_to_close"},
    {"symbol": "AAPL250117C00210000", "ratio_qty": "1", "side": "sell", "position_intent": "sell_to_open"},
    {"symbol": "AAPL250117C00215000", "ratio_qty": "1", "side": "buy",  "position_intent": "buy_to_open"}
  ]
}
```

### Roll a Calendar Spread (expiration change)
Close near-term legs, open far-term legs:
- Legs with `250117` suffix → close (`buy_to_close`, `sell_to_close`)
- Legs with `250224` suffix → open (`sell_to_open`, `buy_to_open`)

---

## Margin Requirements (Universal Spread Rule)

Alpaca uses a **piecewise payoff** approach (CBOE universal spread rule) rather than summing individual leg margins.

1. Model each option's payoff at every strike price present in the spread
2. Net the payoffs at each price point
3. Margin = maximum combined loss (worst-case scenario)

**Benefit:** Offsetting positions reduce margin vs. traditional per-leg calculation.

**Cost basis of MLeg order:**
`Cost Basis = Maintenance Margin + (Net Price × 100)`

Example — call credit spread (short 190 call, long 200 call):
- Margin: $1,000 (10-point spread × 100)
- Net price: -$5 credit → -$500
- Cost basis: $1,000 − $500 = **$500**

---

## Restrictions

1. **GCD rule:** `ratio_qty` values must be in simplest form (GCD = 1). `4:2` → reject; use `2:1`.
2. **No equity+options combos:** Cannot mix stock legs with option legs in one MLeg order.
3. **All legs must be covered within the order:** An MLeg with uncovered short legs (e.g., two naked short calls) is rejected. Short calls must be covered by long calls in the same order.
4. **Max 4 legs per order.**
5. **`time_in_force: "day"` only.**
