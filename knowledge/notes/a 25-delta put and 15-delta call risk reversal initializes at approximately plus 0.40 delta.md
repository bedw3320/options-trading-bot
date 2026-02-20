---
description: "Initial delta of a 25Δ put / 15Δ call risk reversal is ~+0.40 (moderately bullish), rising to 0.80-1.0 at call strike"
category: greek-dynamic
created: 2026-02-20
source: "research_v0_ Options Risk Reversal Strategy.md"
confidence: likely
instruments: [SPY, EEM, EWZ, FXI]
topics: ["[[greeks-and-volatility]]", "[[risk-reversals]]"]
---

A 25Δ put / 15Δ call zero-cost risk reversal initializes at approximately +0.40 delta — moderately bullish. The delta evolves asymmetrically:

- **Underlying rallies halfway to call strike:** Delta rises to +0.60-0.70 (approaching synthetic long)
- **Underlying at or above call strike:** Delta ~0.80-1.0 — full synthetic long territory
- **Underlying falls toward put strike:** Short put approaches ATM (peak negative gamma), call gamma vanishes — position accelerates into losses

This asymmetric delta evolution is the core appeal of the risk reversal: limited initial directional commitment with accelerating upside participation.

## Connections

- [[the gamma profile of risk reversals is fundamentally asymmetric]]
- [[vanna is the dominant second-order Greek in risk reversals creating dangerous feedback in equity markets]]

---
*Topics: [[greeks-and-volatility]], [[risk-reversals]]*
