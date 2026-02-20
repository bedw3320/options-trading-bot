**TRADING BOT: STRATEGY RESEARCH**

*Zero-Cost Risk Reversals on High-Skew EM and US Equities*

Version 1.0  |  February 2026  |  Living Document — Step 1 of 2

# **Executive Summary**

Selling overpriced puts to finance OTM calls in elevated-skew environments is a positive expected-value strategy. The skew risk premium is real, persistent, and approximately half of observed implied skew represents compensatable risk premium (Kozhan, Neuberger & Schneider, 2013). Hull & Sinclair (2021) demonstrated that delta-hedged 15-delta risk reversals on SPY improve portfolio Sharpe ratios, while Qiao et al. (2024) showed that the EM variance risk premium operates nearly independently of developed-market VRP (correlation of just 0.11), creating a differentiated alpha stream.

Current conditions as of February 2026 — VXEEM at 22.36 near its 52-week high, SPX put skew in the top percentile of its post-July 2024 range, and a gaping implied-realized vol spread (SPX implied \~15% vs. realized \~10%) — present a structurally favorable entry window.

*Primary risk: EM ETFs have suffered \-66% to \-77% peak-to-trough drawdowns (not fully recovered in 16+ years). Position sizing and defined-risk structures are existential requirements.*

# **Macro Thesis & Target Universe**

Strategy orientation: Overweight Emerging Markets / Underweight US Mega-Caps. Target instruments:

* US Equities (high put-skew single names)

* EM ETFs: EEM (iShares MSCI Emerging Markets), FXI (iShares China Large-Cap), EWZ (iShares MSCI Brazil)

* Broad ETFs: SPY for baseline skew comparisons

Return objective: 10-20% underlying moves generating 5-10x options returns via zero-cost (financing-neutral) risk reversals.

# **1\. Screening for Tradeable Skew**

## **1.1 The 25-Delta Risk Reversal as Primary Signal**

The 25-delta risk reversal (25Δ RR \= IV of 25Δ call minus IV of 25Δ put) is the industry-standard skew metric. In equities, this value is persistently negative — puts trade at higher implied volatility than equidistant calls due to structural demand for downside hedges. The strategy edge emerges when this skew becomes unusually steep relative to its own history.

## **1.2 Quantitative Entry Filters (Layered)**

Apply in priority order:

* **Filter 1 (Primary):** Skew percentile rank ≥ 75th on 1-year lookback — current 25Δ RR is wider (more negative) than 75% of readings in the past year

* **Filter 2 (Absolute):** 25Δ RR ≤ \-5 vol points (tradeable); ≤ \-8 to \-10 vol points (strong signal)

* **Filter 3 (IV Level):** IV percentile ≥ 60% — options broadly expensive, favorable for credit collection

* **Filter 4 (SPX-specific):** CBOE SKEW ≥ 130 (Tastytrade research: above 130 \= significantly better win rates; above 140 \= strongest signal)

* **Filter 5 (IV-to-HV Spread):** Implied vol \> trailing realized vol — confirms overpricing

* **Filter 6 (Event):** No high-impact events within DTE window unless specifically trading the event premium

## **1.3 Key Nuance: SKEW vs. VIX Divergence**

SKEW and VIX are not correlated. The optimal setup is high SKEW \+ low-to-moderate VIX ("stealth tail-risk pricing") — expensive puts without genuinely elevated realized volatility. Current environment approximates this: CBOE SKEW \~140, VIX \~21, 30-day realized vol on SPX barely above 10%.

## **1.4 EM-Specific Screening Metrics**

| ETF | Current IV / VXEEM | Signal Strength | Key Note |
| :---- | :---- | :---- | :---- |
| EEM | 22-23% ATM IV; VXEEM 22.36 | Moderate | VXEEM/VIX ratio 1.03-1.07x (compressed vs. historical 3-8pt premium) |
| EWZ | 28.85% (VXEWZ) | Strong | Inverted skew on longer-dated options — call IV exceeds put IV by 4-5 pts (net credit possible) |
| FXI | \~55th IV percentile | Moderate | Tradeable but not extreme; China-specific policy risk creates gap risk |

