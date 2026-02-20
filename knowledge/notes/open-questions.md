---
description: "Topic MOC tracking unresolved research items, backtesting needs, and architectural decisions"
type: moc
level: topic
created: 2026-02-20
---

# Open Questions

Unresolved items from the risk reversal research that need further investigation or backtesting.

## Strategy Design

- [[develop Kelly-based or fixed-fractional sizing that survives minus 77 percent EWZ drawdown]]
- [[quantify cost-benefit of 10-delta put protection on EM positions at various skew levels]]
- [[empirically test 50-70 percent partial hedge at weekly vs daily rebalancing]]
- [[build specific logic for EWZ-type inverted skew scenarios]]

## Bot Architecture

- [[confirm combo order support for 2-3 leg structures on current broker]]
- [[assess whether end-of-day screening is sufficient or intraday needed]]
- [[evaluate OptionMetrics vs ORATS historical data for regime-conditional backtests]]
- [[design real-time vanna monitoring alerting when position vanna exceeds threshold]]

## Macro Regime Filters

- [[define quantitative DXY trigger for reducing EM exposure]]
- [[operationalize Qiao et al EMVRP as forward-entry signal for 6-month-plus horizon]]

## Related

- [[risk-reversals]]
- [[options-trading-overview]]
