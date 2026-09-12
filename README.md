# Options Trading Bot

A multi-asset swing trading runtime (stocks, options, crypto) that lets you describe strategies in YAML, run them through a PydanticAI agent, and execute on **Interactive Brokers**.

Paper first. Live only when you deliberately arm it.

**Harness law:** [`LOOP.md`](LOOP.md) — first principles and execution boundaries; read before changing anything that can send an order.

**Delivery plan:** [`ROADMAP.md`](ROADMAP.md) — walking paper-trading slices through the options edge platform.

## How it works

You write a strategy as a YAML file:

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

The runner loads the strategy, fetches the data it needs, and hands everything to a PydanticAI agent that decides whether to trade. Entry/exit conditions are natural language — the agent interprets them with judgment, not rigid if/else.

Every decision is logged to SQLite. Orders require `--allow-trading`. Nothing goes live without `TRADING_MODE=live` **and** that flag.

## Quick start

```bash
git clone https://github.com/bedw3320/options-trading-bot.git
cd options-trading-bot
uv sync

cp .env.example .env
# TWS_USERID / TWS_PASSWORD, ANTHROPIC_API_KEY, TRADING_MODE=paper

# Gateway + agent (paper port 4002)
docker compose up

# Or Gateway already running on the Mini:
TRADING_MODE=paper uv run python main.py --strategy strategies/examples/sol-momentum.yaml

uv run pytest tests/ -v

# Paper identity check (no orders). Requires Gateway + IB_ACCOUNT_ID.
uv run python -m core.paper_readiness
```

Without `--allow-trading`, the loop researches and journals. It does not send.

## What’s in the box

**IBKR execution** — `ib_insync` wrappers under `integrations/ibkr/`. Docker image `gnzsnz/ib-gateway` in `docker-compose.yml` (paper **4002**, live **4001**).

**Strategy system** — YAML validated by Pydantic. Conditions are descriptive strings. Schema mistakes fail before they cost money.

**Data pipeline** — Technicals (`pandas-ta`), news (Tavily), social (Reddit + StockTwits), options flow (IBKR chain). Injected from `data_requirements`.

**AI agent** — PydanticAI tools for market data, account, positions. Structured `AgentResult` + `OrderIntent`. Confidence gate (default 0.75). Agent tools cannot place; the runner sends via `GuardedBroker`.

**Risk in code** — Daily trade limit, per-position cap, total exposure cap in `core/runner.py`. Breaches log as `risk_blocked`.

**State** — SQLite WAL. Append-only event log of decisions, orders, risk blocks, errors.

**Cursor / Claude** — `AGENTS.md` + `LOOP.md` for Cursor. Slash commands under `.claude/commands/` for strategy interview/review/status.

## Configuration

Copy `.env.example` to `.env`:

| Variable | Required | Description |
|---|---|---|
| `TWS_USERID` | Yes (compose) | IBKR username for the Gateway container |
| `TWS_PASSWORD` | Yes (compose) | IBKR password for the Gateway container |
| `TRADING_MODE` | No | `paper` (default, port 4002) or `live` (port 4001) |
| `IB_GATEWAY_HOST` | No | Default `ib-gateway` in compose, `127.0.0.1` locally |
| `IB_GATEWAY_PORT` | No | Default 4002 paper / 4001 live |
| `IB_CLIENT_ID` | No | Default `1` |
| `IB_ACCOUNT_ID` | Yes (identity / readiness) | Connected paper account (typically `DU*`) |
| `ANTHROPIC_API_KEY` | Yes (agent) | Model key |
| `TAVILY_API_KEY` | No | Web/news search |
| `REDDIT_CLIENT_ID` / `REDDIT_CLIENT_SECRET` | No | Social sentiment |

## Safety

- **Paper by default** — `TRADING_MODE=paper`
- **Trading disabled by default** — pass `--allow-trading` (or `ALLOW_TRADING=true`) to send
- **Live is dual-gate** — `TRADING_MODE=live` **and** `--allow-trading`
- **Confidence gating** — below strategy threshold → no trade
- **Risk controls in code** — not just in the prompt
- **Market hours** — strategies only run in their configured sessions
- **Everything logged** — agent output, orders, `risk_blocked`
- **Identity gate** — `managedAccounts` must match `IB_ACCOUNT_ID`; live-looking `U*` or port 4001 aborts. See [`knowledge/ops/paper-readiness.md`](knowledge/ops/paper-readiness.md).
- **Guarded placement** — runner preview → single-use token → risk revalidate → place. Agent `create_order` / `close_position` refuse to send.
- **Live is not armed** — remaining Epic 2 items (idempotency, cancel/flatten) and constraint 3 (autonomy latch) are not done. See `LOOP.md`.

## Commands

| Command | What it does |
|---|---|
| `/project:strategy-interview` | Design a strategy conversationally → validated YAML |
| `/project:strategy-review` | Audit an existing strategy |
| `/project:status` | Positions, P&L, recent events |
| `/project:backtest-plan` | Backtest spec for a strategy |

## Stack

| Component | Choice |
|---|---|
| Broker | Interactive Brokers via `ib_insync` + IB Gateway |
| AI agent | PydanticAI |
| Technicals | `pandas-ta` |
| Social | PRAW + StockTwits |
| Strategies | YAML + Pydantic |
| State | SQLite WAL, append-only events |
| Model | Claude (any PydanticAI provider spec) |

## Layout

```
LOOP.md                          # Harness constitution (read first)
AGENTS.md                        # Cursor / agent entry
main.py                          # Entry point
core/                            # Agent, runner, strategy loader
schemas/                         # StrategyConfig, OrderIntent, AgentResult
integrations/ibkr/               # Gateway client, account, orders, market data
integrations/data/               # Technicals, news, social, options flow
strategies/                      # YAML (examples/ + active/)
utils/state.py                   # SQLite event store
docker-compose.yml               # ib-gateway + agent
```

---

*Paper trade everything. Twice. Identity + token handshake are in code. Do not arm live until the autonomy latch exists.*
