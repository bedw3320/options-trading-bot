---
description: "Hub MOC — entry point for the options trading knowledge graph"
type: moc
level: hub
created: 2026-02-20
---

# Options Trading Knowledge Graph

Entry point for all options trading research, strategy parameters, and execution knowledge.

**Not product-in-force.** Vault notes are research claims (many from the Feb 2026
RR archive). Live product policy (locked 2026-11-11) is
[`../ops/exit-strategy.md`](../ops/exit-strategy.md) and
[`../../STATUS.md`](../../STATUS.md) walking-slice Epic 6: standard RR, no
protective put, no defined max loss, manual flatten only. 21-DTE rolls and
defined-risk EM wings in notes below are vault claims, not current runner policy.

## Domain Maps

- [[options-trading-overview]] — Core concepts, strategy types, market structure
- [[greeks-and-volatility]] — Greek dynamics, volatility surface, vanna/volga
- [[risk-reversals]] — Zero-cost risk reversal strategy: construction, calibration, management
- [[open-questions]] — Unresolved research items and backtesting needs

## Instrument Profiles

- [[em-etf-characteristics]] — EEM, EWZ, FXI drawdown history, liquidity, gap risk
- [[spy-spx-baseline]] — SPX skew benchmarks, CBOE SKEW index, VIX dynamics

## Data Sources & Execution

- [[screening-and-filters]] — Entry filters, data sources, signal layering
- [[execution-parameters]] — Strike selection, DTE, position sizing, roll triggers
