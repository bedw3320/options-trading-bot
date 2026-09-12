# Burry Study Brief — Options Risk Reversal WIP (options-trading-bot)

**Audience:** Burry (paper-desk operator)  
**Repo:** `/Users/aiagent/Documents/GitHub Repos/options-trading-bot` (Mac Mini) · `https://github.com/bedw3320/options-trading-bot`  
**Primary source:** `knowledge/archive/research_v0_ Options Risk Reversal Strategy.md` (v1.0, Feb 2026, “Step 1 of 2”)  
**Vault:** 73 atomic notes + 9 MOCs under `knowledge/notes/` (seeded from that archive; see `knowledge/ops/goals.md`, `knowledge/ops/tasks.md`)  
**Date of brief:** 2026-09-11  
**Tone rule:** Numbers-first. Label **FACT** (market standard / code) vs **VAULT** (claimed in research) vs **INFERENCE** (skeptical reading). **No invented backtests.**

---

## 1. Strategy thesis

**Claimed edge (VAULT):** In elevated put-skew regimes, sell “overpriced” OTM puts and use the credit to buy OTM calls (zero-cost / financing-neutral risk reversal). Harvest the **skew risk premium** while holding a bullish tilt (esp. EM overweight / US mega-cap underweight narrative).

**Falsifiable hypothesis (restated for LOOP principle 6):**
- **H0 to beat:** After costs, liquidity filters, and realistic assignment/gap modeling, a rules-based zero-cost RR (specified deltas/DTE/filters below) does **not** improve Sharpe / Calmar vs (a) buy-and-hold underlying and (b) delta-hedged short-put or short-strangle baselines on the same universe.
- **Claimed mechanism:** ~½ of equity implied skew is compensatable risk premium (cites Kozhan, Neuberger & Schneider 2013 — **VAULT**; treat as literature claim, not repo-proven). Skew and variance premia are the **same** risk factor → do **not** stack RR with pure variance-selling expecting diversification (**VAULT**).
- **Supporting cites in vault (unverified here):** Hull & Sinclair 2021 (delta-hedged 15Δ RR on SPY improves Sharpe); Carr & Wu 2009 (equity VRP large); Qiao et al. 2024 (EM VRP ≈ independent of DM VRP, corr ~0.11; predicts EM returns at >6m horizons).
- **Return objective (VAULT, aspirational):** 10–20% underlying moves → “5–10× options returns” via zero-cost RRs. Treat as marketing math until paper cohort exists.
- **Invalidation / decay signals (should exist; partially missing in vault):** skew percentile collapses without put decay payoff; IV < RV persistently; DXY uptrend + EM gap cluster; repeated stop hits at put+buffer; dealer/positioning regime where selling skew is crowded.

**Primary risk (VAULT, existential):** EM ETF max drawdowns −66% to −77% (EEM/EWZ/FXI) with multi-year or unrecovered peaks. Naked short puts through those regimes = ruin. Sizing + defined-risk are non-optional for EM.

**Universe (VAULT):** US high put-skew single names; EM ETFs **EEM, FXI, EWZ**; **SPY/SPX** as skew baseline.

---

## 2. Structure mechanics

### What a risk reversal is (FACT)
- Structure: **long OTM call + short OTM put** (same expiry), or the reverse. Equity “sell skew” = sell rich puts / buy cheaper calls.
- **25Δ RR** is the industry-standard skew quote. **Sign convention varies by desk:**
  - Vault formula: `25Δ RR = IV(25Δ call) − IV(25Δ put)` → equities usually **negative** (puts richer). Tradeable if ≤ −5 vol pts (**VAULT**).
  - Alternate (Bloomberg/some desks): `IV(put) − IV(call)` → positive put skew. **Always confirm convention before comparing numbers.**

