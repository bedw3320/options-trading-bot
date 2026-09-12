## Project Context

This is **Options Trading Bot**, a multi-asset swing trading platform (stocks, options, crypto) powered by PydanticAI and Interactive Brokers.

Harness law: `LOOP.md`. Isolation: this repo only — no sibling personal projects.

### Architecture
- **Strategies**: YAML files validated by Pydantic models. Conditions are descriptive strings, not code.
- **Runner**: Loads strategy -> fetches data -> builds prompt -> runs PydanticAI agent -> (gated) executes orders
- **Agent**: PydanticAI agent with tools for market data, orders, news, social, options
- **Broker**: `ib_insync` via IB Gateway (`integrations/ibkr/`)
- **State**: SQLite with WAL mode, append-only event log
- **Data**: pandas-ta technicals, Tavily news, Reddit/StockTwits social, options flow

### Key Files
- `LOOP.md` - Loop constitution (read first)
- `main.py` - Entry point
- `core/runner.py` - Main loop
- `core/agent.py` - PydanticAI agent with tools
- `schemas/strategy.py` - StrategyConfig model
- `schemas/output.py` - `OrderIntent` / `TradeIntent` / `AgentResult`
- `core/identity.py` - paper account identity gate
- `core/guarded_broker.py` - preview → token → place
- `core/strategy_loader.py` - YAML parser
- `core/prompt_builder.py` - Strategy -> prompt
- `integrations/ibkr/` - IB Gateway client, account, orders, market data, options
- `integrations/data/` - Data pipeline modules
- `docker-compose.yml` - `ib-gateway` + `agent`

### Testing
Run: `uv run pytest tests/ -v`
All modules should have tests. Use `TestModel()` for PydanticAI agent tests.
