# Deterministic cycle v0 — in-force standard RR

**Product-in-force (locked 2026-11-11):** standard risk reversal (short put + long call),
no protective put, no defined max loss, **no automated exits**. Closes are
**manual flatten only**. Paper DUT116016 equity/margin is the testing-period
risk cap. See [`exit-strategy.md`](exit-strategy.md) and
[`STATUS.md`](../../STATUS.md) walking-slice Epic 6.

Strategy file: `strategies/active/us-large-cap-rr.yaml` (the `rules:` block
executes; no LLM in the decision path).
`strategies/active/spy-defined-risk-rr.yaml` is superseded/historical; the
runner refuses that engine.
Code: `core/cycle.py` (orchestration), `core/signals.py`, `core/rr_rules.py`,
`core/market_state.py`, `core/brokers.py`, `core/reconcile.py`,
`core/entry_window.py`, `core/send_gate.py`, `core/universe.py`,
`utils/lineage.py`, `integrations/ibkr/combo.py`, CLI `core.cli`.

The runner does **not** load `strategies/watchlist.yaml`.

## One cycle (run once, then stop)

1. Start `cycle_id`, record inputs (strategy path + sha256, version, git sha, mode, rules).
2. Kill switch state is read (it blocks new entries only; flatten still runs).
3. Paper mode: identity gate (`assert_paper_identity`, account must be `DU*`, `TRADING_MODE=paper`, port **4002** not 4001); failure latches the kill switch. RTH only.
4. Reconcile **all** IB option positions / working orders vs SQLite. Drift → latch + abstain.
5. Market snapshot per name (IB, CBOE delayed, Alpaca, or fixture). Any data failure → skip that name. If a held name is unavailable, abstain. Never guesses.
6. Open positions: mark-to-market; `evaluate_exit` always holds. `flatten` is the only close. No 21-DTE / underlying / dollar / take-profit stops.
7. Entry window uses **America/Toronto wall clock**, never a quote `as_of`. Slots: 10:00 and 15:00, 10-minute grace, weekdays.
8. Universe: S&P 500 (`data/sp500.txt`) plus the 25d put/call liquidity screen. Rank names that clear **rr25 ≤ −0.05** by richest rr25. Open up to **5 per run** and **10 per day**. Never a second risk reversal on a name that already has an open position. No outstanding position-count cap.
9. Intent → send gate (delayed data and paper bootstrap) → `GuardedBroker.preview_combo` → token → revalidate → BAG limit at mid, DAY.
   Paper auto-send requires (1) live IBKR quotes on the paper account, not CBOE delayed / Alpaca indicative / IB delayed, and (2) one paper fill already in SQLite. Until then the cycle ends `proposed_not_sent` (journal only). After those two, paper sends need no per-ticket human approval — still never live.
   Revalidate: opens need kill not latched and no open RR on that name; closes must exactly offset an open strategy position.
10. Wait `fill_wait_seconds` (30); unfilled → cancel. Record fills, open/close the position row, reconcile again.

Outcomes: `entered`, `exited`, `held`, `abstained`, `proposed_not_sent`, `error`. 3 consecutive `error`s latch the kill switch.

Every cycle writes a decision record before any order, including abstain / hold / proposed_not_sent / blackout / kill / error.

## Kill switch

Latched by: identity failure, reconcile drift (pre or post trade), 3 consecutive error cycles, or `kill`.
**Not** latched by daily realized loss. Stays latched until `rearm`. While latched:

- **New entries are blocked** (cycle check + GuardedBroker revalidate).
- **Flatten still runs** (product-in-force close). Same path as any order: paper identity, pre-trade reconcile, preview → token → revalidate, `--allow-trading` to send, still subject to the delayed/live-IB send gate.
- The cycle record shows it: a `kill_switch` artifact `{"action": "exit_allowed_while_latched", "trigger": "manual_flatten", ...}`.
- Not allowed even for exits: a live/non-`DU` account (identity error, nothing sent) and reconcile drift.

## SQLite (state/state.db, gitignored)

`cycles`, `cycle_artifacts` (kind = inputs | reconcile | market_snapshot | universe_scan | signals | decision | intent | order | fill | error | kill_switch | paper_reset | …),
`strategy_positions`, `orders` (idempotency_key = `<cycle_id>:open:<ticker>` or `:close:<position_id>`), `fills` (unique exec_id), `kill_switch`.
Dry-run and paper rows are separated by `mode`.
Never wipe decision lineage across a paper-account reset — [`exit-strategy.md`](exit-strategy.md).
`core.cli paper-reset-snapshot --confirm yes` records a reset event and clears **open** snapshot rows only.

## Commands (Mini, repo root)

    uv run python -m core.cli run --dry-run                    # fixtures + SimBroker; no IB connection
    uv run python -m core.cli run --dry-run --fixture tests/fixtures/spy_snapshot_unavailable.json
    uv run python -m core.cli explain last                     # why it traded / abstained
    uv run python -m core.cli list
    TRADING_MODE=paper IB_GATEWAY_HOST=127.0.0.1 IB_GATEWAY_PORT=4002 uv run python -m core.cli run                  # paper, journal only
    TRADING_MODE=paper IB_GATEWAY_HOST=127.0.0.1 IB_GATEWAY_PORT=4002 uv run python -m core.cli run --allow-trading  # paper, sends only if live IB + first fill
    uv run python -m core.cli reconcile                        # paper IB vs SQLite, no orders
    uv run python -m core.cli kill --reason "..."  /  rearm    # add --mode dry_run for dry-run rows
    TRADING_MODE=paper IB_GATEWAY_HOST=127.0.0.1 IB_GATEWAY_PORT=4002 uv run python -m core.cli flatten --allow-trading  # product-in-force close
    uv run python -m core.cli flatten --dry-run                # same on fixtures + SimBroker
    uv run python -m core.cli paper-reset-snapshot --confirm yes  # open snapshot only; never wipes history

Paper cycles use clientId 11 (`IB_CYCLE_CLIENT_ID` overrides), readonly unless `--allow-trading`.
A file lock (`state/cycle.lock`) prevents overlapping cycles.

## Known limits (v0)

- Needs IB option quotes + model Greeks + open interest. Until live IB data is on the paper account, paper cycles do not send (`proposed_not_sent` / delayed shadow).
- Open interest arrives on generic tick 101 and may lag; a missing OI fails the liquidity check (skip that name, by design).
- Fixtures are SYNTHETIC (Black-Scholes + skew curve, `tests/fixtures/make_spy_fixtures.py`), not market data. Dry-run on the SPY fixture still works because the fixture provider lists only SPY (SPY is not in `data/sp500.txt`).
- rr25 percentile is informational (`skew_percentile_required: false`).
- 25-delta IVs for rr25 are interpolated in |delta| between the bracketing strikes (nearest strike if a side cannot be bracketed).
- Mini `com.otb.cycle` launchd fires weekdays at **10:00 and 15:00** America/Toronto; `cycle.sh` double-gates those slots. Record-only (`ALLOW_TRADING=false`). Not an auto-close policy.
- Live is not armed and the schema cannot express it (`paper_only: true`, `required_account_prefix: DU`).
- Epic 4 Mini paper flatten/reconcile/debrief evidence on DUT116016 may still be outstanding.