### Construction (VAULT)
| Leg | Delta target | Approx OTM% | Notes |
|---|---|---|---|
| Short put | **15–25Δ** (US **20–25Δ**; EM **15–20Δ**) | **7–15% OTM** | “Richest” skew zone; Goldman cite: 15% OTM puts highest Sharpe ~0.85 (**VAULT claim**) |
| Long call | **10–20Δ**, set by **zero-cost** | **8–20% OTM** | Strike = whatever call **ask** ≈ put **credit**; high skew → can buy closer ATM |

**Zero-cost calibration algorithm (VAULT):**
1. Start put ~**20Δ**, mid-market price.
2. Find call strike with ask ≈ put credit.
3. If excess put premium: pull call closer ATM **or** keep small net credit as theta cushion.
4. Reject if either leg bid–ask **> 10% of mid**.

**Initial Greeks signature (VAULT):** 25Δ put / 15Δ call ≈ **+0.40 Δ** (moderately bullish). Asymmetric γ: upside +convexity (long call), downside −convexity (short put “gamma mortgage”). Slightly **net short vega** in asymmetric form; **θ ≈ neutral** at initiation with small positive tilt in high put-skew (~$0.01–0.03/day claimed — **VAULT, unverified**). **Volga ≈ 0** (vs straddles).

**DTE by target move (VAULT):**
| Target move | DTE |
|---|---|
| 10% | **30–45** (primary) |
| 15% | **45–60** |
| 20% (macro EM) | **60–90** |

**Roll:** at **21 DTE** remaining, assess; roll next monthly if thesis intact.

### US vs EM differences (VAULT)

| Param | US / SPY | EM (EEM, FXI, EWZ) |
|---|---|---|
| Short put Δ | 20–25 | **15–20** (gap buffer) |
| Expiry | Weeklies OK | **Monthlies only** |
| Min OI / leg | **500** | **1000** |
| Size | **3–5%** portfolio notional | **2–3%** |
| Stop | Put strike breach **+3%** | Put strike breach **+5%** |
| Defined-risk | Optional buy **5Δ** put | **Recommended** buy **10Δ** put |
| Extra filters | CBOE SKEW for SPX | **DXY** regime; overnight **gap** risk |

**Liquidity (VAULT):** EEM ~500K–1M contracts/day; EWZ ~200K–500K; FXI ~100K–300K.  
**EM structural risks:** US-hours ETF referencing overnight markets; USD↑ → EM↓ + EM IV↑ + vanna feedback (“left-tail cluster”). EM vol often **backwardation** / event humps; post-event mean-reversion faster than US (**VAULT**).

**EWZ anomaly (VAULT, dated Feb 2026):** longer-dated options with **inverted skew** (call IV > put IV by ~4–5 pts) → standard RR could get credit on both legs. Needs **separate entry logic** (open question). Do not treat as standing rule.

---

## 3. Entry / exit / risk rules (concrete vault numbers)

### Entry filters — priority stack (all must pass for bot logic in §5.1)

1. **Skew percentile** ≥ **75th** vs trailing **252-day / 1y** history on 25Δ RR (more negative = richer put skew).
2. **Absolute skew:** 25Δ RR ≤ **−5** vol pts (tradeable); ≤ **−8 to −10** (strong).
3. **IV percentile** ≥ **60%**.
4. **IV > trailing realized** (vault: trailing **30d HV** in bot table; Filter 5 in exec summary).
5. **No high-impact events** in DTE window unless trading event premium.
6. **SPX-specific:** CBOE SKEW ≥ **130** (better win rates per Tastytrade cite); ≥ **140** strongest (**VAULT**). Optimal regime: **high SKEW + low/moderate VIX** (not correlated — **VAULT**).
7. **Put/call IV ratio (extra):** 25Δ put IV / 25Δ call IV **> 1.15** (min); **> 1.25** strong.
8. **EM:** reduce exposure when **DXY trending strongly higher** (trigger **undefined** — open Q).

### Liquidity / microstructure
- Bid–ask each leg ≤ **10% of mid**.
- OI floors: US **500** / EM **1000** per leg.
- EM: monthly expirations only.

