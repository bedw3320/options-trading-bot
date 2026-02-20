# Derivation Record

Generated: 2026-02-20
Preset base: Research
Domain: Options trading strategy research & execution

## Conversation Signals

- Domain: options trading (risk reversals, Greeks, skew, volatility surface)
- Knowledge types: academic claims, parameter ranges, Greek dynamics, failure modes, regime filters, trade post-mortems
- Connection patterns: claims link to sources, parameters link to backtests, strategies link to instruments
- Growth: steady — manual research notes + occasional bot output capture
- Output: refined strategy YAML files + agent context enrichment
- Execution stack: Alpaca (paper/live), not IBKR/ORATS yet
- Curation style: manual-first, quality over quantity

## Dimension Positions

| Dimension | Position | Confidence | Rationale |
|-----------|----------|------------|-----------|
| Granularity | 0.8 (atomic) | HIGH | One claim per note — enables cross-source comparison of Greeks behavior, parameter ranges |
| Organization | 0.3 (flat) | HIGH | Flat + MOC navigation — options concepts cross-cut (Greeks affect multiple strategies) |
| Linking | 0.7 (explicit + semantic) | HIGH | Typed wiki-links between claims, parameters, instruments |
| Processing | 0.8 (full pipeline) | HIGH | Full extract-connect-verify-reweave cycle for research documents |
| Navigation | 3-tier | HIGH | Hub → domain MOC → topic MOC → notes |
| Maintenance | 0.6 (condition-based) | MEDIUM | Review when orphans accumulate or new research contradicts existing claims |
| Schema | Moderate | HIGH | YAML frontmatter with trading-specific fields |
| Automation | 0.8 (full) | HIGH | Full pipeline from day one |

## Vocabulary Mapping

| Level | Universal | Options Trading |
|-------|-----------|----------------|
| Note type | claim | claim |
| Processing verb | reduce | reduce |
| Connection verb | reflect | reflect |
| Navigation unit | MOC | topic map |
| Collection name | notes/ | notes/ |
| Capture zone | inbox/ | inbox/ |
| Primary verb | extract | extract |

## Extraction Categories

- `academic-claim` — Published research findings with citations
- `parameter-range` — Quantitative thresholds, deltas, DTE ranges, sizing rules
- `greek-dynamic` — How Greeks behave under specific conditions
- `failure-mode` — Scenarios where the strategy breaks down
- `regime-filter` — Market conditions that gate entry/exit
- `open-question` — Unresolved items requiring further research or backtesting
- `trade-mechanic` — Execution details: strike selection, roll timing, order types
- `instrument-profile` — Characteristics of specific tickers/ETFs

## Failure Mode Risks

- Collector's Fallacy (HIGH) — options research is abundant
- Orphan Drift (HIGH) — high creation volume without mandatory connection
- Verbatim Risk (HIGH) — temptation to copy parameter tables verbatim
- Parameter Staleness (MEDIUM) — market conditions change; parameters need freshness dates

## Active Feature Blocks

Always: atomic-notes, wiki-links, mocs, processing-pipeline, schema, maintenance, self-evolution, session-rhythm, templates, ethical-guardrails, helper-functions, graph-analysis
Conditional: semantic-search (deferred — qmd not installed)
Disabled: self-space (goals route to ops/goals.md), personality, multi-domain
