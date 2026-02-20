---
description: "Open: verify Alpaca supports multi-leg combo orders for risk reversals (2-3 legs including protection put)"
category: open-question
created: 2026-02-20
source: "research_v0_ Options Risk Reversal Strategy.md"
confidence: experimental
topics: ["[[open-questions]]"]
---

Unresolved: confirm that the current execution broker (Alpaca) supports combo orders for 2-3 leg options structures. Risk reversals require simultaneous execution of the short put and long call; defined-risk versions add a third leg (protection put). If Alpaca doesn't support combo orders, may need to leg in sequentially with slippage risk.

The research document originally referenced IBKR TWS API via ib_insync for combo orders, but we're staying on Alpaca for now.

## Connections
- [[the zero-cost calibration algorithm starts at 20-delta put and finds the call strike matching the credit]]
- [[defined-risk structures are recommended for EM positions buying 10-delta put protection]]

---
*Topics: [[open-questions]]*
