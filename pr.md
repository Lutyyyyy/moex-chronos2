# MOEX × Chronos-2 — Project Brief for the Numeric/Math Team

> Audience note: this is written for a strong mathematician who is **new to both
> trading and ML**. Trading and AI concepts are explained from first principles;
> where it helps, the idea is stated in math terms you already own
> (expectations, hypothesis tests, distribution forecasting).

---

## 0. The one-paragraph version

We are building an **automated trading bot** for the Moscow Exchange (MOEX). The
end goal is a system that turns a starting capital into a positive return —
target **30%+ annualized** — at controlled risk. The bot is a pipeline of
specialized agents. At its numeric core sits a **forecasting model** that, given
recent price history of many instruments, predicts the near-future distribution
of returns. Around that core, **LLM agents** turn forecasts into trade
decisions, manage risk, read the news, and re-tune the model to the current
market. This document explains *why* we chose the components we did, *what
experiment* is running right now to validate the forecasting core (**Chronos-2**),
and *how we decide* whether it is working.

---

## 1. The problem: why this is hard, and where the opportunity is

A traded price is, to first approximation, a near-martingale: tomorrow's best
guess for the price is today's price. If it were *exactly* a martingale, no
strategy could beat the cost of trading and we should all buy index funds. The
whole game is finding **small, exploitable deviations from the martingale** —
"market inefficiencies" — that survive transaction costs.

Two regimes of this game:

- **High-frequency trading (HFT).** Inefficiencies live at the millisecond /
  microsecond scale. Capturing them is a **latency and infrastructure race** —
  co-located servers, FPGAs, direct exchange feeds. We cannot and do not want to
  compete here: the hardware and concurrency requirements are prohibitive, and
  the edge is gone before a Python process even wakes up.

- **Classical algo-trading (technical indicators, factor models).** Rules like
  "RSI < 30 → buy" are public knowledge. Anything expressible as a simple,
  static formula has been arbitraged down to noise by thousands of participants.
  Pure classical algotrading on a liquid market like MOEX blue chips rarely finds
  a durable edge anymore.

**Our bet (the thesis of the whole project):** the exploitable inefficiencies
today are **statistical and non-stationary** — they appear in the *current*
market regime (last weeks/months), in the *cross-correlation structure* between
instruments, and in *covariate-driven* moves (oil, FX, the index) — and they
**drift**, so a static model decays. A model that (a) reasons over *many
correlated series at once* and (b) can be *re-tuned to the recent regime* is the
natural tool to harvest them. That model is **Chronos-2**.

> Math framing of "is there an edge?" — see §6. In short: with round-trip cost
> `c` and a typical move size `m`, a directional call needs hit-probability
> `p > 0.5 + c/(2m)` to have positive expected value. Everything we measure is
> ultimately aimed at estimating that `p` and proving it clears the bar.

---

## 2. The two numeric models: CatBoost / boosting and Chronos-2

The bot's "numeric analyst" layer has **two complementary kinds of model**. They
answer different questions, so we keep both and let the decision layer combine
them.

### 2A. Gradient boosting (CatBoost / LightGBM) — a *classifier*

- **What it is:** a gradient-boosted decision-tree ensemble. You hand it a wide
  table of hand-engineered **features** per instrument per timestamp (technical
  indicators, volume stats, calendar, lagged returns, …) and a binary label
  ("did price rise N candles later?"). It learns `P(up | features)`.
- **Output:** a single scalar `proba_up ∈ [0,1]` — the probability the price is
  higher after the model's horizon (production model: ~9 hours = 3×3h candles).
- **Strengths:** fast, robust, trivial to retrain, excellent on tabular
  features, gives a calibrated-ish probability that is easy to threshold.
- **Weaknesses:** it does **not** model the *shape* or *magnitude* of the move,
  only direction-probability. It needs features to be engineered by hand, treats
  each instrument largely independently, and has no native notion of
  "uncertainty band" on the price path.
- **Status:** already trained and wired into the production bot
  (`packages/boosting`, artifact `model.pkl`). It is the workhorse direction
  signal *today*. CatBoost vs LightGBM is an implementation detail — same family.

### 2B. Chronos-2 — a *probabilistic forecaster*

- **What it is:** a pretrained **time-series foundation model** (a transformer)
  from Amazon. Given the recent trajectory of a set of series, it outputs a full
  **quantile forecast** of each series' next H steps — i.e. a predicted
  *distribution* of the future path, not just a point or a label.
