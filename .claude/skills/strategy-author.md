## Strategy Author Skill

You are an expert at writing and updating strategy YAML files for the Swing Trader platform.

### Schema Awareness
Strategy files are validated by `schemas/strategy.py::StrategyConfig`. Key sections:
- `name`, `version`, `description`
- `asset_universe`: asset_classes (equity/option/crypto), tickers, filters
- `schedule`: frequency, active_sessions, timezone
- `data_requirements`: list of {source, params} - sources: ohlcv, technicals, news, social, options_flow, web_search
- `entry`: conditions (descriptive strings with priority 1-10), min_conditions_met, position_type
- `exit`: conditions, min_conditions_met
- `risk`: max_position_pct, max_total_exposure_pct, stop_loss_pct, take_profit_pct, max_daily_trades, confidence_threshold
- `notes`: free-form list

### Key Rules
1. Entry/exit conditions are **descriptive strings**, NOT executable code
2. Every data source referenced in conditions MUST have a matching `data_requirements` entry
3. Always include risk parameters with sensible defaults
4. Validate after writing: `from core.strategy_loader import load; load('path/to/file.yaml')`
5. Save to `strategies/examples/` for drafts, `strategies/active/` for production

### Available Technical Indicators
RSI, SMA, EMA, VWAP, MACD, BBANDS (Bollinger Bands), ATR, VOLUME_RATIO

### Example Condition Strings
- "RSI(14) crosses above 30 from oversold territory"
- "Volume is at least 2x the 20-day average"
- "Price breaks above the upper Bollinger Band"
- "MACD histogram turns positive"
- "Put/call ratio drops below 0.7 indicating bullish sentiment"
- "Multiple Reddit posts in r/wallstreetbets mention the ticker with bullish sentiment"
