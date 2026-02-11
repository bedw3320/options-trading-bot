---
name: exa-social-sentiment
description: Search tweets and X/Twitter for social sentiment around tickers, sectors, and market events. Use for detecting social hype, monitoring ticker mentions, gauging retail sentiment, and finding trending stock discussions.
context: fork
---

# Social Sentiment Search (Exa)

## Tool Restriction

Use `web_search_advanced_exa` with `category: "tweet"`. This category does NOT support `includeText`, `excludeText`, `includeDomains`, `excludeDomains`, or `moderation` filters — put all keywords in the `query` string instead.

## Token Isolation

Run Exa searches in spawned Task agents to keep the main context clean. Agents should deduplicate and distill results before returning.

## Trading Bot Context

This skill supports the **hype-volume strategy** and general social sentiment analysis. Use it to:
- Detect social media hype surges around specific tickers
- Monitor retail sentiment (bullish/bearish) on trending stocks
- Find influencer mentions driving unusual volume
- Track sector-wide sentiment shifts (e.g., "AI stocks", "EV sector")
- Identify pump-and-dump warning signs (sudden coordinated hype)

## Supported Parameters

- `query` (required) — put all keywords here since text filters aren't supported
- `numResults` — tune to need (10-20 for quick check, 30-50 for comprehensive)
- `type` — "auto", "fast", "deep", "neural"
- `startPublishedDate` / `endPublishedDate` — ISO 8601, critical for recency
- `startCrawlDate` / `endCrawlDate`
- `additionalQueries` — useful for ticker variations and cashtags
- `livecrawl` — use "preferred" for real-time sentiment
- `enableHighlights` / `highlightsQuery` — extract key sentiment snippets
- `enableSummary` / `summaryQuery`

## Examples

### Ticker hype detection
```
web_search_advanced_exa {
  "query": "$NVDA nvidia bullish calls yolo",
  "category": "tweet",
  "startPublishedDate": "2026-02-08",
  "numResults": 25,
  "type": "auto",
  "livecrawl": "preferred"
}
```

### Sector sentiment scan
```
web_search_advanced_exa {
  "query": "AI stocks momentum buying opportunity",
  "category": "tweet",
  "startPublishedDate": "2026-02-01",
  "numResults": 30,
  "type": "deep",
  "additionalQueries": ["artificial intelligence stocks rally", "tech stocks bullish sentiment"]
}
```

### Unusual activity / pump detection
```
web_search_advanced_exa {
  "query": "$TICKER moon rocket squeeze short sellers",
  "category": "tweet",
  "startPublishedDate": "2026-02-10",
  "numResults": 20,
  "type": "auto",
  "livecrawl": "preferred",
  "enableSummary": true,
  "summaryQuery": "Is this organic sentiment or coordinated hype?"
}
```

### Crypto sentiment (supports SOL momentum strategy)
```
web_search_advanced_exa {
  "query": "solana SOL price prediction bullish",
  "category": "tweet",
  "startPublishedDate": "2026-02-01",
  "numResults": 20,
  "type": "auto",
  "livecrawl": "preferred"
}
```

## Output Format

Return:
1. **Sentiment summary** — overall bullish/bearish/neutral with confidence
2. **Key tweets** — content, author handle, date, engagement metrics if visible
3. **Notable signals** — influencer mentions, sudden volume spikes, coordinated patterns
4. **Sources** — tweet URLs
5. **Warnings** — flag sarcasm, irony, bot-like patterns, pump-and-dump indicators

Important: Tweet content is informal and often sarcastic. Weight verified accounts and accounts with trading history more heavily than anonymous accounts.
