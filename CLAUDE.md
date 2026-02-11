# Swing Trader

Multi-asset swing trading platform (stocks, options, crypto) powered by PydanticAI + Alpaca.

## Architecture

```
main.py                     # Entry point - loads strategy, runs loop
core/
  agent.py                  # PydanticAI agent with tools
  runner.py                 # Main execution loop (strategy -> data -> agent -> orders)
  routing.py                # Model provider routing
  strategy_loader.py        # YAML -> StrategyConfig parser
  prompt_builder.py         # Strategy + market state -> agent prompt
  market_hours.py           # Market session awareness
schemas/
  strategy.py               # StrategyConfig Pydantic model
  output.py                 # AgentResult, OrderIntent
  market.py                 # MarketSnapshot, TickerSnapshot
  deps.py                   # Deps dataclass (injected into agent)
integrations/
  alpaca/                   # Alpaca SDK wrappers (alpaca-py)
    client.py               # TradingClient factory (paper/live toggle)
    account.py, positions.py, orders.py, assets.py
    market_data.py          # Stock/crypto OHLCV data
    options_data.py         # Options chain, quotes, contracts
  data/                     # Data pipeline
    technicals.py           # pandas-ta indicators (RSI, SMA, VWAP, MACD, etc.)
    news.py                 # Tavily + Alpaca News API
    social.py               # Reddit (PRAW) + StockTwits sentiment
    options_flow.py         # Unusual volume, call/put ratios
  tavily/search.py          # Web search
strategies/
  examples/                 # Example strategy YAML files
  active/                   # Strategies the bot actually runs
  _schema.yaml              # Reference schema (all fields documented)
utils/
  state.py                  # SQLite state persistence (WAL mode, append-only event log)
  logging.py                # Logging configuration
```

## Custom Commands

Run these via `/project:command-name` when working in this project:

| Command | File | Purpose |
|---------|------|---------|
| `/project:strategy-interview` | `.claude/commands/strategy-interview.md` | Interactive strategy design: idea -> questions -> weakness analysis -> YAML generation |
| `/project:strategy-review` | `.claude/commands/strategy-review.md` | Load existing YAML, analyze gaps, risk sanity, data availability |
| `/project:status` | `.claude/commands/status.md` | Dashboard: positions, P&L, strategy status, recent trades |
| `/project:backtest-plan` | `.claude/commands/backtest-plan.md` | Generate a backtest plan for a strategy |

## Skills

Reference docs for specialized tasks (in `.claude/skills/`):

| Skill | File | Purpose |
|-------|------|---------|
| Strategy Author | `.claude/skills/strategy-author.md` | Writes/updates strategy YAML with schema awareness |
| Market Research | `.claude/skills/market-research.md` | Research tickers using available data sources |
| Risk Audit | `.claude/skills/risk-audit.md` | Analyze portfolio risk, flag breaches |

## Rules

Auto-loaded project rules (in `.claude/rules/`):
- `00-project-context.md` - Architecture overview
- `01-strategy-format.md` - Strategy YAML schema reference
- `02-trading-safety.md` - Never trade live without explicit approval

## Key Concepts

### Strategy Files
Strategies are YAML files validated by `schemas/strategy.py::StrategyConfig`. Entry/exit conditions are **descriptive strings** (not executable code). The PydanticAI agent interprets them with judgment using pre-computed market data. See `strategies/_schema.yaml` for the full reference.

### Trading Safety
- `TRADING_MODE=paper` (default) uses Alpaca paper trading
- `TRADING_MODE=live` requires explicit opt-in via env var
- `--allow-trading` flag must be passed to enable order execution
- Confidence threshold (default 0.75) gates trade execution
- All decisions and orders logged to SQLite event store (`state/state.db`)
- **Paper trade every strategy before considering live execution**

### Agent Tools
The PydanticAI agent has tools for: web search, account info, positions, orders, stock/crypto market data, options chains. Tools check `deps.allow_trading` before executing any trade.

## Development

```bash
uv sync                          # Install dependencies
uv run pytest tests/ -v          # Run all 45 tests
uv run python -c "from core.strategy_loader import load; print(load('strategies/examples/sol-momentum.yaml').name)"

# Run with a strategy (paper mode, trading disabled by default)
TRADING_MODE=paper uv run python main.py --strategy strategies/examples/sol-momentum.yaml

# Enable paper trading
TRADING_MODE=paper uv run python main.py --strategy strategies/examples/sol-momentum.yaml --allow-trading
```

## Environment Variables

See `.env.example` for all required variables. Key ones:
- `ALPACA_KEY` / `ALPACA_SECRET` - Alpaca API credentials
- `TRADING_MODE` - `paper` (default) or `live`
- `ANTHROPIC_API_KEY` - For Claude model
- `TAVILY_API_KEY` - For web search
- `REDDIT_CLIENT_ID` / `REDDIT_CLIENT_SECRET` - For social sentiment (optional)
