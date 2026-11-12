# Current Goals

Vault research vs product-in-force: notes under `knowledge/notes/` are research
claims. Live product policy (locked 2026-11-11) is
[`exit-strategy.md`](exit-strategy.md) and [`STATUS.md`](../../STATUS.md)
walking-slice Epic 6 — standard RR, no protective put, no defined max loss,
manual flatten only. Do not treat vault 21-DTE / defined-risk notes as in-force.

## Active

- [ ] Walking-slice Epic 4 Mini paper evidence (reconcile / debrief / manual flatten on DUT116016) — not yellow-zone auto-exits
- [ ] Interview strategy brain with `/project:expert-interview`
- [ ] Expand failure-mode notes (only 3 — need vol collapse, liquidity crisis, skew inversion)
- [ ] Later: rewrite core-strategy YAML to the locked standard RR (not this docs cleanup)

## Deferred

- [ ] Integrate ORATS data feed for live skew screening
- [ ] Build backtesting framework for risk reversal parameters
- [ ] Expand knowledge graph with additional academic sources

## Completed

- [x] Seed knowledge graph from risk reversal research document (73 notes, 9 MOCs)
- [x] Build initial MOC structure for options trading domain
- [x] Identify gaps in research that need further investigation (10 open questions tracked)
- [x] Build expert interview command for strategy brain extraction
