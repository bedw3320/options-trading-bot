---
description: "ORATS Data API ($399/yr): pre-calculated skew slope/deriv, ATM vol, IV rank/percentile, historical data to 2007 — optimal for bot screening"
category: trade-mechanic
created: 2026-02-20
source: "research_v0_ Options Risk Reversal Strategy.md"
confidence: likely
topics: ["[[screening-and-filters]]"]
---

ORATS Data API ($399/year) provides pre-calculated skew parameters (slope, deriv), ATM vol, IV rank/percentile, and historical data back to 2007. This is optimal for systematic screening because the skew calculations are pre-computed rather than requiring real-time options chain parsing.

Note: Currently staying on Alpaca execution stack, not migrating to IBKR/ORATS yet. ORATS would be a data source addition, not an execution change.

## Connections
- [[skew percentile rank must be 75th or above on 1-year lookback for entry]]
- [[assess whether end-of-day screening is sufficient or intraday needed]]

---
*Topics: [[screening-and-filters]]*
