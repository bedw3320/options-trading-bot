# Options Trading Bot

Multi-asset swing trading platform (stocks, options, crypto) powered by PydanticAI + Interactive Brokers.

**Read `LOOP.md` first.** That file is first principles and harness law (planes, four constraints, current vs target). This file is the working map.

Standalone runtime. No sibling personal repos. No shared secrets.

## Architecture

```
main.py                     # Entry point - loads strategy, runs loop
core/
  agent.py                  # PydanticAI agent with tools (place tools refuse)
  runner.py                 # Main execution loop (strategy -> data -> agent -> orders)
  identity.py               # Paper account identity gate
  guarded_broker.py         # preview → token → revalidate → place
  paper_readiness.py        # Mini paper Gateway check (no orders)
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
  ibkr/                     # Interactive Brokers wrappers (ib_insync)
    client.py               # IB Gateway connection factory (paper/live toggle)
    account.py, positions.py, orders.py, assets.py
    market_data.py          # Stock/crypto OHLCV data
    options_data.py         # Options chain, contracts
  data/                     # Data pipeline
    technicals.py           # pandas-ta indicators (RSI, SMA, VWAP, MACD, etc.)
    news.py                 # Tavily
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
| `/project:expert-interview` | `.claude/commands/expert-interview.md` | Interview domain expert: extract strategy knowledge, validate against vault, produce YAML + vault notes |
| `/project:strategy-interview` | `.claude/commands/strategy-interview.md` | Interactive strategy design: idea -> questions -> weakness analysis -> YAML generation |
| `/project:strategy-review` | `.claude/commands/strategy-review.md` | Load existing YAML, analyze gaps, risk sanity, data availability |
| `/project:status` | `.claude/commands/status.md` | Dashboard: positions, P&L, strategy status, recent trades |
| `/project:backtest-plan` | `.claude/commands/backtest-plan.md` | Generate a backtest plan for a strategy |
| `/project:reduce` | `.claude/commands/reduce.md` | Extract atomic claims from source material into knowledge vault |
| `/project:reflect` | `.claude/commands/reflect.md` | Find connections between notes, update topic maps |
| `/project:verify` | `.claude/commands/verify.md` | Quality check: description, schema, link health |
| `/project:reweave` | `.claude/commands/reweave.md` | Backward pass: update older notes with new context |
| `/project:seed` | `.claude/commands/seed.md` | Register source document in processing queue |
| `/project:pipeline` | `.claude/commands/pipeline.md` | End-to-end: seed → reduce → reflect → verify |
| `/project:vault-stats` | `.claude/commands/vault-stats.md` | Knowledge vault metrics and health indicators |
| `/project:vault-health` | `.claude/commands/vault-health.md` | Comprehensive vault health check |

## Skills

Reference docs for specialized tasks (in `.claude/skills/`):

| Skill | File | Purpose |
|-------|------|---------|
| Strategy Author | `.claude/skills/strategy-author.md` | Writes/updates strategy YAML with schema awareness |
| Market Research | `.claude/skills/market-research.md` | Research tickers using available data sources |
| Risk Audit | `.claude/skills/risk-audit.md` | Analyze portfolio risk, flag breaches |
| Social Sentiment (Exa) | `.claude/skills/exa-social-sentiment.md` | X/Twitter sentiment for hype detection, ticker buzz, retail sentiment |
| Financial Reports (Exa) | `.claude/skills/exa-financial-reports.md` | SEC filings, earnings reports, fundamental analysis |
| Company Research (Exa) | `.claude/skills/exa-company-research.md` | Ticker due diligence, news catalysts, competitive analysis |

## Rules

Auto-loaded project rules (in `.claude/rules/`):
- `00-project-context.md` - Architecture overview
- `01-strategy-format.md` - Strategy YAML schema reference
- `02-trading-safety.md` - Never trade live without explicit approval
- `LOOP.md` (repo root) - Harness constitution — wins over the rules above on execution questions

## Key Concepts

### Strategy Files
Strategies are YAML files validated by `schemas/strategy.py::StrategyConfig`. Entry/exit conditions are **descriptive strings** (not executable code). The PydanticAI agent interprets them with judgment using pre-computed market data. See `strategies/_schema.yaml` for the full reference.

### Trading Safety
- `TRADING_MODE=paper` (default) uses IB Gateway paper (port **4002**)
- `TRADING_MODE=live` uses port **4001** and requires explicit opt-in
- `--allow-trading` must be passed to enable order execution
- Confidence threshold (default 0.75) gates trade execution
- All decisions and orders logged to SQLite (`state/state.db`)
- **Paper trade every strategy before considering live.** Constraints 1–2 exist (`core/identity.py`, `core/guarded_broker.py`). Do not arm live until constraint 3 (autonomy latch) exists.
- Agent `create_order` / `close_position` refuse to place. Runner-only send via `GuardedBroker`. Do not add one-hop paths.
- Paper identity check: `uv run python -m core.paper_readiness`

### Agent Tools
The PydanticAI agent has tools for: web search, account info, positions, stock/crypto market data, options chains. Place/close tools refuse; the runner places via `GuardedBroker`. Broker I/O is `integrations/ibkr/` only.

## Development

```bash
uv sync                          # Install dependencies
uv run pytest tests/ -v          # Run tests
uv run python -c "from core.strategy_loader import load; print(load('strategies/examples/sol-momentum.yaml').name)"

# Run with a strategy (paper mode, trading disabled by default)
TRADING_MODE=paper uv run python main.py --strategy strategies/examples/sol-momentum.yaml

# Enable paper trading
TRADING_MODE=paper uv run python main.py --strategy strategies/examples/sol-momentum.yaml --allow-trading
```

## Environment Variables

See `.env.example` for all required variables. Key ones:
- `TWS_USERID` / `TWS_PASSWORD` - Interactive Brokers credentials
- `IB_GATEWAY_HOST` / `IB_GATEWAY_PORT` - IB Gateway connection (defaults: `ib-gateway` / `4002`)
- `TRADING_MODE` - `paper` (default) or `live`
- `ANTHROPIC_API_KEY` - For Claude model
- `TAVILY_API_KEY` - For web search
- `REDDIT_CLIENT_ID` / `REDDIT_CLIENT_SECRET` - For social sentiment (optional)
