## Project Context

This is **Swing Trader**, a multi-asset swing trading platform (stocks, options, crypto) powered by PydanticAI and Alpaca.

### Architecture
- **Strategies**: YAML files validated by Pydantic models. Conditions are descriptive strings, not code.
- **Runner**: Loads strategy -> fetches data -> builds prompt -> runs PydanticAI agent -> executes orders
- **Agent**: PydanticAI agent with tools for market data, orders, news, social, options
- **State**: SQLite with WAL mode, append-only event log
- **Data**: pandas-ta technicals, Tavily/Alpaca news, Reddit/StockTwits social, options flow

### Key Files
- `main.py` - Entry point
- `core/runner.py` - Main loop
- `core/agent.py` - PydanticAI agent with tools
- `schemas/strategy.py` - StrategyConfig model
- `core/strategy_loader.py` - YAML parser
- `core/prompt_builder.py` - Strategy -> prompt
- `integrations/alpaca/` - Alpaca SDK wrappers
- `integrations/data/` - Data pipeline modules

### Testing
Run: `uv run pytest tests/ -v`
All modules should have tests. Use `TestModel()` for PydanticAI agent tests.