*EWZ anomaly: June-Nov 2026 expirations show inverted skew driven by bullish speculative demand. A standard risk reversal here could receive premium from BOTH legs — a structural gift aligned with the EM overweight thesis.*

## **1.5 Data Sources for Bot**

* **ORATS:** $399/year — pre-calculated skew parameters (slope, deriv), ATM vol, IV rank/percentile, historical data to 2007\. Optimal for systematic screening.

* **CBOE SKEW Index:** Free via Barchart ($SKEW) — SPX-specific but useful as macro regime filter

* **Put-Call IV Ratio Filter:** 25Δ put IV / 25Δ call IV \> 1.15 (minimum); \> 1.25 (strong signal)

# **2\. Strike & Expiry Selection**

## **2.1 Strike Calibration Framework**

Optimal structure for 10-20% underlying moves with 5-10x options returns:

| Leg | Delta Target | Approx OTM% | Rationale |
| :---- | :---- | :---- | :---- |
| Short Put | 15-25Δ | 7-15% OTM | Richest portion of skew curve; \~1.0-1.3 SD below spot. Goldman 10yr study: 15% OTM puts \= highest Sharpe (0.85). |
| Long Call | 10-20Δ (zero-cost constraint) | 8-20% OTM | Strike determined by whatever achieves zero net premium after put credit. High skew allows buying closer-to-ATM calls than normal. |

## **2.2 Zero-Cost Calibration Algorithm**

Step 1: Identify put strike at 20-delta — where skew is richest. Price at mid-market.

Step 2: Find call strike where ask price ≈ put credit received.

Step 3: If excess put premium exists, move call closer to ATM (higher probability of profit) or accept small net credit as theta cushion.

Step 4: Verify bid-ask spread on each leg ≤ 10% of mid-market premium. If put sells for $0.50, spread must be ≤ $0.05.

## **2.3 DTE Selection by Target Move**

| Target Move | DTE | Notes |
| :---- | :---- | :---- |
| 10% move | 30-45 DTE | Primary vehicle — Goldman: 1-month tenors outperformed 12-month on absolute and risk-adjusted returns for put selling |
| 15% move | 45-60 DTE | Wider window; more theta decay to manage |
| 20% move | 60-90 DTE | Suitable for macro EM thesis plays |

*Roll trigger: At 21 DTE remaining, assess position. Roll to next monthly cycle if thesis intact. Avoid holding through high-impact EM events unless trading the event premium.*

## **2.4 Liquidity Requirements**

* **EM ETFs (EEM, FXI, EWZ):** Monthly expirations only — weeklies lack sufficient OI at 15-delta strikes. Minimum OI per leg: 1,000 contracts.

* **SPY / US single names:** Weekly options acceptable; minimum OI: 500 contracts. SPY Mon/Wed/Fri weeklies have deep OTM liquidity.

* **EM ETF relative liquidity:** EEM \~500K-1M contracts/day, EWZ \~200K-500K, FXI \~100K-300K

# **3\. Greeks & Volatility Dynamics**

## **3.1 Delta-Gamma Signature**

A 25Δ put / 15Δ call zero-cost risk reversal initializes at approximately \+0.40 delta — moderately bullish. Evolution:

* **Underlying rallies halfway to call strike:** Delta rises to \+0.60-0.70 (approaching synthetic long)

* **Underlying at or above call strike:** Delta \~0.80-1.0 — full synthetic long territory

* **Underlying falls toward put strike:** Short put approaches ATM (peak negative gamma), call gamma vanishes — position accelerates into losses

The gamma profile is fundamentally asymmetric: positive convexity on the upside (call gamma accelerates profits), negative convexity on the downside (short put gamma amplifies losses). This is the core structural trade-off — a gamma mortgage that funds upside convexity.

## **3.2 Vega, Vanna, and the Skew Surface**

At initiation: approximately vega-neutral for symmetric structures; slightly net short vega for the asymmetric (25Δ put / 15Δ call) configuration (ATM put carries more vega than far-OTM call). However, this ignores the critical dynamic:

