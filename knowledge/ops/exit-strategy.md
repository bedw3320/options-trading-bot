# Exit strategy — deferred (locked 2026-11-11, America/Toronto)

Locked with Will. Product intent for closes, assignment, and paper-reset
durability. **Not implemented here.** The v0 open path must not wait on this
epic. The new core-strategy YAML (standard risk reversal, no protective put)
is a later change; this document does not rewrite
`strategies/active/spy-defined-risk-rr.yaml`.

Walking-slice **Epic 6** in [`STATUS.md`](../../STATUS.md). That row is not
ROADMAP Epic 6 (multi-agent desk).

## In force now

- Structure target: standard risk reversal — **short put + long call**. No
  protective put. No defined max loss.
- Risk cap for the testing period: paper account **DUT116016** equity and
  margin. That account is the bound.
- **No automated exits.** None of: 21-DTE time stop, underlying-price stop,
  dollar stop, take-profit.
- Closes are **manual flatten only** (`core.cli flatten`, still through
  GuardedBroker, paper identity, `--allow-trading` to send).
- Assignment and other sub-routines are designed later **in this epic**. They
  do not block opening.

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
- A paper-reset tool or CLI. Record the rules below; do not implement them in
  the epic-registration PR.

## Superseded as-built (do not delete in this PR)

Code and `strategies/active/spy-defined-risk-rr.yaml` still evaluate this
`evaluate_exit` order (`core/rr_rules.py`). Treat it as superseded intent,
not product-in-force:

1. 21-DTE hard close
2. Underlying stop: short put − 3%, floored at long put + 25% of the wing
3. −$1,250 stop
4. +$1,000 take profit

Daily −$1,500 latches the kill switch and blocks new entries; it does **not**
exit. That yellow zone is deferred into this epic. Leave the YAML exits in
place until a later PR changes the core strategy.

As-built cycle behavior is still described in
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
2. Clear **only** the live open-position snapshot (`strategy_positions` rows
   with `status=open`) so `core/reconcile.py` does not see expected option
   legs that the broker no longer has and latch the kill switch
   (`latch_on_reconcile_drift`).
3. Do not rearm live. Paper remains the default.

## Paper reset facts (ops; no tool in this PR)

IBKR paper reset does **not** close positions. Flatten first.

- Log into Client Portal with the **paper** username and password. Do not use
  live credentials.
- Paper Trading Account Reset: submit by **16:00 ET**. It takes effect the
  **next trading day**. Later submissions slip a business day.
- Official start equity is **USD 1,000,000**. Reset equity is capped at
  **five times** the live account's value.
- Mask any live account id as `U****8141`. Never copy TWS secrets or `.env`
  values into git, issues, or this file.

## Non-goals of the registration PR

- No exit-logic changes, no `evaluate_exit` edits, no strategy YAML rewrite.
- No paper-reset tool, no snapshot-clear command, no assignment handler.
