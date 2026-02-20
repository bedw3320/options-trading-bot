---
description: "A uniform +5 vol-point ATM increase translates to +7-8 pts on 25Δ puts but only +3-4 pts on 15Δ calls — position is functionally short vol in crises"
category: greek-dynamic
created: 2026-02-20
source: "research_v0_ Options Risk Reversal Strategy.md"
confidence: likely
topics: ["[[greeks-and-volatility]]", "[[risk-reversals]]"]
---

During IV spikes, skew steepens — put IV rises disproportionately to call IV. A uniform +5 vol-point ATM increase might translate to +7-8 points on 25Δ puts but only +3-4 points on 15Δ calls. The position is functionally net short vol during crises, even when nominally vega-neutral at initiation.

This is the hidden vega risk in risk reversals: the first-order vega calculation understates the actual vol exposure because it assumes parallel shifts in the volatility surface, when in reality the surface tilts during stress.

## Connections

- [[risk reversals are slightly net short vega in asymmetric configurations]]
- [[vanna is the dominant second-order Greek in risk reversals creating dangerous feedback in equity markets]]
- [[vol spike without price move marks negatively due to skew steepening on short put]]

---
*Topics: [[greeks-and-volatility]], [[risk-reversals]]*
