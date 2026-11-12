# Exit strategy — deferred (locked 2026-11-11, America/Toronto)

Locked with Will. Product intent for closes, assignment, and paper-reset
durability. Assignment/sub-routines are **not** in the v0 open path.

Walking-slice **Epic 6** in [`STATUS.md`](../../STATUS.md). That row is not
ROADMAP Epic 6 (multi-agent desk).

The in-force open path is `strategies/active/us-large-cap-rr.yaml` (standard
risk reversal). `strategies/active/spy-defined-risk-rr.yaml` is superseded /
historical and is not loaded by the runner.

## In force now

- Structure: standard risk reversal — **short put + long call**. No
  protective put. No defined max loss. Same expiry, 30–45 DTE, 25-delta short
  put and 25-delta long call, 1 lot.
- Binding entry signal: **rr25 ≤ −0.05** (25d call IV minus 25d put IV).
- Risk cap for the testing period: paper account **DUT116016** equity and
  margin. That account is the bound. No $1,500 daily-loss kill.
- **No automated exits.** None of: 21-DTE time stop, underlying-price stop,
  dollar stop, take-profit.
- Closes are **manual flatten only** (`core.cli flatten`, still through
  GuardedBroker, paper identity, `--allow-trading` to send) or hold to expiry.
- Assignment and other sub-routines are designed later **in this epic**. They
  do not block opening.
- Paper auto-send is still gated: live IBKR quotes on the paper account, and
  one paper fill already reconciled into SQLite. Delayed data hard-shadows.

## Three core scenarios

1. **Bullish.** The stock goes up. The long call pays. The short put expires
   worthless.
2. **Flat.** The stock stays between the strikes through expiry. Both legs
   expire worthless. We keep the net credit from opening the trade.
3. **Bearish.** The short put is assigned and we hold the shares. A later
   sub-process in this epic will manage that outcome. Out of scope until then.

## Deferred (this epic; not the v0 open path)

- Time stop, underlying stop, dollar stop, take-profit (the yellow zone).
- Assignment handling and any other close/hold sub-routines.

## Historical YAML (do not load)

`strategies/active/spy-defined-risk-rr.yaml` still encodes the old defined-risk
`evaluate_exit` order. Treat it as lineage of past cycles, not product-in-force:

1. 21-DTE hard close
2. Underlying stop: short put − 3%, floored at long put + 25% of the wing
3. −$1,250 stop
4. +$1,000 take profit

The runner refuses to execute that engine.

As-built cycle behavior is described in
[`deterministic-cycle.md`](deterministic-cycle.md).

## Decision-database durability (non-negotiable)

The local decision/trade database (`state/state.db`) is the gold mine
(LOOP principle 10). It must stay intact at all times, including after a
paper-account reset.

**Never wipe:** `cycles`, `decision_v1` / `decision_records`, `fills`,
debriefs (`trade_debriefs`), or related lineage (`cycle_artifacts`, `orders`,
closed `strategy_positions`, `agent_events`). History stays queryable.

After an IBKR flatten **and** a Client Portal paper equity reset:

1. Record a **reset event** (append-only; do not rewrite history).
   `core.cli paper-reset-snapshot --confirm yes` does this.
2. Clear **only** the live open-position snapshot (`strategy_positions` rows
   with `status=open`, every strategy name for that mode) so `core/reconcile.py`
   does not see expected option legs that the broker no longer has and latch
   the kill switch (`latch_on_reconcile_drift`). Closed rows and decision
   lineage stay.
3. Do not rearm live. Paper remains the default.
4. There is no tool that wipes the DB.

## Paper reset facts (ops)

IBKR paper reset does **not** close positions. Flatten first.

- Log into Client Portal with the **paper** username and password. Do not use
  live credentials.
- Paper Trading Account Reset: submit by **16:00 ET**. It takes effect the
  **next trading day**. Later submissions slip a business day.
- Official start equity is **USD 1,000,000**. Reset equity is capped at
  **five times** the live account's value.
- Mask any live account id as `U****8141`. Never copy TWS secrets or `.env`
  values into git, issues, or this file.

## Non-goals of Epic 6 (still)

- No assignment handler.
- Do not compact the Mini decision DB from this path.
