# Epic status

Update this section in every merged PR.
Walking-slice names match [PR #3](https://github.com/bedw3320/options-trading-bot/pull/3), [PR #5](https://github.com/bedw3320/options-trading-bot/pull/5), and `core/cycle.py`. Long-term Epic 0–7 plan: [`ROADMAP.md`](ROADMAP.md). Walking-slice Epic 5 below is not ROADMAP Epic 5.

| Epic | Status | Definition of done | PR(s) |
|---|---|---|---|
| **0** Paper connectivity | done | IB Gateway paper **4002**; one tiny paper order; fill in SQLite | [#1](https://github.com/bedw3320/options-trading-bot/pull/1), [#3](https://github.com/bedw3320/options-trading-bot/pull/3) |
| **1** Cycle decision lineage | in progress | Every cycle artifact shares a `cycle_id`; structured decision record + `explain` | [#5](https://github.com/bedw3320/options-trading-bot/pull/5), [#15](https://github.com/bedw3320/options-trading-bot/pull/15) |
| **2** Paper readiness / intent gates | done | Identity gate + GuardedBroker preview → token → place | [#3](https://github.com/bedw3320/options-trading-bot/pull/3) |
| **3** Market state + deterministic signals | in progress | Signals from a real snapshot; IB live-data share unblocked | [#4](https://github.com/bedw3320/options-trading-bot/pull/4), [#5](https://github.com/bedw3320/options-trading-bot/pull/5)/[#6](https://github.com/bedw3320/options-trading-bot/pull/6), [#8](https://github.com/bedw3320/options-trading-bot/pull/8)–[#11](https://github.com/bedw3320/options-trading-bot/pull/11) |
| **4** Close-out, exits, reconcile/debrief | in progress | Full paper enter → exit → reconcile → debrief | [#14](https://github.com/bedw3320/options-trading-bot/pull/14) |
| **5** Two-way watchlist RR | next after Epic 4 | Shared watchlist; sell rich skew (puts or calls) only with a written thesis; defined risk; record-only until a human promotes | [#13](https://github.com/bedw3320/options-trading-bot/pull/13) |

**Epic 0 evidence** (2026-10-06): account `DUT116016`. GuardedBroker BUY 1 SPY @ 778.25 (`00025b49.6ac58ef0.01.01`) and SELL 1 SPY @ 778.18 (`00025b49.6ac59033.01.01`). Notes: [`knowledge/ops/2026-10-06-epic0-paper-fill.md`](knowledge/ops/2026-10-06-epic0-paper-fill.md).

**Epic 3 note:** Signals run on CBOE delayed shadow data only ([#8](https://github.com/bedw3320/options-trading-bot/pull/8)–[#11](https://github.com/bedw3320/options-trading-bot/pull/11); strategy `strategies/active/spy-defined-risk-rr.yaml`). IBKR live-data share to paper is blocked until a funded live account (USD 500 equity); then `MARKET_DATA_SOURCE` switches back to `ib`.

**Epic 5 (design only, not built):** Skew vs each name's own trailing history (e.g. top 20% of its 1-year range), not a fixed threshold. Calls count as rich only if borrow cost and short interest are known and under a cap. 10y yield block (e.g. no selling puts if the 10y is up ≥25 bps in 10 days). Event blackouts. Max loss as a % of the account. New names are `record_only` in [`strategies/watchlist.yaml`](strategies/watchlist.yaml) (log signal + what the structure would have paid; no orders) until a sample exists and a human promotes. Separate candidate strategy: wheel / cash-secured puts.

**Watchlist:** optional `falsifier` field added (what would prove the thesis wrong; existing rows stay valid). CRWV Q3 2026 earnings filled (Tue 2026-11-10 after close).

**Epic 1 note:** [#15](https://github.com/bedw3320/options-trading-bot/pull/15): every cycle now writes an append-only decision record (WAL, before any order) keyed by `cycle_id`: strategy YAML + sha256, `gates_v1` catalog, input quotes/IV/OI with live|delayed|fixture + age, every candidate, every gate (no recording short-circuit), binding gate, derived reason. Not acting is a decision — abstain, hold, `proposed_not_sent`, blackout, kill switch, and error all get a full record. Recording is not gated on mode (paper is the primary case). `core.cli explain <cycle_id>` prints outcome, binding gate, 3 closest margins, data-trust, YAML hash, and “no learned weights” ranking. Replay of a stored snapshot must reproduce the stored decision. Exit/hold records share `cycle_id` with Epic 4 debrief (`opened_cycle_id`).

**Epic 4 note:** Harness close-out is in [#14](https://github.com/bedw3320/options-trading-bot/pull/14): each cycle reconciles IBKR paper (DUT116016 / 4002) vs SQLite, marks the open structure, evaluates the YAML exits (21 DTE, underlying stop, −$1,250 / +$1,000) and the $1,500 daily-loss kill switch, and sends a whole-structure close only through GuardedBroker. Dry-run and CBOE-shadow closes stay `proposed_not_sent`. Fills persist exec id / price / qty / `time_utc`. A debrief (entry reason, exit reason, realized P&L, holding period) is keyed by the closing `cycle_id` and linked to the opening cycle. Mini paper demo against DUT116016 is still the remaining evidence.

**Next:** Epic 4 Mini paper close-out against DUT116016, then Epic 5.
