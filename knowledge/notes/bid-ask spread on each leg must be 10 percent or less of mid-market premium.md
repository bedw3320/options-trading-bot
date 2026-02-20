---
description: "Liquidity gate: bid-ask spread ≤10% of mid-market premium on each leg. If put sells for $0.50, spread must be ≤$0.05."
category: parameter-range
created: 2026-02-20
source: "research_v0_ Options Risk Reversal Strategy.md"
confidence: likely
topics: ["[[execution-parameters]]"]
---

Bid-ask spread on each leg must be 10% or less of mid-market premium. If the put sells for $0.50, the spread must be ≤ $0.05. This ensures execution costs don't erode the skew premium edge.

## Connections
- [[the zero-cost calibration algorithm starts at 20-delta put and finds the call strike matching the credit]]
- [[EM ETF options require monthly expirations only with minimum OI of 1000 contracts per leg]]

---
*Topics: [[execution-parameters]]*
