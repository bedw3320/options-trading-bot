# Vault Health Report — 2026-02-20

## Summary
Overall: HEALTHY

## Metrics

| Metric | Value |
|--------|-------|
| Total notes | 73 (9 MOCs + 64 atomic claims) |
| Schema compliance | 100% — all required fields present |
| Dangling links | 0 (2 found and resolved) |
| Orphaned notes | 0 |
| Category coverage | All 8 categories populated |
| Average links/note | ~6.3 |

## Category Distribution

| Category | Count |
|----------|-------|
| parameter-range | 12 |
| open-question | 10 |
| instrument-profile | 9 |
| regime-filter | 8 |
| greek-dynamic | 8 |
| academic-claim | 7 |
| trade-mechanic | 7 |
| failure-mode | 3 |

## Actions Taken

1. Created `60-90 DTE suitable for macro EM thesis plays targeting 20 percent moves.md` — resolved dangling link from execution-parameters.md
2. Created `CBOE SKEW index is free via Barchart and useful as macro regime filter for SPX.md` — resolved dangling link from screening-and-filters.md

## Source Document

Seeded from: `research/research_v0_ Options Risk Reversal Strategy.md` (318 lines)
Extraction yield: 64 atomic claims from 1 source document

## Next Steps

- Monitor for parameter staleness (instrument-profile notes have `confidence: experimental` with Feb 2026 market data)
- Consider adding more failure-mode notes (currently lowest category at 3)
- Run `/project:reweave` after adding new research sources to update existing notes