*During IV spikes, skew steepens — put IV rises disproportionately to call IV. A uniform \+5 vol-point ATM increase might translate to \+7-8 pts on 25Δ puts but only \+3-4 pts on 15Δ calls. The position is functionally net short vol during crises, even when nominally vega-neutral.*

### **Vanna: The Dominant Second-Order Greek**

Both legs contribute positive vanna: the long OTM call has positive vanna directly; shorting the OTM put (negative vanna) also contributes positive vanna when the sign is reversed. Net result: strongly positive vanna — delta increases as volatility rises.

In equity markets with negative spot-vol correlation (prices fall → vol rises), this creates a dangerous feedback: the position gets longer delta precisely as the underlying is falling. This amplifies losses beyond what first-order Greeks suggest. The put skew IS the vanna premium — selling it means accepting this unfavorable correlation exposure.

### **Volga (Vomma): Approximately Zero**

The long call's positive volga offsets the short put's negative volga contribution. Risk reversal is not meaningfully exposed to vol-of-vol, distinguishing it from straddles or butterflies.

### **Theta: Near-Zero with Directional Tilt**

Zero-cost structure: short put theta collection roughly offsets long call theta bleed. High-put-skew environments create a slight theta positive (\~$0.01-0.03/day on notional-neutral structure). Theta turns directional as underlying moves:

* **Near put strike:** Theta turns positive — short ATM put with peak theta, long far-OTM call with minimal theta

* **Near call strike:** Theta turns negative — long near-ATM call at peak theta burn, short far-OTM put contributing nothing

## **3.3 Dynamic Adjustment Protocols**

| Scenario | What Happens | Response Options |
| :---- | :---- | :---- |
| Vol spike, no price move | Marks negatively — short put vega loss exceeds long call vega gain due to skew steepening | 1\. Roll put to lower strike2. Add delta hedge (sell shares/futures)3. Buy further-OTM put to convert to defined-risk spread |
| Vol crush, range-bound underlying | Long call decays; short put profits | 1\. Close position, capture theta2. Roll call to nearer strike3. Let theta accumulate, re-enter new RR |
| Underlying falls through put strike | Synthetic short put with accelerating losses — most dangerous scenario | Pre-defined stop: put strike breach \+ 2-3% (US) or \+5% (EM). Rolling down/out costs 2-3x original credit when vol is elevated. |

*For systematic bot: partial delta hedging (50-70% of delta) with weekly rebalancing provides better risk-adjusted returns than daily hedging — balances skew premium isolation with directional exposure.*

## **3.4 EM-Specific Greeks Considerations**

* **USD correlation:** USD strengthening simultaneously pushes EM equities lower (delta loss), increases EM IV (vega loss via skew steepening), and amplifies vanna feedback. All Greeks move against the position simultaneously — the 'left-tail cluster.'

* **Gap risk:** EM ETFs trade US hours but reference overnight markets. Chinese policy announcements, Brazilian CB decisions, currency devaluations create opening gaps that delta hedging cannot protect against.

* **Term structure:** EM vol more frequently in backwardation; pronounced humps around events. Post-event mean reversion is faster than US — faster vol spike/revert creates post-event entry opportunities.

* **DXY regime filter:** Reduce EM risk reversal exposure when USD is trending strongly higher

# **4\. Historical Performance & Failure Modes**

## **4.1 Academic Foundation**

The skew risk premium has robust, multi-study support:

* **Kozhan, Neuberger & Schneider (2013):** Almost half of implied volatility skew represents risk premium — not an informational signal. Combined with the finding that skew and variance premia are manifestations of the same underlying risk factor — do not combine with pure variance-selling strategies expecting diversification.

* **Hull & Sinclair (2021):** Delta-hedged 15-delta risk reversals on SPY improve portfolio Sharpe ratios. OTM puts are systematically overpriced relative to OTM calls — implied risk-neutral skewness consistently exceeds subsequently realized skewness.

* **Carr & Wu (2009):** Variance risk premium over \-50% per month for S\&P 500; annualized Sharpe of approximately \-1.7 for short variance exposure — 5x larger than equities' Sharpe.

