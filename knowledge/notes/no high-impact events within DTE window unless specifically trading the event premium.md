---
description: "Event calendar filter: avoid earnings, CB decisions, elections within the option's DTE window unless the trade specifically targets event premium"
category: regime-filter
created: 2026-02-20
source: "research_v0_ Options Risk Reversal Strategy.md"
confidence: likely
topics: ["[[screening-and-filters]]"]
---

The event calendar filter excludes positions where high-impact events (earnings, central bank decisions, elections) fall within the DTE window — unless the trade specifically targets the event premium.

Events create binary outcomes that can gap through strikes, making delta hedging ineffective. The risk reversal's negative gamma on the downside makes it especially vulnerable to gap moves through the short put strike.

Data source: Earnings Whispers API or manual event calendar.

## Connections

- [[EM ETFs trade US hours but reference overnight markets creating gap risk from policy announcements]]
- [[stop-loss at put strike breach plus 3 percent for US and 5 percent for EM]]

---
*Topics: [[screening-and-filters]]*
