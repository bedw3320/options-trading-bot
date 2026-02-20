---
description: "Strongly positive vanna means delta increases as vol rises — in equity markets with negative spot-vol correlation, position gets longer as underlying falls"
category: greek-dynamic
created: 2026-02-20
source: "research_v0_ Options Risk Reversal Strategy.md"
confidence: likely
topics: ["[[greeks-and-volatility]]", "[[risk-reversals]]"]
---

Both legs of a risk reversal contribute positive vanna: the long OTM call has positive vanna directly; shorting the OTM put (negative vanna) also contributes positive vanna when the sign is reversed. Net result: strongly positive vanna — delta increases as volatility rises.

In equity markets with negative spot-vol correlation (prices fall → vol rises), this creates a dangerous feedback loop: the position gets longer delta precisely as the underlying is falling. This amplifies losses beyond what first-order Greeks suggest.

**The put skew IS the vanna premium — selling it means accepting this unfavorable correlation exposure.**

## Connections

- [[during IV spikes skew steepens making risk reversals functionally net short vol even when nominally vega-neutral]]
- [[USD strengthening simultaneously pushes EM equities lower increases EM IV and amplifies vanna feedback]]
- [[the gamma profile of risk reversals is fundamentally asymmetric]]

---
*Topics: [[greeks-and-volatility]], [[risk-reversals]]*
