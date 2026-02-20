---
description: "Short put theta offsets long call theta bleed; high-skew environments create slight theta positive (~$0.01-0.03/day); theta turns directional near strikes"
category: greek-dynamic
created: 2026-02-20
source: "research_v0_ Options Risk Reversal Strategy.md"
confidence: likely
topics: ["[[greeks-and-volatility]]", "[[risk-reversals]]"]
---

Zero-cost structure means short put theta collection roughly offsets long call theta bleed. High-put-skew environments create a slight theta positive (~$0.01-0.03/day on notional-neutral structure). Theta turns directional as underlying moves:

- **Near put strike:** Theta turns positive — short ATM put with peak theta, long far-OTM call with minimal theta
- **Near call strike:** Theta turns negative — long near-ATM call at peak theta burn, short far-OTM put contributing nothing

## Connections

- [[a 25-delta put and 15-delta call risk reversal initializes at approximately plus 0.40 delta]]
- [[the gamma profile of risk reversals is fundamentally asymmetric]]

---
*Topics: [[greeks-and-volatility]], [[risk-reversals]]*