* **Qiao, Xu, Zhang & Zhou (2024):** First comprehensive study of EM VRP across 9 countries (2006-2023). EMVRP predicts EM stock returns for horizons \>6 months (adjusted R² of 5.1-14.2%) and EM currency returns. Near-zero correlation (0.11) with developed-market VRP \= independent alpha stream.

## **4.2 EM Bull Market Historical Pattern**

Regime analysis: risk reversals perform best when initiated during elevated skew/vol periods that precede EM rallies. The strategy captures both:

* Premium decay (put skew compression during risk-on)

* Directional upside (call appreciation)

Historical EM bull markets: 2003-2007 EEM \+300%, 2016-2017 recovery \+50%, post-COVID rebound all followed this pattern.

## **4.3 Catastrophic Failure Modes — Sizing Constraints**

Maximum drawdowns in EM ETFs vs. US equities are categorically different:

| ETF | Max Drawdown | Recovery Time | Implication for Bot |
| :---- | :---- | :---- | :---- |
| EEM | \-66.4% (Nov 2008\) | 2,220 trading sessions | Any put at ≤30% OTM would have been breached |
| EWZ | \-77.3% (Jan 2016\) | Still not recovered (16+ years) | Size assuming \-77% is possible; not just 1-SD moves |
| FXI | \-73.3% (Oct 2008\) | Still not recovered | China policy risk \= structural gap-down risk |

S\&P 500: \-34% in 23 trading days (COVID 2020\) — the fastest bear market in history. Delta hedging gave virtually no time to adjust.

*Verdad Capital (OptionMetrics data): Passive put hedging (30% OTM, 3-month, monthly roll) costs \~260 bps/year; premium sellers earn the mirror \~260 bps/year but with losses up to \-800% of premium in tail events. The edge is real but the distribution is deeply negatively skewed.*

# **5\. Implementation Architecture**

## **5.1 Bot Screening Logic (Ordered Filters)**

Layer in this priority order — all 5 must pass for entry:

| Filter | Condition | Source |
| :---- | :---- | :---- |
| 1\. Skew Rank | 25Δ RR ≥ 75th percentile vs. trailing 252-day history | ORATS slope/deriv fields |
| 2\. Skew Absolute | 25Δ RR ≤ \-5 vol pts (tradeable) / ≤ \-8 (strong) | ORATS or manual calc |
| 3\. IV Percentile | ≥ 60% (options broadly expensive) | ORATS ivPct or TastyTrade |
| 4\. IV-to-HV Spread | Implied vol \> trailing 30-day realized vol | ORATS or Yahoo Finance HV |
| 5\. Event Calendar | No earnings/CB/election within DTE window | Earnings Whispers API or manual |

## **5.2 Trade Parameters by Instrument**

| Parameter | US Equities / SPY | EM ETFs (EEM, FXI, EWZ) |
| :---- | :---- | :---- |
| Short put delta | 20-25Δ | 15-20Δ (wider buffer for gap risk) |
| Long call delta | Zero-cost constraint | Zero-cost constraint |
| Target DTE | 30-45 days | 30-45 days (monthly only) |
| Minimum OI per leg | 500 contracts | 1,000 contracts |
| Max bid-ask spread | ≤ 10% of mid-price | ≤ 10% of mid-price |
| Position size | 3-5% of portfolio notional | 2-3% (reduced for EM vol) |
| Roll trigger | 21 DTE remaining | 21 DTE remaining |
| Stop-loss | Put strike breach \+ 3% | Put strike breach \+ 5% |
| Defined-risk structure | Optional (buy 5Δ put) | Recommended (buy 10Δ put) |

## **5.3 Data & Execution Stack**

* **Options Data:** ORATS API ($399/year) — pre-calculated skew params, IV rank/percentile, historical to 2007

* **Execution:** IBKR TWS API via ib\_insync — combo orders for multi-leg risk reversals

* **IV Calculation:** scipy.optimize.brentq for IV inversion; scipy.stats.norm for delta calculation

* **Regime Filter:** CBOE SKEW Index via Barchart ($SKEW) \+ DXY trend for EM positions

## **5.4 Current Opportunity Assessment (February 2026\)**

