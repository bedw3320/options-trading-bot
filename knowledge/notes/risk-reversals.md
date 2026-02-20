---
description: "Domain MOC for zero-cost risk reversal strategy construction, calibration, and management"
type: moc
level: domain
created: 2026-02-20
---

# Risk Reversals

Zero-cost risk reversal strategy: sell overpriced puts, finance OTM calls, harvest skew premium.

## Strategy Construction

- [[zero-cost risk reversals sell overpriced puts to finance OTM calls in elevated-skew environments]]
- [[the zero-cost calibration algorithm starts at 20-delta put and finds the call strike matching the credit]]
- [[optimal short put strike is 15-25 delta at 7-15 percent OTM where skew curve is richest]]

## Strike and Expiry Selection

- [[Goldman 10-year study shows 15 percent OTM puts achieve highest Sharpe ratio of 0.85]]
- [[30-45 DTE is the primary vehicle for 10 percent target moves]]
- [[bid-ask spread on each leg must be 10 percent or less of mid-market premium]]

## Risk Management

- [[stop-loss at put strike breach plus 3 percent for US and 5 percent for EM]]
- [[defined-risk structures are recommended for EM positions buying 10-delta put protection]]
- [[partial delta hedging at 50-70 percent weekly provides better risk-adjusted returns than daily]]

## Dynamic Adjustments

- [[vol spike without price move marks negatively due to skew steepening on short put]]
- [[at 21 DTE remaining assess position and roll to next monthly if thesis intact]]

## Related

- [[greeks-and-volatility]]
- [[screening-and-filters]]
- [[execution-parameters]]
- [[em-etf-characteristics]]
