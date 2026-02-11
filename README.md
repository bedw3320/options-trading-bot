# Alpaca Trading Bot

A multi-asset swing trading platform that lets you describe trading strategies in plain English, poke holes in them, and then execute them — all through an AI agent with real market tools.

Stocks. Options. Crypto. Paper trade first, go live when you're ready.

## How It Works

You write a strategy as a simple YAML file:

```yaml
name: hype-volume-options
description: Detect social media hype driving unusual options volume, ride the momentum

entry:
  conditions:
    - description: "Social media mentions surging with bullish sentiment"
      priority: 8
    - description: "Call option volume is 2x+ the 20-day average"
      priority: 9
    - description: "RSI(14) between 40-70 — room to run, not overbought"
      priority: 5
  min_conditions_met: 2
```

The bot reads the strategy, fetches the data it needs, and hands everything to a PydanticAI agent that decides whether to trade. Entry/exit conditions are natural language — the AI interprets them with judgment, not rigid if/else logic.

Every decision gets logged. Every order gets tracked. Nothing goes live without your say-so.

## Quick Start

```bash
# Clone and install
git clone https://github.com/bedw3320/alpaca-trading-bot.git
cd alpaca-trading-bot
uv sync

# Set up your keys
cp .env.example .env
# Edit .env with your API keys (Alpaca, Anthropic, etc.)

# Run with an example strategy (paper mode, no live trades)
uv run python main.py --strategy strategies/examples/sol-momentum.yaml

# Run tests
uv run pytest tests/ -v
```

## What's In The Box

**Strategy System** — YAML files validated by Pydantic. Write conditions in plain English, reference any data source, set your risk params. The schema catches mistakes before they cost you money.

**Multi-Asset Trading** — Stocks, options, and crypto through the Alpaca SDK (`alpaca-py`). Paper/live toggle via a single env var.

**Data Pipeline** — Technical indicators (RSI, MACD, Bollinger Bands, 130+ via `pandas-ta`), news aggregation (Tavily + Alpaca News), social sentiment (Reddit + StockTwits), and options flow analysis.

**AI Agent** — PydanticAI agent with tools for market data, account management, order execution, and web search. Structured outputs with confidence scoring — won't trade unless it's confident enough.

**State Management** — SQLite with WAL mode. Append-only event log of every decision, order, and reconciliation. Fully auditable.

**Claude Code Integration** — Custom commands for strategy design, review, and monitoring. Open the project in Claude Code and run `/project:strategy-interview` to design a strategy conversationally.

## Strategies

Strategies live in `strategies/` as YAML files:

```
strategies/
  examples/
    sol-momentum.yaml          # News-driven crypto (ported from original bot)
    hype-volume-options.yaml   # Social hype -> options flow -> momentum
  active/                      # Drop strategies here to run them
  _schema.yaml                 # Full reference of all fields
```

A strategy defines: what to trade, when to check, what data to fetch, when to enter/exit, and how much risk to take. See `_schema.yaml` for every available field.

**Key design decision**: Conditions are descriptive strings, not code. The AI agent interprets "RSI(14) crosses above 30 from oversold territory" using pre-computed indicator data and its own judgment. This keeps strategies readable, auditable, and git-diffable.

## Configuration

Copy `.env.example` to `.env` and fill in your keys:

| Variable | Required | Description |
|----------|----------|-------------|
| `ALPACA_KEY` | Yes | Alpaca API key |
| `ALPACA_SECRET` | Yes | Alpaca API secret |
| `ANTHROPIC_API_KEY` | Yes | For the AI agent |
| `TRADING_MODE` | No | `paper` (default) or `live` |
| `TAVILY_API_KEY` | No | Web search for news |
| `REDDIT_CLIENT_ID` | No | Social sentiment |
| `REDDIT_CLIENT_SECRET` | No | Social sentiment |

## Safety

This bot defaults to doing nothing dangerous:

- **Paper trading by default** — `TRADING_MODE=paper` unless you explicitly change it
- **Trading disabled by default** — pass `--allow-trading` to enable order execution
- **Confidence gating** — the agent won't trade below the strategy's confidence threshold (default 0.75)
- **Everything is logged** — every agent decision and order goes to the SQLite event store
- **Strategies are code** — YAML files in git, fully diffable and reviewable

## Claude Code Commands

If you use [Claude Code](https://docs.anthropic.com/en/docs/claude-code), this project comes with custom slash commands:

| Command | What it does |
|---------|-------------|
| `/project:strategy-interview` | Walk through designing a new strategy — captures your idea, asks probing questions, finds weaknesses, generates validated YAML |
| `/project:strategy-review` | Audit an existing strategy for logical gaps and risk issues |
| `/project:status` | Dashboard showing positions, P&L, and recent trades |
| `/project:backtest-plan` | Generate a backtest specification for a strategy |

## Tech Stack

| Component | Choice | Why |
|-----------|--------|-----|
| Trading | `alpaca-py` | Official SDK, typed, multi-asset |
| AI Agent | PydanticAI | Structured outputs, tool system, dependency injection |
| Technicals | `pandas-ta` | Pure Python, 130+ indicators, no C deps |
| Social | PRAW + StockTwits | Free APIs for Reddit + stock sentiment |
| Strategies | YAML + Pydantic | Human-readable, machine-parseable, git-diffable |
| State | SQLite | WAL mode, append-only event log |
| Model | Claude (configurable) | Any PydanticAI-compatible provider works |

## Project Structure

```
main.py                          # Entry point
core/
  agent.py                       # PydanticAI agent + all tools
  runner.py                      # Strategy evaluation loop
  strategy_loader.py             # YAML -> validated StrategyConfig
  prompt_builder.py              # Strategy + market data -> agent prompt
  market_hours.py                # Knows when markets are open
schemas/
  strategy.py                    # StrategyConfig Pydantic model
  output.py                      # AgentResult, OrderIntent
  market.py                      # MarketSnapshot, TickerSnapshot
integrations/
  alpaca/                        # SDK wrappers (account, orders, positions, market data, options)
  data/                          # Technicals, news, social sentiment, options flow
strategies/                      # Your trading strategies (YAML)
```

## Contributing

Fork it, break it, make it better. PRs welcome.

This started as a minimal SOL crypto bot and grew into a multi-asset platform. The framework is designed to support any strategy — the ones included are just examples to get you started.

---

*Paper trade everything. Twice. Then maybe consider going live.*