| Instrument | Signal Strength | Key Condition | Recommended Action |
| :---- | :---- | :---- | :---- |
| SPY/SPX | Strong | CBOE SKEW \~140; 30-day RV \~10% vs. IV \~15%; wide implied-realized gap | Primary target for zero-cost RR; put skew at extreme levels |
| EWZ | Strong+ | Inverted skew on longer-dated options; VXEWZ 28.85% | Unusual: potential net credit entry on standard RR structure |
| EEM | Moderate | VXEEM 22.36 near 52-wk high but VXEEM/VIX ratio only 1.03-1.07x | EM vol premium vs SPX is compressed; EWZ more attractive on relative value |
| FXI | Moderate | \~55th IV percentile | Tradeable but not extreme; China policy gap risk warrants smaller sizing |

# **6\. Open Questions & Step 2 Agenda**

The following items are unresolved and should be addressed in Step 2 with the implementation agent:

## **Strategy Design**

* **Position sizing framework:** Develop Kelly-based or fixed-fractional sizing that survives \-77% EWZ drawdown without ruin

* **Defined-risk vs. naked short put:** Quantify the cost-benefit of buying the 10Δ put protection leg on EM positions — at what skew levels does the protection cost destroy the edge?

* **Delta hedging frequency:** Empirically test 50-70% partial hedge at weekly vs. daily rebalancing on historical data

* **EM inverted skew handling:** Build specific logic for EWZ-type inverted skew scenarios — different entry mechanics needed

## **Bot Architecture**

* **Broker API:** IBKR vs. Tradier — confirm combo order support for 2-3 leg structures

* **Data latency:** ORATS vs. real-time Greeks from broker feed — assess whether end-of-day screening is sufficient or intraday needed

* **Backtesting engine:** OptionMetrics vs. ORATS historical data for regime-conditional backtests

* **Risk monitoring:** Real-time vanna monitoring — alert when position vanna exceeds threshold relative to portfolio DXY exposure

## **Macro Regime Filters**

* **USD regime:** Define quantitative trigger for reducing EM exposure (e.g., DXY 20-day breakout above 200-day MA)

* **EMVRP signal:** Operationalize Qiao et al. EMVRP as a forward-entry signal for the 6-month+ horizon EM calls

# **Key Sources & References**

Academic Papers:

* Kozhan, Neuberger & Schneider (2013). "The Skew Risk Premium in the Equity Index Market." — SSRN: papers.ssrn.com/sol3/papers.cfm?abstract\_id=1571700

* Hull & Sinclair (2021). "The Risk-Reversal Premium." — SSRN: papers.ssrn.com/sol3/papers.cfm?abstract\_id=3968542

* Carr & Wu (2009). "Variance Risk Premia." Review of Financial Studies. — NYU: engineering.nyu.edu

* Qiao, Xu, Zhang & Zhou (2024). Emerging Market Variance Risk Premium — Tsinghua: eng.pbcsf.tsinghua.edu.cn

Practitioner Research:

* Goldman Sachs. "The Art of Put Selling." (2016) — 10-year study on put selling across strikes and tenors

* Macrosynergy. "The Risk-Reversal Premium." macrosynergy.com/research/the-risk-reversal-premium

* Verdad Capital. "The Efficacy & Cost of Hedging with Options." verdadcap.com

* QuantPedia. "Volatility Risk Premium Effect." quantpedia.com

* RiskMetrics Working Paper 99-06. "Vega Risk and the Smile." (Vanna/Volga framework)

Data & Tools:

* ORATS Data API: orats.com/data-api — skew screening and historical options data

* CBOE SKEW Index: barchart.com/stocks/quotes/$SKEW

* PortfoliosLab: portfolioslab.com — ETF analytics (EEM, EWZ, FXI historical stats)

* MenthorQ: menthorq.com/guide/risk-reversal-and-skew — RR and SKEW guide

* Vol Vibes (Substack): February 2026 market overview — current vol regime data

*This is a living document. Update as strategy is refined through Step 2 (agent-assisted implementation). All parameter ranges are starting points — validate against historical backtests before capital deployment.*