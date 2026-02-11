---
name: exa-financial-reports
description: Search SEC filings, earnings reports, and financial documents for fundamental analysis of swing trade candidates. Use when researching 10-K/10-Q filings, earnings surprises, revenue trends, or risk factors.
context: fork
---

# Financial Report Search (Exa)

## Tool Restriction

Use `web_search_advanced_exa` with `category: "financial report"`. The `excludeText` parameter is NOT supported — use query phrasing to narrow results instead.

## Token Isolation

Run Exa searches in spawned Task agents to keep the main context clean. Agents should extract key financial figures and distill before returning.

## Trading Bot Context

Use this skill for **fundamental analysis** supporting swing trade decisions:
- Check recent earnings reports before entering a position
- Find revenue/profit trends that confirm or contradict technical signals
- Look for earnings surprises that could drive multi-day momentum
- Identify risk factors that might invalidate a trade thesis
- Verify company health before options plays (avoid selling puts on shaky companies)

## Supported Parameters

- `query` (required)
- `numResults`
- `type` — "auto", "fast", "deep", "neural"
- `includeDomains` — e.g., `["sec.gov", "investor.apple.com"]`
- `excludeDomains`
- `startPublishedDate` / `endPublishedDate` — ISO 8601
- `includeText` — **single-item arrays only** (multi-item causes 400)
- `enableSummary` / `summaryQuery` — great for extracting specific metrics
- `enableHighlights` / `highlightsQuery` — pull out key figures
- `livecrawl` / `livecrawlTimeout`

## Examples

### Pre-trade earnings check
```
web_search_advanced_exa {
  "query": "NVDA nvidia Q4 2025 earnings revenue guidance",
  "category": "financial report",
  "startPublishedDate": "2025-10-01",
  "numResults": 10,
  "type": "auto",
  "enableHighlights": true,
  "highlightsQuery": "What were revenue, EPS, and forward guidance?"
}
```

### Earnings surprise screening
```
web_search_advanced_exa {
  "query": "earnings beat expectations revenue surprise technology",
  "category": "financial report",
  "startPublishedDate": "2026-01-15",
  "numResults": 20,
  "type": "deep",
  "enableSummary": true,
  "summaryQuery": "Which companies beat earnings and by how much?"
}
```

### Risk factor analysis (before options play)
```
web_search_advanced_exa {
  "query": "AAPL apple 10-K risk factors 2025",
  "category": "financial report",
  "includeDomains": ["sec.gov"],
  "numResults": 5,
  "type": "deep",
  "enableHighlights": true,
  "highlightsQuery": "What are the major risk factors?"
}
```

### SEC filing lookup
```
web_search_advanced_exa {
  "query": "TSLA tesla 10-Q quarterly report 2025",
  "category": "financial report",
  "includeDomains": ["sec.gov"],
  "startPublishedDate": "2025-06-01",
  "numResults": 5,
  "type": "auto"
}
```

## Output Format

Return:
1. **Key financials** — revenue, EPS, margins, guidance (with period)
2. **Trend** — QoQ and YoY direction
3. **Surprises** — beat/miss vs consensus, magnitude
4. **Risk factors** — anything relevant to the trade thesis
5. **Sources** — filing/report URLs
6. **Trading relevance** — how this data supports or undermines the current strategy signal
