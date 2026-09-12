## Trading Safety Rules

See `LOOP.md` for first principles and the four harness constraints. This file is the operational checklist.

### NEVER
- Never execute live trades without the user explicitly setting `TRADING_MODE=live` AND `--allow-trading`
- Never arm live until constraint 3 (autonomy latch) exists. Constraints 1–2 are in code (`core/identity.py`, `core/guarded_broker.py`).
- Never add a new path that lets the LLM call `ib_insync` or place an order in one hop
- Never bypass the confidence threshold
- Never place orders larger than `risk.max_position_pct` of portfolio
- Never modify `TRADING_MODE` or `ALLOW_TRADING` without explicit user instruction
- Never delete the state database or event log
- Never copy secrets from, or write trading state into, any other personal repo

### ALWAYS
- Always default to paper trading (`TRADING_MODE=paper`, Gateway port 4002)
- Always log every agent decision and order to the SQLite event store
- Always respect `risk.max_daily_trades` limit
- Always show the user what trades will be placed before enabling trading
- Always commit strategy changes to git for auditability
- Always validate strategy YAML files against the Pydantic schema

### Paper Trading First
Every new strategy must be paper traded before live execution. The flow is:
1. Design strategy via `/strategy-interview`
2. Review via `/strategy-review`
3. Paper trade for observation period
4. Analyze results via `/status`
5. Only then consider live trading (with user approval at every step) — and only after constraint 3 (autonomy latch) ships. Identity + token handshake already exist.