### Exit / management
- **Stop:** underlying through put strike **+3% (US)** / **+5% (EM)**.
- **Roll review:** **21 DTE**.
- **Partial Δ hedge (proposed):** hedge **50–70%** of delta, **weekly** rebalance preferred over daily (**VAULT**, untested in-repo).
- **Vol spike, price flat:** marks down via skew steepening on short put → roll put down / add Δ hedge / buy further OTM put → defined-risk.
- **Through put strike:** “most dangerous”; rolling down/out when vol elevated costs **~2–3× original credit** (**VAULT**).

### Sizing
- US **3–5%** notional; EM **2–3%**.
- Kelly / fixed-fractional that survives **−77% EWZ** drawdown: **not designed** (open Q).
- Passive put-hedging cost cite ~**260 bps/yr**; sellers earn mirror with tail losses up to **~800% of premium** (Verdad / OptionMetrics — **VAULT**).

### “Current conditions” snapshot in vault (Feb 2026 — **STALE / PARAMETER RISK**)
- VXEEM **22.36** near 52w high; VXEEM/VIX ratio **1.03–1.07×** (compressed vs historical **3–8 pt** premium).
- SPX IV ~**15%** vs RV ~**10%**; CBOE SKEW ~**140**.
- FXI ~**55th** IV percentile.
- These are **not** live inputs. Re-measure before any paper thesis.

---

## 4. Greeks / vol concepts needed to critique

| Concept | FACT (standard) | How it bites THIS strategy |
|---|---|---|
| **Skew** | IV varies by strike; equities: OTM puts richer than equidistant calls | Edge is selling steep put wing vs buying call wing when steepness is historically extreme |
| **25Δ RR** | Standard skew metric; sign convention desk-dependent | Vault uses call−put (negative). Filters (−5 / −8) meaningless without matching convention + history |
| **VRP** | IV (risk-neutral) typically > subsequent RV (physical); sellers earn premium on average, lose in crises | Vault conflates **skew premium** and **VRP**; Kozhan et al. say they are **same factor** → RR is **not** diversifying vs short-vol |
| **Vanna** | ∂Δ/∂σ = ∂vega/∂S | Long call + short put → **strongly +vanna**. Equities: spot↓ ⇒ vol↑ ⇒ Δ↑ → gets **longer into selloffs** (**VAULT greek-dynamic**, confidence: likely). “Put skew IS the vanna premium.” |
| **Vega path** | Nominally near-flat; during IV spike skew steepens | Uniform +5 ATM vol → vault example +7–8 on 25Δ puts vs +3–4 on 15Δ calls → **functionally short vol in crises** |
| **Gamma** | Asymmetric | Upside helps; into short put ATM = peak −γ = accelerating losses |
| **Theta** | ~flat at start | Near put: +θ; near call: −θ. Not a “theta strategy”; directional + skew |
| **Volga** | ~0 for RR | Distinguishes from straddles; don’t expect vol-of-vol payoff |

**Critique angles:**
1. Selling skew = selling crash insurance with a financed lottery ticket. Win rate can look high; left tail owns you.
2. Positive vanna + negative spot-vol corr = **adverse feedback** exactly when stops matter; EM adds USD cluster.
3. Filters that require **high IV percentile AND steep skew** may select **pre-crash** regimes; academic “premium” is compensation for that selection.
4. “Zero-cost” ignores **spread × 2 legs**, margin, assignment, and early exercise on short puts — paper must model these or results are fantasy.
5. Hull/Sinclair-style evidence is often **delta-hedged** index RR; vault also wants **directional EM** exposure — different bet.

---

## 5. How it maps to this bot

### YAML agent loop (FACT — code/harness)
- Strategies = descriptive YAML (`strategies/_schema.yaml`); agent interprets NL conditions with pre-fetched data (`core/runner.py` → `build_strategy_prompt`).
- `OrderIntent` (`schemas/output.py`): **single** `symbol` + optional one `contract_symbol` / strike / dte. **No multi-leg / ratio / BAG fields.**
- `strategies/active/`: **empty** (`.gitkeep` only). Examples = `hype-volume-options.yaml`, `sol-momentum.yaml` — **not** risk-reversal.
- Default run path (`main.py`): `strategies/examples/sol-momentum.yaml`. Knowledge graph **not wired** into strategy YAML yet (`knowledge/ops/goals.md`: “Connect knowledge graph insights back to trading bot strategy YAML” still open).

