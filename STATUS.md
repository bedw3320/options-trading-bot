# Epic status

Update this section in every merged PR.
Walking-slice names match [PR #3](https://github.com/bedw3320/options-trading-bot/pull/3), [PR #5](https://github.com/bedw3320/options-trading-bot/pull/5), and `core/cycle.py`. Long-term Epic 0–7 plan: [`ROADMAP.md`](ROADMAP.md). Walking-slice Epic 5 below is not ROADMAP Epic 5.

| Epic | Status | Definition of done | PR(s) |
|---|---|---|---|
| **0** Paper connectivity | done | IB Gateway paper **4002**; one tiny paper order; fill in SQLite | [#1](https://github.com/bedw3320/options-trading-bot/pull/1), [#3](https://github.com/bedw3320/options-trading-bot/pull/3) |
| **1** Cycle decision lineage | in progress | Every cycle artifact shares a `cycle_id` (`utils/lineage.py`) | [#5](https://github.com/bedw3320/options-trading-bot/pull/5) |
| **2** Paper readiness / intent gates | done | Identity gate + GuardedBroker preview → token → place | [#3](https://github.com/bedw3320/options-trading-bot/pull/3) |
| **3** Market state + deterministic signals | in progress | Signals from a real snapshot; IB live-data share unblocked | [#4](https://github.com/bedw3320/options-trading-bot/pull/4), [#5](https://github.com/bedw3320/options-trading-bot/pull/5)/[#6](https://github.com/bedw3320/options-trading-bot/pull/6), [#8](https://github.com/bedw3320/options-trading-bot/pull/8)–[#11](https://github.com/bedw3320/options-trading-bot/pull/11) |
| **4** Close-out, exits, reconcile/debrief | next | Full paper enter → exit → reconcile → debrief | — |
| **5** Two-way watchlist RR | next after Epic 4 | Shared watchlist; sell rich skew (puts or calls) only with a written thesis; defined risk; record-only until a human promotes | — |

**Epic 0 evidence** (2026-10-06): account `DUT116016`. GuardedBroker BUY 1 SPY @ 778.25 (`00025b49.6ac58ef0.01.01`) and SELL 1 SPY @ 778.18 (`00025b49.6ac59033.01.01`). Notes: [`knowledge/ops/2026-10-06-epic0-paper-fill.md`](knowledge/ops/2026-10-06-epic0-paper-fill.md).

**Epic 3 note:** Signals run on CBOE delayed shadow data only ([#8](https://github.com/bedw3320/options-trading-bot/pull/8)–[#11](https://github.com/bedw3320/options-trading-bot/pull/11); strategy `strategies/active/spy-defined-risk-rr.yaml`). IBKR live-data share to paper is blocked until a funded live account (USD 500 equity); then `MARKET_DATA_SOURCE` switches back to `ib`.

**Epic 5 (design only, not built):** Skew vs each name's own trailing history (e.g. top 20% of its 1-year range), not a fixed threshold. Calls count as rich only if borrow cost and short interest are known and under a cap. 10y yield block (e.g. no selling puts if the 10y is up ≥25 bps in 10 days). Event blackouts. Max loss as a % of the account. New names are `record_only` in [`strategies/watchlist.yaml`](strategies/watchlist.yaml) (log signal + what the structure would have paid; no orders) until a sample exists and a human promotes. Separate candidate strategy: wheel / cash-secured puts.

**Next:** Epic 4. Flatten/exit rules exist in dry-run ([#6](https://github.com/bedw3320/options-trading-bot/pull/6)); no paper lifecycle close-out yet.
