## Strategy YAML Format

Strategy files must conform to `schemas/strategy.py::StrategyConfig`.

### Critical Rules
1. Entry/exit conditions are **descriptive strings** - never write executable code in YAML conditions
2. Every data source referenced in conditions MUST have a matching `data_requirements` entry
3. Always validate after writing: `from core.strategy_loader import load; load('path')`
4. Save drafts to `strategies/examples/`, production to `strategies/active/`

### Available Data Sources
- `ohlcv` - Price bars (timeframe, bars count)
- `technicals` - Indicators: RSI, SMA, EMA, VWAP, MACD, BBANDS, ATR, VOLUME_RATIO
- `news` - Tavily + Alpaca News (keywords, max_age_hours)
- `social` - Reddit + StockTwits (subreddits, keywords)
- `options_flow` - Chain analysis (min_volume_ratio)
- `web_search` - General web (queries)

### Condition Priority Scale
- 10: Must-have (stop loss, hard limits)
- 7-9: Primary signals
- 4-6: Secondary/confirming signals
- 1-3: Nice-to-have context
