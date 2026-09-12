# Roadmap — Autonomous Options Research Backbone

## North star

Build an autonomous options research institution in miniature: detect potential market
inefficiencies, form falsifiable theses, execute risk-bounded paper trades through IBKR,
attribute outcomes, and improve through controlled experiments.

Long-term strategic moats:

1. Proprietary options knowledge graph
2. High-quality timestamped decision/outcome dataset
3. Superior evaluation and counterfactual machinery
4. Reliable execution and risk infrastructure
5. Repeatable process for discovering and validating edges

Phase-one success is **not** positive paper P&L. The system succeeds when decisions are
reproducible; evidence, abstentions, orders, and fills have complete lineage; reasoning
failures are distinguishable from strategy and execution failures; and proposed
improvements are tested before promotion.

## Delivery principles

See [`LOOP.md`](LOOP.md) **First principles** for stable epistemic and safety law. This roadmap adds delivery sequence only:

- Build walking vertical slices and fire paper trades early.
- End every epic with an observable demo.
- Use just-in-time research spikes only when an epic reaches a real uncertainty.

## Delivery sequence

```text
Baseline
  → Walking autonomous cycle
  → Guarded execution
  → Unattended operation
  → Evaluation foundation
  → Controlled improvement
  → Multi-agent desk
  → Options edge platform
```

---

## Epic 0 — Establish the IBKR paper baseline

**Goal:** Prove the repo and Mac Mini can operate predictably against IBKR paper.

### Scope

- [ ] Run the full test suite and record/fix the baseline
- [ ] Start IB Gateway against the paper account
- [ ] Verify the connected account identity and paper status
- [ ] Capture account and position snapshots
- [ ] Send one tiny, predetermined paper order
- [ ] Reconcile the fill into SQLite
- [ ] Document the reproducible Mini startup command

### Acceptance criteria

- The process aborts on a live or unexpected account.
- One paper order is visible in IBKR and traceable in SQLite.
- Restart instructions work from a clean shell.

### Demo

Start the Gateway and bot, submit one known paper order, then show the matching local
event and IBKR fill.

### Research spike

None. Use the existing `ib_insync` integration.

---

## Epic 1 — Walking autonomous cycle

**Goal:** One agent completes one bounded paper-trading cycle without human input.

### Scope

- [ ] Add a run-once entry point
- [ ] Limit the first slice to one instrument and one deterministic signal
- [ ] Capture a timestamped market snapshot
- [ ] Let the agent research and return a typed trade or abstention
- [ ] Apply deterministic risk checks
- [ ] Place a paper order when approved
- [ ] Reconcile the result and stop
- [ ] Preserve minimal lineage: cycle, evidence, decision, intent, order, fill
- [ ] Log abstention as a first-class outcome

### Acceptance criteria

- One command completes without intervention.
- The cycle trades or abstains with a structured rationale.
- Every artifact shares a `cycle_id`.
- The process terminates after reconciliation.

### Demo

Invoke one command and inspect the complete lineage for its trade or abstention.

### Non-goals

- Infinite daemon
- Multiple agents
- Multiple strategies or instruments
- Self-modification

---

## Epic 2 — Guarded execution

**Goal:** Make autonomous paper execution trustworthy and structurally incapable of
bypassing risk.

### Scope

- [ ] Remove `create_order` and `close_position` tools from reasoning agents (refuse-only stubs; they cannot place)
- [x] Introduce one `GuardedBroker` execution boundary
- [ ] Add a mock broker with the same contract as IBKR
- [x] Implement preview → single-use token → revalidate → place
- [x] Verify account id and paper/live status before every send
- [ ] Add idempotency keys and duplicate-order prevention
- [ ] Reject stale quotes and expired previews (expired tokens: yes; stale quotes: no)
- [ ] Reconcile open orders, fills, and positions
- [ ] Add cancel and flatten controls

### Acceptance criteria

Tests prove that duplicate, expired, mismatched-account, oversized, and stale orders
cannot execute. No reasoning agent imports or invokes `ib_insync`.

### Demo

Run the mock safety suite, then execute the same contract against IBKR paper.

### Research spike

Review preview-token and fail-closed identity patterns from the prior-art IBKR MCP
implementations only when defining `GuardedBroker`.

---

## Epic 3 — Operate repeatedly on the Mac Mini

**Goal:** Run bounded cycles unattended through a paper-trading session.

### Scope

- [ ] Add an explicit paper-autonomy arm
- [ ] Add market-hours scheduling
- [ ] Prevent overlapping cycles with a process lock
- [ ] Classify retryable and terminal failures
- [ ] Reconnect the Gateway and reconcile before resuming
- [ ] Add a latching kill switch
- [ ] Recover from restart without duplicate orders
- [ ] Emit heartbeat and daily summary events
- [ ] Install the runtime as a local Mini service

### Acceptance criteria

- No overlapping cycles.
- Disconnect/restart cannot duplicate an order.
- The kill latch requires deliberate re-arm.
- A complete paper session produces a coherent daily summary.

