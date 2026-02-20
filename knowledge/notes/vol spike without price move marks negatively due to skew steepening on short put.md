---
description: "Vol spike with no price move: short put vega loss exceeds long call vega gain due to skew steepening — response: roll put down, delta hedge, or add protection"
category: failure-mode
created: 2026-02-20
source: "research_v0_ Options Risk Reversal Strategy.md"
confidence: likely
topics: ["[[risk-reversals]]", "[[greeks-and-volatility]]"]
---

When volatility spikes without a price move, the position marks negatively because the short put's vega loss exceeds the long call's vega gain due to skew steepening.

Response options:
1. Roll put to lower strike
2. Add delta hedge (sell shares/futures)
3. Buy further-OTM put to convert to defined-risk spread

## Connections
- [[during IV spikes skew steepens making risk reversals functionally net short vol even when nominally vega-neutral]]
- [[risk reversals are slightly net short vega in asymmetric configurations]]
- [[stop-loss at put strike breach plus 3 percent for US and 5 percent for EM]]

---
*Topics: [[risk-reversals]], [[greeks-and-volatility]]*
