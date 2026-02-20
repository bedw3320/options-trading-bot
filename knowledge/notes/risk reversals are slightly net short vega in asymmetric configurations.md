---
description: "25Δ put / 15Δ call config is slightly net short vega because ATM put carries more vega than far-OTM call; critical during IV spikes"
category: greek-dynamic
created: 2026-02-20
source: "research_v0_ Options Risk Reversal Strategy.md"
confidence: likely
topics: ["[[greeks-and-volatility]]", "[[risk-reversals]]"]
---

At initiation, a risk reversal is approximately vega-neutral for symmetric structures but slightly net short vega for the asymmetric (25Δ put / 15Δ call) configuration because the ATM put carries more vega than the far-OTM call.

However, this first-order analysis is misleading. The critical dynamic: [[during IV spikes skew steepens making risk reversals functionally net short vol even when nominally vega-neutral]].

## Connections

- [[during IV spikes skew steepens making risk reversals functionally net short vol even when nominally vega-neutral]]
- [[volga is approximately zero in risk reversals distinguishing them from straddles]]

---
*Topics: [[greeks-and-volatility]], [[risk-reversals]]*