### Demo

Run multiple scheduled cycles, interrupt the Gateway once, and show safe recovery.

---

## Epic 4 — Evaluation and counterfactual foundation

**Goal:** Learn something defensible from every decision, including abstentions and
missed opportunities.

### Scope

- [ ] Store the full candidate universe for each cycle
- [ ] Preserve inputs, source provenance, and freshness
- [ ] Record signals, evidence, disagreements, and rejected candidates
- [ ] Attribute orders, fills, slippage, and outcomes
- [ ] Define evaluation horizons before observing outcomes
- [ ] Score data, reasoning, strategy, risk, execution, and outcome separately
- [ ] Evaluate rejected candidates under the same availability/liquidity constraints
- [ ] Add temporal-leakage tests

### Acceptance criteria

- An evaluator can reconstruct a decision from stored artifacts.
- Missed-opportunity analysis uses timestamped candidates and predeclared horizons.
- A losing trade is not automatically classified as bad reasoning.
- A profitable trade is not automatically classified as good reasoning.

### Demo

Reconstruct one trade and one abstention, then produce an attribution report without
using future information unavailable at decision time.

### Research spike

Counterfactual evaluation, temporal leakage, and calibrated decision scoring.

---

## Epic 5 — Controlled improvement and promotion

**Goal:** Convert lessons into versioned experiments rather than uncontrolled
self-modification.

### Scope

- [ ] Let the evaluator propose explicit hypotheses
- [ ] Version prompts, thresholds, strategies, and agent configurations
- [ ] Add an experiment registry
- [ ] Replay candidate versions on historical cycle snapshots
- [ ] Run shadow comparisons on live paper inputs
- [ ] Run independent paper cohorts
- [ ] Define promotion and rejection thresholds
- [ ] Keep safety rules immutable to learning agents
- [ ] Preserve every promotion decision and its evidence

### Acceptance criteria

- No agent can directly edit or promote its production strategy.
- Every promoted change has replay, shadow, and paper evidence.
- Rejected experiments remain queryable.

### Demo

Take one evaluator hypothesis through proposal, replay, shadow comparison, and an
evidence-backed promotion or rejection.

---

## Epic 6 — Earn the multi-agent trading desk

**Goal:** Determine whether specialist agents outperform the single-agent baseline.

### Scope

Add and evaluate one role at a time:

1. [ ] Adversarial critic
2. [ ] Parallel research scouts
3. [ ] Portfolio synthesizer
4. [ ] Independent offline evaluator

Compare each configuration on:

- Evidence quality and provenance
- Decision calibration
- Opportunity capture
- Risk-adjusted paper outcomes
- Drawdown
- Latency and cost
- Reproducibility

### Acceptance criteria

- Every additional agent has a typed input/output contract.
- Researchers remain read-only.
- Execution remains deterministic.
- A role is retained only if it delivers measurable lift over the baseline.

### Demo

Run the same timestamped cycles through baseline and candidate desk configurations,
then show the comparison and keep/remove decision.

### Non-goal

An unbounded swarm.

---

## Epic 7 — Options edge platform

**Goal:** Integrate the domain machinery required to discover and validate proprietary
options edges.

### Scope

- [ ] Normalize chains, Greeks, IV surfaces, skew, and term structure
- [ ] Model liquidity, spreads, commissions, assignment, and exercise
- [ ] Implement multi-leg IBKR BAG execution
- [ ] Track event and regime context
- [ ] Connect evidence to the proprietary options knowledge graph
- [ ] Add strategy families and portfolio-level capital allocation
- [ ] Build edge-discovery experiments and decay monitoring

### Acceptance criteria

- Options inputs are timestamped and reproducible.
- Backtests/replays model realistic execution constraints.
- Every claimed edge has a falsifiable hypothesis, experiment history, and observed
  out-of-sample evidence.

### Demo

Run one options thesis from knowledge-graph evidence through signal, construction,
paper execution, evaluation, and edge-validation reporting.

---

## GitHub issue mapping

GitHub Issues is currently disabled for this repository. Once enabled, create:

1. `Roadmap: autonomous options research and paper-trading backbone` (parent)
2. `[Epic 0] Establish the IBKR paper baseline`
3. `[Epic 1] Build the walking autonomous cycle`
4. `[Epic 2] Introduce guarded execution`
5. `[Epic 3] Operate repeatedly on the Mac Mini`
6. `[Epic 4] Build evaluation and counterfactual foundations`
7. `[Epic 5] Add controlled improvement and promotion`
8. `[Epic 6] Earn the multi-agent trading desk`
9. `[Epic 7] Build the options edge platform`

Add Epic 0–7 as ordered sub-issues of the parent. Use the matching sections above as
issue bodies and apply the existing `enhancement` label.

## Immediate next step

Start Epic 0. Do not begin multi-agent work or additional architecture research until
the first IBKR paper fill is reproducible and traceable.