### IBKR options path (FACT)
- `integrations/ibkr/options_data.py`: `reqSecDefOptParams` → lists contracts by expiry/strike/right. **`open_interest: None`**. **No IV, no Greeks, no skew surface, no mid/spread.**
- `integrations/ibkr/orders.py`: **single-leg** `Option` via OCC parse or localSymbol; notional→qty via snapshot; **Market/Limit/STP LMT**. **No `BAG` / combo / multi-leg.**
- Agent tool `create_order` (`core/agent.py`) calls IB place in **one hop** when `allow_trading=True` — directly contradicts LOOP constraint 1 target (preview → token → revalidate → place). `LOOP.md` admits gap.

### LOOP constraints relevant to papering RR (FACT)
1. LLM proposes; code places — **not implemented** (one-hop `create_order`).
2. Fail-closed account identity paper/live check — **not implemented**.
3. Autonomy armed, not implied — paper needs `--allow-trading` + `TRADING_MODE=paper`; live needs extra arm.
4. Process skills ≠ broker — OK in spirit; but agent still holds `create_order` tool.
- First principles 6–7: falsifiable edge + versioned experiments (replay → shadow → paper cohort). RR is still **Step 1 research**, not an experiment registry entry.
- Roadmap: **Epic 0** (first reproducible paper fill) not done; **Epic 7** is where chains/Greeks/skew/BAG/edge platform live. Papering RR before Epic 0–2 is out of sequence for *autonomous* execution; manual/confirm-in-TWS paper tickets are a separate path.

### What’s missing for paper RR (gap list)
| Need | Status |
|---|---|
| RR strategy YAML in `strategies/active/` | Missing |
| Multi-leg `OrderIntent` + IBKR BAG | Missing |
| Chain Greeks / IV / skew / IV percentile history | Missing (ORATS cited $399/yr, not integrated) |
| OI + bid-ask mid checks in data path | Missing (`OI=None`) |
| Defined-risk 3-leg (short put + long call + long 10Δ put) | Missing |
| Event calendar / DXY / CBOE SKEW feeds | Missing |
| Stop logic on underlying vs put strike + buffer | Not in runner risk (only `max_position_pct`, daily trades, confidence) |
| Vanna / portfolio risk monitor | Open question only |
| Backtest / replay with OptionMetrics or ORATS | Deferred (`goals.md`) |
| GuardedBroker preview token | Epic 2; not shipped |
| Any in-repo backtest numbers for these filters | **None — do not invent** |

---

## 6. Gaps / open questions

### From vault (`knowledge/notes/open-questions.md` + archive §6)
**Strategy design**
- Kelly / fixed-fractional sizing that survives −77% EWZ without ruin.
- Cost-benefit of **10Δ** put protection vs skew level (when does wing destroy edge?).
- Empirically test **50–70%** partial hedge weekly vs daily.
- EWZ **inverted skew** entry mechanics.

**Bot architecture**
- Confirm combo/2–3 leg support on broker (IBKR BAG) — code says **no** today.
- EOD screening vs intraday.
- OptionMetrics vs ORATS for regime-conditional backtests.
- Real-time vanna alerts vs DXY exposure.

**Macro filters**
- Quantitative **DXY** trigger (e.g. 20d breakout above 200d MA suggested, not locked).
- Operationalize Qiao EMVRP as 6m+ forward entry signal.