- **Output:** for each instrument and each future bar `h`, a set of quantiles
  (q10, q50, q90, …) of the future log-return. That gives us **direction,
  magnitude, and uncertainty** in one object.
- **Strengths:** models many correlated series jointly; ingests covariates;
  works **zero-shot** (no training required to get a forecast); gives genuine
  uncertainty bands we can size positions against.
- **Weaknesses:** heavier than a tree; zero-shot it knows nothing
  MOEX-specific; needs validation before we trust it with money.

**Why keep both?** They disagree in informative ways. The boosting model is a
sharp, cheap *direction* vote. Chronos-2 adds *magnitude + confidence + cross-asset
structure*. In the production decision layer the two are blended into a hybrid
score, with a **bonus when they agree and a penalty when they disagree** — a
disagreement is a signal to stand down. (See architecture, §4.)

```
                    proba_up (scalar)            quantile paths (distribution)
                         ▲                                 ▲
        ┌────────────────┴───────────┐     ┌───────────────┴────────────────┐
        │  Boosting (CatBoost/LGBM)  │     │           Chronos-2             │
        │  P(up | engineered feats)  │     │  q10..q90 of next-H log-returns │
        │  fast · per-asset · direction│   │  joint · covariates · magnitude │
        └────────────────────────────┘     └─────────────────────────────────┘
                         └──────────────┬──────────────────┘
                                        ▼
                          hybrid score  (agreement bonus,
                                         disagreement penalty)
```

---

## 3. Why Chronos-2 specifically (the model choice)

Chronos-2 is already chosen; here is the justification a skeptic should accept.

### 3.1 What it is and how it works (the math-friendly version)

- It is a **pretrained foundation model for forecasting**: trained once, on huge
  amounts of (largely synthetic) time series, then used *as is* — "zero-shot" —
  on new series it has never seen. Analogous to how an LLM is pretrained then
  prompted, here the "prompt" is your recent price history (the *context*) and
  the model "completes" the future.
- Architecture: a transformer stack that **alternates two attention axes**
  (Chronos-2 paper, Fig. 1):
  - **Time attention** — aggregates information *along the time axis* within one
    series (the usual sequence modeling).
  - **Group attention** — aggregates information *across series within a group*
    at each time index. A "group" is a flexible bag of related series: the
    variates of a multivariate series, a set of correlated instruments, or a
    **target together with its covariates**.
- This **group attention** is the key feature for us. It lets the model do
  *in-context learning* across instruments and covariates **without retraining**:
  it infers, on the fly, how SBER, GAZP, the IMOEX index, Brent and USD/RUB move
  together, and uses that structure to sharpen each forecast. It scales as `O(V)`
  in the number of variates `V`, not `O(V²)` — so adding covariates stays cheap.
- Output is **quantile**: the model is trained to emit calibrated quantiles of
  the future, i.e. a predictive distribution, which is exactly what we need for
  risk-aware position sizing.

### 3.2 Proven results (so we are not betting on a press release)

From the **Chronos-2 technical report** (Ansari, Shchur, Küken et al., 2025):

- **Paper:** *Chronos-2: From Univariate to Universal Forecasting*,
  arXiv:**2510.15821** (local copy: `2510.15821v1.pdf`).
- **Code/weights:** `github.com/amazon-science/chronos-forecasting`
  (HuggingFace `amazon/chronos-2`).
