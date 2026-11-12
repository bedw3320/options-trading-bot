## Risk Audit Skill

You analyze portfolio risk against strategy parameters and flag potential breaches.

Product-in-force (locked 2026-11-11): no defined max loss, no automated yellow-zone
exits; paper DUT116016 equity/margin is the testing-period cap; closes are manual
flatten. See `knowledge/ops/exit-strategy.md`. YAML `evaluate_exit` numbers are
as-built / superseded.

### What to Check

1. **Position Sizing**
   - Is any position > `risk.max_position_pct` of portfolio?
   - Is total exposure > `risk.max_total_exposure_pct`?
   - Are there concentration risks (too much in one sector/asset)?

2. **Stop Loss Compliance**
   - Do open positions have losses exceeding `risk.stop_loss_pct`?
   - Are there positions without a defined exit strategy?

3. **Trade Frequency**
   - Has `risk.max_daily_trades` been exceeded today?
   - Is the trading frequency sustainable for the strategy type?

4. **Correlation Risk**
   - Are multiple positions highly correlated?
   - Is the portfolio diversified across asset classes?

5. **Drawdown Analysis**
   - Current drawdown from peak portfolio value
   - Consecutive losing trades

### Data Sources
- Portfolio positions: `utils/state.py::load_state(db_path, state_key)`
- Strategy parameters: Load from `strategies/active/` YAML files
- Account info: `integrations/ibkr/account.py::get_account()`

### Output Format
```
=== Risk Audit ===
Strategy: [name]
Date: [current]

BREACHES (action required):
- [critical issues]

WARNINGS:
- [potential issues]

METRICS:
- Total exposure: X% (limit: Y%)
- Largest position: SYMBOL at X% (limit: Y%)
- Daily trades: X (limit: Y)
- Max drawdown: X%
- Consecutive losses: X

RECOMMENDATIONS:
- [specific actions]
```
