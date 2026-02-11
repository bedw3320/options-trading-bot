---
name: exa-company-research
description: Research companies, competitors, and market news for ticker due diligence. Use when evaluating a trade candidate's business fundamentals, competitive position, recent news, or sector dynamics.
context: fork
---

# Company Research (Exa)

## Tool Restriction

Use `web_search_advanced_exa`. Choose the appropriate `category` based on what you need:
- `company` — homepages, metadata (headcount, location, funding, revenue)
- `news` — press coverage, announcements, catalysts
- No category (`type: "auto"`) — general web results for deeper context

Do NOT use `web_search_exa` or other Exa tools.

## Filter Restrictions by Category

**`company` category** — does NOT support: `includeDomains`, `excludeDomains`, `startPublishedDate`, `endPublishedDate`, `startCrawlDate`, `endCrawlDate`

**`news` category** — supports all filters (domain + date work fine)

**Universal**: `includeText` and `excludeText` only support **single-item arrays**.

## Token Isolation

Run Exa searches in spawned Task agents. Use 2-3 query variations for coverage, merge and deduplicate before returning.

## Trading Bot Context

Use this skill for **ticker due diligence** before swing trades:
- Research what a company does before taking a position
- Find recent news catalysts (partnerships, product launches, management changes)
- Understand competitive landscape and market position
- Check for red flags (lawsuits, regulatory issues, insider selling)
- Evaluate sector trends and peer companies

## Examples

### Ticker due diligence
```
web_search_advanced_exa {
  "query": "Palantir PLTR business model revenue streams",
  "category": "company",
  "numResults": 10,
  "type": "auto"
}
```

### Recent news catalysts
```
web_search_advanced_exa {
  "query": "NVDA nvidia partnership deal announcement",
  "category": "news",
  "startPublishedDate": "2026-01-01",
  "numResults": 15,
  "type": "auto"
}
```

### Sector screening
```
web_search_advanced_exa {
  "query": "quantum computing companies publicly traded",
  "category": "company",
  "numResults": 20,
  "type": "deep"
}
```

### Red flag check
```
web_search_advanced_exa {
  "query": "TICKER lawsuit SEC investigation regulatory",
  "category": "news",
  "startPublishedDate": "2025-06-01",
  "numResults": 15,
  "type": "auto"
}
```

### Competitive analysis
```
web_search_advanced_exa {
  "query": "CrowdStrike competitors cybersecurity market share",
  "type": "deep",
  "livecrawl": "fallback",
  "numResults": 15,
  "includeDomains": ["techcrunch.com", "reuters.com", "bloomberg.com"]
}
```

## Output Format

Return:
1. **Company overview** — what they do, market cap, sector
2. **Recent catalysts** — news that could drive price action
3. **Competitive position** — moat, market share, key competitors
4. **Red flags** — lawsuits, investigations, insider selling, debt concerns
5. **Sources** — URLs with brief relevance notes
6. **Trading relevance** — how findings support or undermine the trade thesis