### Skeptical additions (INFERENCE — grill material)
1. **No own backtest** of the layered filter stack; academic citations ≠ this parameter set on EEM/EWZ/FXI with IBKR costs.
2. **Feb 2026 “opportunity” table is stale**; vault warns parameter staleness (`knowledge/CLAUDE.md`).
3. **Sign convention / RR definition** risk if ORATS slope fields don’t match call−put.
4. **Selection bias:** requiring IV pct ≥60 + skew ≥75th may load crisis-adjacent periods.
5. **Correlation of edges:** vault itself says skew premium ≈ variance premium → “EM independent VRP” does not make EM RR independent of SPX short-vol crashes if global risk-off.
6. **Failure-mode coverage thin** — `goals.md`: only 3 failure-mode notes; need vol collapse, liquidity crisis, skew inversion.
7. **Assignment / corporate action / early exercise** on short ETF puts ignored.
8. **“5–10× options returns”** on zero-cost RR is payoff asymmetry storytelling; paper KPI should be **distribution of P&L / max DD / time-underwater**, not anecdotal multiples.
9. **Harness not ready:** one-hop orders + no multi-leg + empty active strategies = paper RR today would be **manual construction outside the agent loop**, or reckless single-leg approximation (not the strategy).
10. **Confidence labels:** many atomic notes `confidence: likely` / single-source; only a subset cite primary papers with `proven`.

---

## 7. What Burry should grill Will on before papering this first

1. **Falsification:** Exact H0, evaluation horizon, and kill criteria *before* first paper ticket (LOOP §6). What number ends the experiment?
2. **Convention:** Is 25Δ RR call−put or put−call in the data you’ll actually use? Show one ORATS/IBKR row.
3. **Own backtest:** Filter stack on SPY first (liquid), then EEM — with spreads, OI, and stop rules. No paper until a dated replay artifact exists (even crude).
4. **Defined-risk mandatory for EM?** Yes/no. If yes, recompute “zero-cost” after paying for 10Δ put — edge still positive at −5 vs −10 skew?
5. **Sizing:** Show ruin probability under EWZ −77% path at 2–3% notional with and without wing. If unprepared, EM is out of paper universe v0.
6. **Execution path:** Multi-leg BAG or two separate tickets? Slippage model? Who clicks confirm-in-TWS until GuardedBroker exists?
7. **Why EM overweight now?** VXEEM/VIX compression in vault argues EM vol premium vs SPX is *not* rich — contradicts “harvest EM VRP” narrative. Resolve.
8. **Hedge policy:** Directional (+0.4Δ) vs Hull-style delta-hedged. Pick one for paper cohort; don’t mix.
9. **Stop realism:** Put+3/5% vs gap open through stop — how is gap stop handled on paper?
10. **Sequence:** Epic 0 paper fill with a **trivial single-leg** first, or jump to RR? If jump: accept that RR paper is **desk-manual**, not bot-autonomous.
11. **Data:** ORATS paid + wired, or IBKR-only Greeks? EOD enough?
12. **Conflict with examples:** Are we shelving hype-volume/SOL, or is RR competing for the same paper book risk budget?

---

## Quick reference — file map

| Path | Role |
|---|---|
| `knowledge/archive/research_v0_ Options Risk Reversal Strategy.md` | Canonical WIP strategy |
| `knowledge/notes/{risk-reversals,screening-and-filters,execution-parameters,greeks-and-volatility,em-etf-characteristics,spy-spx-baseline,open-questions,options-trading-overview,index}.md` | MOCs |
| `knowledge/CLAUDE.md` | Vault methodology; stale-param warning |
| `knowledge/ops/{goals,tasks,derivation,config}.yaml|md` | Vault status / pipeline |
| `LOOP.md` / `AGENTS.md` / `ROADMAP.md` | Harness law; Epic 0→7 |
| `strategies/_schema.yaml` | YAML contract (NL conditions) |
| `strategies/examples/*.yaml` | Non-RR examples only |
| `schemas/output.py` | Single-leg `OrderIntent` |
| `integrations/ibkr/options_data.py` | Chain list, no Greeks/OI |
| `integrations/ibkr/orders.py` | Single-leg place only |
| `core/agent.py` | One-hop `create_order` tool |

---

*End of brief. Update when: (a) RR YAML lands, (b) first dated backtest artifact exists, (c) BAG path ships, or (d) Feb-2026 regime numbers are refreshed.*