- **Headline claims (paper's own benchmarks):** state-of-the-art across three
  comprehensive suites — **fev-bench**, **GIFT-Eval**, and **Chronos Benchmark
  II**. On *fev-bench* (which stresses multivariate and covariate-informed
  tasks) it improves substantially over prior models, and on **covariate-informed
  tasks it beats baselines by a wide margin** — the single most relevant axis
  for us, since covariates (oil/FX/index) are our hypothesized edge.
- **Capability matrix:** it is the only model in the paper's comparison table
  ticking *all* of {univariate, multivariate, past-only covariates, known-future
  covariates, categorical covariates, cross-learning} at `O(V)` memory.
- **Efficiency:** ~**300 time series/second on a single mid-range GPU (A10G)** —
  cheap enough to run a 12–30 instrument universe on a Colab T4 in production.

> Caveat we state honestly: these benchmarks are *general* forecasting, **not
> financial**. Financial returns are near-unpredictable by design. So strong
> benchmark numbers are *necessary encouragement, not proof*. That is precisely
> why we run our own MOEX experiment (§5) before trusting it.

### 3.3 What we intend to *leverage* — where to look, what to feed it

The whole reason to pick Chronos-2 over a univariate model is to **exploit
structure that a single-series model cannot see**. Concretely:

1. **Cross-asset group attention.** Feed the whole liquid universe as one group
   so the model uses, e.g., oil-sector co-movement and lead/lag between names.
2. **Covariates as same-group series** (this is the big lever, and where the
   paper's largest gains are):
   - *Past-only covariates*: index returns (IMOEX + sector indices), commodity
     returns (Brent, Gold), FX (USD/RUB), per-instrument volume change.
   - *Known-future covariates* (leakage-safe — we know them in advance):
     calendar features — hour-of-day, day-of-week, session-open flag.
   - *Price-**level** covariates* (a deliberate extension): exporter margins are
     ~linear in the Brent **level**, and USD/RUB **level** is a
     sanctions/capital-flow regime proxy — information a short window of
     *returns* cannot recover. Encoded as `log(price)` / rolling z-score (never
     raw price, which Chronos's per-series scaling would center out).
3. **Where the inefficiency should appear:** short horizons and the first 2–3
   predicted bars, intraday, in the cross-correlation and covariate channels,
   in the *recent* regime. The experiment is designed to look exactly there.

---

## 4. General architecture — Chronos-2 as the forecast engine, LLMs as the operators

The trading system (production repo `team_repo/team-40`) is a **multi-agent
pipeline**. The numeric models *forecast*; the LLMs *decide, validate, and
supervise*. Division of labor:

```
   30 MOEX blue chips
          │
   ┌──────▼───────┐  Layer 1 — SCREENER (cheap classical filter)
   │ RSI/MACD/Vol │  narrow ~30 → ~7–20 candidates worth deep analysis
   └──────┬───────┘
          │
   ┌──────▼────────────────────────────────────────────────┐
   │ Layer 2 — PER-ASSET ANALYSTS (run in parallel)         │
   │  • Numeric:  Chronos-2 forecast  +  Boosting proba_up  │
   │  • Semantic: LLM news/Telegram summary per company     │
   │  • Macro:    LLM on CBR rate / sanctions / oil / geo   │
   └──────┬─────────────────────────────────────────────────┘
          │
   ┌──────▼───────┐  Layer 3 — JUDGE (LLM, two passes)
   │ LLM Pass-1   │   per-ticker: action ∈ {long, short, skip}, confidence 0..10
   │ LLM Pass-2   │   portfolio review: re-rank by relative strength + amplitude
   └──────┬───────┘   hybrid score = f(LLM confidence, ML signal, agreement)
          │
   ┌──────▼───────┐  Layer 4 — ORDER FORMATION
   │ size ∝ score │   position size ∝ confidence; per-position & short limits
   └──────┬───────┘
          │  MOEX / ArenaGo API
   ┌──────▼───────┐  Layer 5 — POSITION MONITORING (parallel loops)
   │ risk watcher │   TP / SL every 2 min; time-based profit-take; reversal check
   │ time checker │   on Chronos forecast flip → re-evaluate position
   └──────────────┘
```

Mapping to the roles the guidelines call out:

- **Chronos-2 = the forecast machine.** It forecasts the near-future **return
  distribution** per instrument (direction + magnitude + quantile band). *What we
  forecast:* next-H log-returns, primary horizons h ∈ {2,3,5} bars. *Levels of
  assurance:* the quantile spread *is* the confidence — a tight band around a
  same-sign q10/q90 is a high-assurance call; a band straddling zero is a "skip".
- **LLM = trade-strategy executor.** Turns the numeric forecast + news + macro
  into an actual `{action, direction, confidence, holding_period}` decision, and
  builds the order (entry, stop, size).
- **LLM = forecast validator.** Cross-checks the numeric signal against news and
  macro context; the hybrid score *penalizes* a numeric signal the LLM finds
  contradicted, and *boosts* one it confirms. Disagreement → stand down.
- **LLM = "re-tune to current market" supervisor.** Periodically triggers /
  oversees re-fitting Chronos to the recent regime (this is **Path B**, §5–§7)
  and adjusts which signals are trusted as the regime shifts.
- **Separate LLM = news / risk-management agent.** A dedicated agent parses
  news, Telegram, and macro feeds and emits risk flags that can veto or shrink a
  position independently of the price model.

### 4.1 Confidence vs commissions — what probability is "enough"?

This is the quantitative gate the whole bot lives or dies by, in language you
will like. For a single directional trade with symmetric expected move `m`
(in return units) and round-trip cost `c`:

```
   EV  =  p · (+m)  +  (1 − p) · (−m)  −  c
       =  (2p − 1) · m  −  c
   EV > 0   ⇔   p  >  ½  +  c / (2m)
```

Production numbers: commission `0.05%` per side ⇒ `c ≈ 0.10%` round-trip; the
risk watcher's take-profit is `m ≈ 1.42%`. So the **break-even hit-rate** is

```
   p*  ≈  0.5  +  0.0010 / (2 · 0.0142)  ≈  0.5 + 0.035  =  0.535.
```

→ A directional model needs **~53.5% directional accuracy to merely cover costs**,
and meaningfully more to clear slippage and produce 30%+ annualized. This is
*exactly* why the experiment's success thresholds (§5) sit at DA ≥ 0.53–0.56:
they are the cost-of-trading line, not arbitrary. Chronos's quantile output also
lets us *only trade when the predicted edge `(2p−1)·m` exceeds `c` with margin* —
i.e. trade selectively on high-assurance forecasts, which raises realized `p`
above the unconditional DA.

---

## 5. The current experiment — validating Chronos-2 as a forecaster

This is the work happening **now**, before Chronos is trusted with capital. It
is a **descriptive significance study**, not yet a trading backtest: we are
asking, with statistics rather than vibes, *"does Chronos-2 predict MOEX returns
better than chance and better than naive baselines?"*

**Master plan:** [`exp_plan.md`](exp_plan.md). **Design decisions:**
[`wiki.md`](wiki.md). **Live status:** [`current_state.md`](current_state.md).
**Code:** [`basic_cells.ipynb`](basic_cells.ipynb) (reusable library) driven by
[`runner.ipynb`](runner.ipynb) over per-stage [`configs/*.yaml`](configs/).

### 5.1 Setup

- **Universe:** 12 liquid MOEX blue chips (SBER, GAZP, LKOH, ROSN, NVTK, TATN,
  GMKN, PLZL, MAGN, NLMK, MOEX, VTBR), grouped by economic linkage.
- **Data:** MOEX ISS API → local Parquet cache; intervals 15m / 60m / 1d; range
  2021-01-01 → 2026-04-30 (spans the 2022 dislocation → useful for regime tests).
- **Target:** close-to-close **log-returns**.
- **Covariates:** index/sector/commodity/FX returns + volume + calendar (and the
  price-level extension); leakage rule: only calendar features are known-future.
- **Evaluation:** **walk-forward** — context window → forecast horizon → shift →
  repeat — never a single split, so we get hundreds of out-of-sample forecasts.
- **This is "Path A":** Chronos **zero-shot**, weights straight from the box. No
  fine-tuning yet — we first measure what the model gives for free.

### 5.2 The two questions, and how each is scored (the statistics)

For every (stage, interval, ticker, horizon) cell:

1. **Direction.** Is directional accuracy (DA) above 0.5 by enough margin, over
   enough windows, to reject "fair coin"? → DA + **binomial p-value** + **95%
   Wilson CI** per (ticker, horizon); aggregated as a **bootstrap median DA**.
   Multiple-testing across (ticker × horizon) controlled by **Benjamini–Hochberg**
   (and Bonferroni for the single headline claim).
2. **Amplitude.** Does the *magnitude* of the predicted return co-move with the
   realized one? → **Pearson & Spearman** corr(pred, true), the calibration ratio
   `|pred| / |true|`, and **quantile coverage** (does the q10–q90 band actually
   contain ~80% of outcomes?).

**Baselines, computed on the identical windows** — Chronos must beat these or it
is adding nothing: **B0** zero-return, **B1** last-return persistence, **B2**
5-bar momentum, **B3** per-ticker AR(1). A result is "interesting" only if it
beats B0–B2 on DA *and* improves correlation or coverage.

**Power floor:** ≥ ~400 forecasts to detect a +5pp DA edge at p<0.05 → minimum
windows per cell: 1d ≥ 100, 60m ≥ 300, 15m ≥ 400.

### 5.3 Stages 0–7 (each stage = one config + one scratchpad of results)

| Stage | Interval | What it answers | Success criterion (the bar) |
|------|---------|-----------------|------------------------------|
| **0 smoke** | 1d | Pipeline/cache/output schema run end-to-end | DA ∈ [0.40,0.60] (sanity, no claim) |
| **1 daily** | 1d | Full daily study; context grid {64,128,250,500} | ≥1 (ticker,h) cell DA ≥ 0.56 @ p<0.05 **and** beats B1 on aggregate |
| **2 60m** | 60m | Intraday signal; ctx {300,600,1000} | aggregate DA(h=2) ≥ 0.53, bootstrap CI lower bound > 0.50 |
| **3 15m** | 15m | High-freq; "first 2–3 bars predictive?" effect | DA at h∈{2,3} statistically ≠ 0.5 (bootstrap CI) |
| **4 sector** | best | Does intra-sector group attention beat mixed grouping? | ≥1 sector +1.5pp DA over its mixed-universe baseline |
| **5 covariates** | best | Ablation: none / calendar / market / full / +price-levels | full beats none by ≥1pp DA; price-levels +0.5pp to be kept |
| **6 stability** | best | Hold across regimes (2021-H1 … 2026-YTD)? | ≥4 of 7 sub-windows DA>0.5 @ p<0.10; worst ≥ 0.46 |
| **7 hold-out** | best | Headline table on locked 2025-11-01…2026-04-30 | replicates stages 1–3 magnitudes within CI |

Every stage emits to `runs/<stage_id>/`: a config snapshot, raw predictions,
`metrics.csv` + `metrics_baselines.csv`, `summary.json`, and plots (DA heatmap,
DA−baseline bars, correlation histogram, amplitude calibration, coverage bars,
example forecasts). **Where the colleague should look:** `exp_plan.md` §3 for the
full per-stage spec; the per-stage `scratchpads/stage_X_scratch_pad.md` for the
actual numbers and the go/no-go note after each run.

> **Honest status (2026-06-02):** the framework, configs, code library and FORTS
> futures resolver are **built and validated**, but `runs/` is still **empty** —
> the stages have not yet been executed on the GPU. We are at the
> "press go on Stage 0/1 in Colab" point. So we currently have *no* Chronos MOEX
> result numbers yet; that is the immediate next action.

---

## 6. Part B — fine-tuning Chronos to the current market (the planned continuation)

**This is the heart of the trading thesis** and runs *only if Part A shows
zero-shot Chronos has at least a pulse of signal.* The idea: the exploitable
inefficiency lives in the **recent regime**, so we **fine-tune Chronos on the
last ~3 months** of MOEX data to bend the general model toward *current* market
microstructure — catching the inefficiency that static/classical methods miss.

### 6.1 Mechanism

Path B reuses Path A's cache and panel build verbatim. A single config flag
(`path_b.enabled: true`) flips the runner from zero-shot `predict_df` to an
**AutoGluon `TimeSeriesPredictor.fit(...)`** with
`hyperparameters={"Chronos": {model_path: "amazon/chronos-2", fine_tune: true, …}}`.
The walk-forward harness is unchanged, so **Path A vs Path B is an
apples-to-apples comparison** on identical windows.

### 6.2 Training periods & how datasets are formed (the "characteristic-value" approach)

- **Recency-weighted windows.** Primary fine-tune set = **last ~3 months**
  (the live-regime hypothesis). Build *multiple* training datasets sliced by
  *characteristic regime values*, not just by calendar, so the model is tuned to
  conditions resembling *now*:
  - by **volatility regime** (e.g. IMOEX realized-vol terciles),
  - by **trend vs range** (sign-consistency of recent returns, the
    `trendiness`/amplitude statistic the production bot already computes),
  - by **macro level buckets** (Brent / USD/RUB level z-scores).
- **Walk-forward re-fit, chunked.** Re-fit per outer fold over `N_FOLDS` outer
  windows (chunked to keep T4 GPU time bounded), so the "current model" always
  reflects data just before the window it predicts — the production-realistic
  setup and the basis for the LLM "re-tune supervisor" loop.
- **No leakage, ever:** the leakage rule (only calendar is known-future) and the
  Stage-7 hard metric-mask carry into Path B unchanged.

### 6.3 Hyperparameter approach

- **Coarse first, on the proxy metric.** Tune the *few* knobs that matter most
  for a foundation-model fine-tune — context length, number of fine-tune steps /
  early-stop, learning rate, and the covariate set — using **DA and quantile
  loss on walk-forward validation folds**, not on the final hold-out.
- **Small grid, big steps.** Reuse the Path A context grids ({64…500} daily,
  {300…1000} 60m) as the search axis; pick by aggregate DA + CI, then confirm.
- **Regularize toward the base model.** Few steps / low LR — the goal is to
  *nudge* the pretrained weights to the recent regime, not to overfit 3 months of
  noisy returns. Over-tuning here is the primary failure mode; the regime
  sub-window test (Stage 6 logic) is the guard against it.
- **Decision metric:** statistically significant **DA / quantile-loss lift of
  Path B over Path A** on the same (ticker, horizon) cells. No lift ⇒ keep
  zero-shot (simpler, cheaper). Lift ⇒ Path B becomes the production forecaster.

---

## 7. Key decision points — when, where, and what to look at

These are the explicit **go / no-go gates**. At each, *where to look* is named so
the colleague can audit the call.

| # | When | Where to look | GO if… | NO-GO / pivot if… |
|---|------|---------------|--------|-------------------|
| **G0** | After Stage 0 | `runs/stage_0_smoke/`, resolver WARN lines | DA∈[0.40,0.60], schema clean, no futures-stitch WARN | sign bug (DA≈0 or 1) or WARN spam → fix `basic_cells.ipynb` before any claim |
| **G1** | After Stage 1 (daily) | `metrics.csv`, `da_heatmap.png`, scratchpad | ≥1 cell DA≥0.56 @ p<0.05 (post-BH) **and** beats B1 aggregate | no cell clears coin-flip vs baselines → daily horizon is dead, lean intraday |
| **G2** | After Stages 2–3 (intraday) | aggregate DA + bootstrap CI at h∈{2,3} | DA(h=2)≥0.53, CI lower bound >0.50 | CI straddles 0.5 at every horizon → zero-shot edge unproven |
| **G3** | After Stage 5 (covariates) | Δ DA vs no-covariate baseline | covariates add ≥1pp DA (esp. market/price-level) | covariates add nothing → the multivariate thesis is weak; reconsider model choice |
| **G4 ★** | After Stage 6 (stability) | per-regime DA blocks | ≥4/7 windows DA>0.5 @ p<0.10, worst ≥0.46 | signal concentrated in one lucky window → **do not trade**; it won't survive live |
| **G5** | After Stage 7 (hold-out) | the locked headline table | replicates stage 1–3 within CI on untouched 6 months | hold-out collapses → earlier results were overfit; back to drawing board |
| **G6** | After Path B fine-tune | Path A vs Path B per-cell DA / q-loss | statistically significant lift over zero-shot | no lift → ship zero-shot; fine-tune not worth the cost/risk |
| **G7** | Pre-capital | trading backtest + paper trading | edge survives commissions (p>~0.535) & slippage, Sharpe/DD acceptable | costs eat the edge → tighten selectivity or shelve |

**The single most important gate is G4 (regime stability).** A model that looks
brilliant on the full sample but only because of one anomalous quarter is the
classic way to lose money. We weight that test the heaviest.

---

## 8. TL;DR for the new colleague

1. **Goal:** an auto-trading bot for MOEX, 30%+ annualized, risk-managed by LLMs,
   with **Chronos-2** as the forecasting brain.
2. **Why these models:** boosting (CatBoost/LightGBM) gives a fast, calibrated
   *direction probability*; **Chronos-2** adds joint, covariate-aware,
   *distributional* forecasts (direction + magnitude + uncertainty). Both feed an
   LLM decision layer; agreement is rewarded, disagreement vetoes.
3. **Why Chronos-2:** its **group-attention** mechanism does zero-shot in-context
   learning across instruments and covariates and is **SOTA on covariate-informed
   benchmarks** (arXiv:2510.15821) — exactly the channel where we expect MOEX's
   exploitable inefficiency to live. Runs cheap (~300 series/s on one GPU).
4. **The math gate:** edge exists iff hit-rate `p > ½ + c/(2m)`; with our costs
   that's **~53.5% DA** to break even — which is why our success thresholds sit
   at DA 0.53–0.56.
5. **Part A (now):** zero-shot Chronos on MOEX, a 7-stage walk-forward
   significance study (DA + binomial/Wilson/bootstrap, amplitude, coverage,
   beat-the-baseline). *Framework is built; stages not yet run.*
6. **Part B (next, if A passes):** AutoGluon fine-tune of Chronos on the **last
   ~3 months**, datasets sliced by regime characteristics (vol / trend / macro
   level), light hyperparameters to avoid overfit; ship it only if it beats
   zero-shot with statistical significance.
7. **Where to read more:** `exp_plan.md` (plan), `wiki.md` (design),
   `current_state.md` (status), `2510.15821v1.pdf` (the model paper),
   `team_repo/team-40/SYSTEM_OVERVIEW.md` (the production bot).
</content>
</invoke>
