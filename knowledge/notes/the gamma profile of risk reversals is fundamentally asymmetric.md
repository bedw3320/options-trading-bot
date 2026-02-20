---
description: "Positive convexity on upside (call gamma accelerates profits), negative convexity on downside (short put gamma amplifies losses)"
category: greek-dynamic
created: 2026-02-20
source: "research_v0_ Options Risk Reversal Strategy.md"
confidence: likely
topics: ["[[greeks-and-volatility]]", "[[risk-reversals]]"]
---

The gamma profile of risk reversals is fundamentally asymmetric: positive convexity on the upside (call gamma accelerates profits), negative convexity on the downside (short put gamma amplifies losses). This is the core structural trade-off — a gamma mortgage that funds upside convexity.

When the underlying falls toward the put strike, the short put approaches ATM where gamma peaks. The long call, now deep OTM, contributes essentially zero gamma. The position accelerates into losses with no offsetting convexity from the call leg.

## Connections

- [[a 25-delta put and 15-delta call risk reversal initializes at approximately plus 0.40 delta]]
- [[stop-loss at put strike breach plus 3 percent for US and 5 percent for EM]]

---
*Topics: [[greeks-and-volatility]], [[risk-reversals]]*
