---
description: "Step 1: 20Δ put at mid-market → Step 2: find call where ask ≈ put credit → Step 3: if excess, move call closer to ATM → Step 4: verify spread ≤10% of mid"
category: trade-mechanic
created: 2026-02-20
source: "research_v0_ Options Risk Reversal Strategy.md"
confidence: likely
topics: ["[[risk-reversals]]", "[[execution-parameters]]"]
---

The zero-cost calibration algorithm:

1. Identify put strike at 20-delta — where skew is richest. Price at mid-market.
2. Find call strike where ask price ≈ put credit received.
3. If excess put premium exists, move call closer to ATM (higher probability of profit) or accept small net credit as theta cushion.
4. Verify bid-ask spread on each leg ≤ 10% of mid-market premium. If put sells for $0.50, spread must be ≤ $0.05.

High skew allows buying closer-to-ATM calls than normal — the put premium finances a better call strike.

## Connections

- [[optimal short put strike is 15-25 delta at 7-15 percent OTM where skew curve is richest]]
- [[bid-ask spread on each leg must be 10 percent or less of mid-market premium]]

---
*Topics: [[risk-reversals]], [[execution-parameters]]*
