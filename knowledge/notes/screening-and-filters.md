---
description: "Topic MOC for entry screening filters, data sources, and signal layering for risk reversal trades"
type: moc
level: topic
created: 2026-02-20
---

# Screening and Filters

Quantitative entry filters for identifying tradeable skew in risk reversal candidates.

## Filter Stack (Priority Order)

- [[skew percentile rank must be 75th or above on 1-year lookback for entry]]
- [[25-delta risk reversal of minus 5 vol points is tradeable and minus 8 to 10 is a strong signal]]
- [[IV percentile must be 60 percent or above confirming options are broadly expensive]]
- [[CBOE SKEW above 130 indicates significantly better win rates and above 140 is strongest signal]]
- [[implied vol must exceed trailing realized vol to confirm overpricing]]
- [[no high-impact events within DTE window unless specifically trading the event premium]]

## EM-Specific Filters

- [[put-call IV ratio filter requires 25-delta put IV divided by call IV above 1.15 minimum]]
- [[DXY regime filter reduces EM risk reversal exposure when USD trends strongly higher]]

## Data Sources

- [[ORATS provides pre-calculated skew parameters at 399 per year optimal for systematic screening]]
- [[CBOE SKEW index is free via Barchart and useful as macro regime filter for SPX]]

## Related

- [[risk-reversals]]
- [[execution-parameters]]
- [[options-trading-overview]]
