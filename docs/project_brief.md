# MOEX × Chronos-2 — Project Brief & Proposed Agent Architecture

> Audience note: this is written for a strong mathematician who is **new to both
> trading and ML**. Trading and AI concepts are explained from first principles;
> where it helps, the idea is stated in math terms you already own
> (expectations, hypothesis tests, distribution forecasting, fractional Kelly).
>
> Scope note: §1–§3 and §6–§8 describe the goal, the model, and the validation
> experiment. **§4–§5 are a *design proposal*** — how I would architect the LLM
> agent layer that wraps Chronos-2 into a full trading system. It is written
> **assuming the Chronos validation experiment (§6) succeeds**, i.e. that
> Chronos-2 has a measurable, cost-clearing edge on MOEX. Nothing here is built
> yet; this is the blueprint.

---

## 0. The one-paragraph version

We are building an **automated trading bot** for the Moscow Exchange (MOEX). The
end goal is a system that turns a starting capital into a positive return —
target **30%+ annualized** — at controlled risk. At its numeric core sits a
single **forecasting model, Chronos-2**, which, given the recent price history of
many instruments plus covariates (oil, FX, the index), predicts the near-future
**distribution** of each instrument's returns. Around that core we wrap a layer
of **LLM agents**: one turns forecasts into a trading strategy, one validates the
forecasts, one manages portfolio risk, one reads the news, and one periodically
**re-tunes** Chronos to the current market. This document explains *why* Chronos-2,
*how the experiment validates it*, and — the main contribution — *how I would
design the agent layer* that turns a good forecaster into a profitable bot.

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

> Math framing of "is there an edge?" — see §4.4. In short: with round-trip cost
> `c` and a typical move size `m`, a directional call needs hit-probability
> `p > 0.5 + c/(2m)` to have positive expected value. Everything we measure is
> ultimately aimed at estimating that `p` and proving it clears the bar.

---

## 2. The numeric core: Chronos-2 as a probabilistic forecaster

Deliberate design choice: **Chronos-2 is the *sole* numeric engine.** We do not
maintain a separate hand-engineered classifier. The reason is that a single
distributional forecaster gives us everything a classifier would (a direction
probability is recoverable from the forecast distribution) **plus** magnitude and
uncertainty, **plus** cross-asset structure — in one object the agent layer can
reason over uniformly.

- **What it is:** a pretrained **time-series foundation model** (a transformer)
  from Amazon. Given the recent trajectory of a set of series, it outputs a full
  **quantile forecast** of each series' next H steps — i.e. a predicted
  *distribution* of the future path, not just a point or a label.
- **Output (the "forecast object"):** for each instrument and each future bar
  `h`, a set of quantiles (q10, q50, q90, …) of the future log-return. From this
  one object we derive **direction** (sign of q50), **magnitude** (q50 size),
  **uncertainty** (band width q90−q10), and an **implied edge** the agents act on.
- **Strengths:** models many correlated series jointly; ingests covariates;
  works **zero-shot** (no training required to get a forecast); gives genuine
  uncertainty bands we can size positions against.
- **Weaknesses we design around:** heavier than a tree; zero-shot it knows
  nothing MOEX-specific (→ the §6 validation and §7 up-tuning address this).

```
                                Chronos-2  →  per-instrument quantile path
                                              ┌───────────────────────────┐
   recent prices (12–30 names) ──┐            │  h=1  h=2  h=3 ...  h=5    │
   index/sector returns       ───┼──► group ──┤ q90  ▁▂▃▄▅                 │
   Brent / Gold / USD-RUB     ───┤   attention│ q50  ▁▁▂▂▃   ← direction   │
   volume, calendar (future)  ───┘            │ q10  ▁▁▁▂▂   ← band=conf.  │
                                              └───────────────────────────┘
                                          direction · magnitude · uncertainty
                                                  (one object per name)
```

---

## 3. Why Chronos-2 specifically (the model choice)

Chronos-2 is chosen; here is the justification a skeptic should accept.

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
> why we run our own MOEX experiment (§6) before trusting it.

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

## 4. Proposed architecture — how I would wrap Chronos-2 in an LLM agent layer

**This section is my design proposal.** The principle: **Chronos-2 forecasts;
LLM agents reason, decide, guard, and adapt.** A forecaster alone is not a
strategy — it does not know how much to bet, when to stand down, what the news
says, or that its edge has decayed. Those are *judgment under uncertainty* tasks,
which is exactly where an LLM with structured inputs and hard guardrails is the
right tool. I split that judgment into **five specialized agents** plus a thin
deterministic spine, so each agent has one job, a typed input, and a typed
output that the next stage can audit.

### 4.1 The agent roster (one job each)

| # | Agent | Type | One-line job |
|---|-------|------|--------------|
| A0 | **Universe Gate** | deterministic | Keep the Chronos group to the ~12–30 liquid names worth forecasting (liquidity + data-quality filter). No alpha logic — just tractability. |
| A1 | **Strategy Agent** | LLM | Turn each Chronos forecast object into a *trade thesis*: direction, entry, target, stop, holding horizon, conviction. The "trade-strategy executor". |
| A2 | **Forecast Validator** | LLM + checks | Sanity-gate the forecast: degenerate/flat/NaN detection, calibration plausibility, agreement with recent realised path. Can downgrade or kill a thesis. |
| A3 | **News / Macro Risk Agent** | LLM | Independently of price, read news/Telegram/macro; emit per-name **risk flags** and a market-**regime label**. Can veto or shrink, never *create* a position. |
| A4 | **Risk-Management Agent** | LLM + hard limits | Portfolio-level: size each position from the Chronos quantiles, enforce exposure/correlation/drawdown limits, manage live TP/SL. The deterministic limits are inviolable; the LLM only chooses *within* them. |
| A5 | **Up-Tuning Supervisor** | LLM + monitors | Watch live forecast quality; detect decay/regime shift; trigger and approve periodic re-fine-tuning of Chronos (§7). Champion/challenger gatekeeper. |

A thin **Orchestrator** (deterministic, e.g. a LangGraph state machine) sequences
A0→A1→A2→A3→A4, calls **Execution** (deterministic broker adapter), and runs A4's
risk loop and A5's supervisor loop as independent timers. Everything shares one
lock so no two loops touch the broker at once.

### 4.2 The decision pipeline (one cycle)

```
            ┌──────────────┐   universe of ~12–30 names
            │ A0 Universe  │
            │ Gate (det.)  │
            └──────┬───────┘
                   ▼
        ┌─────────────────────┐   one batched call, whole group
        │   CHRONOS-2 FORECAST │   → forecast object per name (q10..q90 × h)
        └──────────┬──────────┘
                   ▼
        ┌─────────────────────┐
        │ A1 Strategy Agent   │   per-name thesis:
        │ (LLM, per-name)     │   {dir, entry, target=q50, stop, H, conviction}
        └──────────┬──────────┘
                   ▼
        ┌─────────────────────┐   kill degenerate / implausible forecasts,
        │ A2 Forecast Validator│  downgrade conviction on weak calibration
        └──────────┬──────────┘
                   ▼
        ┌─────────────────────┐   per-name risk flags + regime label;
        │ A3 News/Macro Agent │   veto or shrink (cannot flip direction)
        └──────────┬──────────┘
                   ▼
        ┌─────────────────────┐   size by edge/variance (frac-Kelly, capped),
        │ A4 Risk Manager     │   exposure & correlation limits, pick TOP-N
        │ (LLM + hard limits) │   → final weighted order list
        └──────────┬──────────┘
                   ▼
            ┌──────────────┐
            │  Execution   │  MOEX/broker API (margin-safe, idempotent)
            │  (det.)      │
            └──────────────┘
   ── parallel timers ───────────────────────────────────────────────
   A4 risk loop (minutes): live TP / SL / forecast-flip exit
   A5 supervisor (daily/weekly + triggered): forecast-quality watch → re-tune
```

**Why an LLM at A1/A3/A4 rather than a formula?** Because the inputs are
heterogeneous and contextual — a quantile path *plus* a news headline *plus* a
macro regime *plus* current portfolio state — and the decision ("is this edge
real enough, given everything, to risk capital, and how much?") is a judgment
the LLM can articulate and *log its reasoning for*, which is auditable. The hard
numeric guardrails (A4's limits, A2's calibration checks) keep the LLM from doing
anything reckless: the LLM proposes, the deterministic spine disposes.

### 4.3 From a Chronos quantile path to a trade — levels of assurance

The forecast object is the contract between Chronos and A1. I would standardize
the **assurance tiers** straight off the quantile band, so the whole system
speaks one language of confidence:

| Tier | Condition (on horizon-h return) | Meaning | A1 action |
|------|----------------------------------|---------|-----------|
| **High** | `sign(q10)=sign(q90)` (band entirely one side of 0) **and** `\|q50\| > k·c` | strong directional, low ambiguity | full-conviction thesis |
| **Medium** | `sign(q50)≠0`, band straddles 0 but `q50` edge `> c` | directional but uncertain | reduced conviction |
| **Skip** | band straddles 0 and `\|q50\| ≤ c` | no cost-clearing edge | no trade |

Here `c` is the round-trip cost and `k>1` a safety multiple (slippage buffer).
The point: **we only trade when the *whole forecast distribution*, not just its
mean, says the edge beats cost.** That selectivity is what turns a modest
average directional accuracy into a profitable subset of trades.

### 4.4 Confidence vs commissions — what probability is "enough"?

This is the quantitative gate the whole bot lives or dies by, in language you
will like. For a single directional trade with symmetric expected move `m`
(in return units) and round-trip cost `c`:

```
   EV  =  p · (+m)  +  (1 − p) · (−m)  −  c
       =  (2p − 1) · m  −  c
   EV > 0   ⇔   p  >  ½  +  c / (2m)
```

Illustrative numbers: commission `0.05%` per side ⇒ `c ≈ 0.10%` round-trip; a
target move `m ≈ 1.4%`. The **break-even hit-rate** is

```
   p*  ≈  0.5  +  0.0010 / (2 · 0.014)  ≈  0.5 + 0.036  =  0.536.
```

→ A directional model needs **~53.6% directional accuracy to merely cover costs**,
and meaningfully more to clear slippage and produce 30%+ annualized. This is
*exactly* why the experiment's success thresholds (§6) sit at DA ≥ 0.53–0.56:
they are the cost-of-trading line, not arbitrary. Because Chronos gives a full
distribution, A1 trades *only* the high-assurance subset (§4.3), where realised
`p` is well above the unconditional DA — that is how a fractional edge becomes
money.

### 4.5 Position sizing (how A4 turns the distribution into a bet size)

From a name's horizon-h forecast, estimate the return mean and spread:
`μ ≈ q50`, `σ ≈ (q90 − q10)/2.563` (Gaussian-equivalent). Net of cost the
expected edge is `μ_net = μ − c`. A **fractional-Kelly** weight, capped, is a
clean, defensible rule:

```
   f*  =  clip(  λ · μ_net / σ²ʼ ,  0 ,  w_max )
```

with `λ ∈ (0,1]` a risk-aversion fraction (e.g. 0.25–0.5 of full Kelly) and
`w_max` a hard per-name cap (e.g. 10–15% of capital). Properties we want and get:
sizing **grows with edge, shrinks with uncertainty**, and is bounded. A4 then
applies *portfolio* constraints on top: total gross exposure ≤ limit, no stacking
of highly correlated longs (Chronos's own cross-asset structure flags the
correlation), max short count, and a drawdown circuit-breaker that flattens and
pauses new entries if equity drops past a threshold.

### 4.6 The risk loop and exits (A4, continuous)

Independently of the main cycle, A4 runs a fast loop (every couple of minutes):
- **Take-profit / stop-loss** on live price vs entry (levels derived from the
  forecast band, not fixed ad-hoc %s).
- **Forecast-flip exit:** re-query Chronos; if the sign of `q50` for the held
  horizon flips against the position with conviction, exit early — the thesis is
  dead. This is the direct payoff of having a *forecaster* rather than a static
  rule.
- **Time stop:** if the forecast horizon `H` has elapsed and the move did not
  materialise, close — the edge had a shelf life.

### 4.7 Why these specific five agents (ablation-minded design)

Each agent earns its place by removing a distinct failure mode. The design is
built so each can be **ablation-tested** (run the system with the agent off; if
metrics don't drop, the agent is dead weight):

- No A2 → a degenerate Chronos forecast (flat line, NaN, miscalibrated band)
  silently drives a real trade.
- No A3 → the bot buys into an earnings disaster / sanction headline the price
  model cannot see.
- No A4 → correct direction calls still blow up via oversizing or correlated
  concentration.
- No A5 → the edge decays as the regime drifts and nobody notices until the P&L
  curve rolls over.

---

## 5. Orchestration, cadence, and observability (the operational design)

- **Cadence.** Forecast + decision cycle runs once per chosen bar interval (e.g.
  hourly intraday or per session). A4's risk loop runs every ~2 min. A5's
  supervisor runs daily for monitoring, weekly (or on trigger) for re-tuning.
- **Concurrency safety.** All broker-touching actions go through one async lock;
  watcher loops yield if the main cycle holds it. No races, ever.
- **Idempotent, margin-safe execution.** The Execution adapter retries on
  margin rejection by halving size, reconciles opposite tails before flipping a
  name, and guarantees full close on exit. (Deterministic, no LLM.)
- **Observability / tracing.** Every agent call logs its structured input,
  prompt, output, and token cost (e.g. via Langfuse-style tracing). We keep a
  per-cycle decision table: name, Chronos tier, A1 conviction, A3 flags, A4 size,
  final action. This is what makes the LLM layer **auditable** instead of a black
  box, and is the dataset for later confidence-calibration checks (does realised
  win-rate rise with A1 conviction?).
- **Graceful shutdown / hard deadline.** On stop signal or a configured
  liquidation time, the bot stops opening, flattens to flat, and exits.

> Honest engineering note: the LLM in the loop adds **latency and a failure
> surface** (timeouts, truncated JSON, hallucinated fields). The design mitigates
> this with strict typed outputs, partial-JSON recovery, and a deterministic
> fallback (if A1/A4 fail, fall back to "no new positions, hold existing under
> A4's hard rules"). The LLM is never on the critical path for *safety* — only
> for *alpha*.

---

## 6. Validating Chronos-2 as a forecaster (the experiment, assumed successful)

Before any of §4–§5 is worth building, Chronos must be shown to actually predict
MOEX returns. That validation is a **descriptive significance study** — asking,
with statistics rather than vibes, *"does Chronos-2 beat chance and beat naive
baselines?"* **For this brief we proceed on the assumption that it does** (the
gates in §8 fire green); here is what that study is and where to read it.

**Master plan:** [`exp_plan.md`](exp_plan.md). **Design decisions:**
[`wiki.md`](wiki.md). **Live status:** [`current_state.md`](current_state.md).
**Code:** [`basic_cells.ipynb`](../path_a/basic_cells.ipynb) driven by
[`runner.ipynb`](../path_a/runner.ipynb) over per-stage [`configs/*.yaml`](../path_a/configs/).

### 6.1 Setup

- **Universe:** 12 liquid MOEX blue chips (SBER, GAZP, LKOH, ROSN, NVTK, TATN,
  GMKN, PLZL, MAGN, NLMK, MOEX, VTBR), grouped by economic linkage.
- **Data:** MOEX ISS API → local Parquet cache; intervals 15m / 60m / 1d; range
  2021-01-01 → 2026-04-30 (spans the 2022 dislocation → useful for regime tests).
- **Target:** close-to-close **log-returns**.
- **Covariates:** index/sector/commodity/FX returns + volume + calendar (and the
  price-level extension); leakage rule: only calendar features are known-future.
- **Evaluation:** **walk-forward** — context → forecast horizon → shift → repeat
  — never a single split, so we get hundreds of out-of-sample forecasts.
- **"Path A":** Chronos **zero-shot**, weights straight from the box — measure
  what the model gives for free before any fine-tuning.

### 6.2 The two questions, and how each is scored (the statistics)

For every (stage, interval, ticker, horizon) cell:

1. **Direction.** Is directional accuracy (DA) above 0.5 by enough margin, over
   enough windows, to reject "fair coin"? → DA + **binomial p-value** + **95%
   Wilson CI**; aggregated as a **bootstrap median DA**. Multiple-testing across
   (ticker × horizon) controlled by **Benjamini–Hochberg** (Bonferroni for the
   single headline claim).
2. **Amplitude.** Does the *magnitude* of the predicted return co-move with the
   realized one? → **Pearson & Spearman** corr(pred, true), the calibration ratio
   `|pred| / |true|`, and **quantile coverage** (does the q10–q90 band actually
   contain ~80% of outcomes?). Coverage matters doubly here: §4.3/§4.5 *depend*
   on the band being honest.

**Baselines, on identical windows** — Chronos must beat these or it adds nothing:
**B0** zero, **B1** last-return persistence, **B2** 5-bar momentum, **B3** AR(1).
A result is "interesting" only if it beats B0–B2 on DA *and* improves correlation
or coverage. **Power floor:** ≥ ~400 forecasts for a +5pp DA edge at p<0.05.

### 6.3 Stages 0–7

| Stage | Interval | What it answers | Success criterion |
|------|---------|-----------------|-------------------|
| **0 smoke** | 1d | Pipeline/cache/schema end-to-end | DA ∈ [0.40,0.60] (sanity, no claim) |
| **1 daily** | 1d | Daily study; context grid {64,128,250,500} | ≥1 (ticker,h) cell DA ≥ 0.56 @ p<0.05 **and** beats B1 aggregate |
| **2 60m** | 60m | Intraday; ctx {300,600,1000} | aggregate DA(h=2) ≥ 0.53, bootstrap CI lower bound > 0.50 |
| **3 15m** | 15m | High-freq; "first 2–3 bars predictive?" | DA at h∈{2,3} statistically ≠ 0.5 |
| **4 sector** | best | Intra-sector group attention vs mixed? | ≥1 sector +1.5pp DA over its mixed baseline |
| **5 covariates** | best | Ablation: none/calendar/market/full/+levels | full beats none by ≥1pp DA; price-levels +0.5pp to keep |
| **6 stability** | best | Hold across regimes 2021-H1…2026-YTD? | ≥4 of 7 sub-windows DA>0.5 @ p<0.10; worst ≥ 0.46 |
| **7 hold-out** | best | Headline table, locked 2025-11-01…2026-04-30 | replicates stages 1–3 within CI |

Each stage emits to `runs/<stage_id>/`: config snapshot, raw predictions,
`metrics.csv` + `metrics_baselines.csv`, `summary.json`, plots. **Where to look:**
`exp_plan.md` §3 for the full spec; `scratchpads/stage_X_scratch_pad.md` for the
numbers and the go/no-go note after each run.

---

## 7. Periodic up-tuning — keeping Chronos on the current regime (Part B + Agent A5)

The thesis (§1) is that the edge lives in the **recent regime** and drifts. So
the system must **re-tune** — and that re-tuning must itself be governed by an
agent, not a cron job that blindly overwrites a working model. This is the
combination of **Part B (the fine-tuning mechanism)** and **Agent A5 (the
supervisor that decides when and whether to deploy it).**

### 7.1 The fine-tuning mechanism (Part B)

- Reuse Path A's cache and panel build verbatim; flip a config flag to fine-tune
  Chronos via **AutoGluon `TimeSeriesPredictor.fit(...)`** with
  `hyperparameters={"Chronos": {model_path: "amazon/chronos-2", fine_tune: true,…}}`.
  Walk-forward harness unchanged ⇒ **zero-shot vs fine-tuned is apples-to-apples.**
- **Training periods / dataset shaping ("characteristic-value" approach).**
  Primary fine-tune set = **last ~3 months** (live-regime hypothesis). Build
  several training datasets sliced by *regime characteristics*, not just by
  calendar, so the model is tuned to conditions resembling *now*:
  - by **volatility regime** (e.g. IMOEX realised-vol terciles),
  - by **trend vs range** (sign-consistency / trendiness of recent returns),
  - by **macro level buckets** (Brent / USD-RUB level z-scores).
- **Walk-forward re-fit, chunked** over `N_FOLDS` outer windows (bounded GPU
  time), so the "current model" always reflects data just before the window it
  predicts. No leakage: only calendar is known-future; hold-out mask preserved.
- **Hyperparameters — light touch.** Tune only the few knobs that matter
  (context length, fine-tune steps / early-stop, learning rate, covariate set) on
  **DA + quantile loss over validation folds**. Few steps / low LR: *nudge* the
  pretrained weights toward the recent regime, do **not** overfit 3 months of
  noisy returns. Over-tuning is the primary failure mode.

### 7.2 The supervisor that governs it (Agent A5)

A5 is what makes up-tuning safe and automatic:

- **Monitors live forecast quality** — rolling realised DA, quantile-coverage
  drift, calibration of A1 conviction vs outcomes. These are the early-warning
  signals of decay.
- **Triggers a re-tune** when monitors cross thresholds (coverage drifts off
  0.80, rolling DA sags toward 0.5, or a regime-label change from A3 persists).
- **Champion / challenger gate.** A freshly fine-tuned model is a *challenger*;
  it must **beat the live champion on a fresh walk-forward block with statistical
  significance** before it is promoted. If it doesn't, keep the champion. This
  prevents the classic "retrained on noise, deployed, lost money" spiral.
- **Logs every promotion decision** with the evidence, so the human team can
  audit why the production forecaster changed.

> In short: **Part B is the engine; A5 is the driver with a seatbelt.** Re-tuning
> only ships when it is *measurably* better, never on schedule alone.

---

## 8. Key decision points — when, where, and what to look at

Explicit **go / no-go gates**, with *where to look* named so the call is auditable.
(We assume G0–G7 pass; they remain the standing criteria the live system is held
to.)

| # | When | Where to look | GO if… | NO-GO / pivot if… |
|---|------|---------------|--------|-------------------|
| **G0** | After Stage 0 | `runs/stage_0_smoke/` | DA∈[0.40,0.60], schema clean | sign bug (DA≈0 or 1) → fix code first |
| **G1** | After Stage 1 (daily) | `metrics.csv`, `da_heatmap.png` | ≥1 cell DA≥0.56 @ p<0.05 **and** beats B1 | nothing clears coin-flip → lean intraday |
| **G2** | After Stages 2–3 (intraday) | aggregate DA + bootstrap CI, h∈{2,3} | DA(h=2)≥0.53, CI lower bound >0.50 | CI straddles 0.5 everywhere → edge unproven |
| **G3** | After Stage 5 (covariates) | Δ DA vs no-covariate baseline | covariates add ≥1pp DA | covariates add nothing → multivariate thesis weak |
| **G4 ★** | After Stage 6 (stability) | per-regime DA blocks | ≥4/7 windows DA>0.5 @ p<0.10, worst ≥0.46 | signal in one lucky window → **do not trade** |
| **G5** | After Stage 7 (hold-out) | the locked headline table | replicates stages 1–3 within CI | hold-out collapses → earlier results overfit |
| **G6** | After Part B fine-tune | champion vs challenger DA / q-loss | significant lift over zero-shot | no lift → ship zero-shot; A5 keeps champion |
| **G7** | Pre-capital | backtest of the *full agent stack* + paper trading | edge survives commissions (p>~0.536), slippage; Sharpe/DD OK; ablations (§4.7) justify each agent | costs eat the edge → tighten A1/A4 selectivity or shelve |

**The single most important gate is G4 (regime stability).** A model that looks
brilliant on the full sample only because of one anomalous quarter is the classic
way to lose money — and it is exactly the failure A5 (§7.2) exists to catch in
production. We weight that test the heaviest.

---

## 9. TL;DR for the new colleague

1. **Goal:** an auto-trading bot for MOEX, 30%+ annualized, with **Chronos-2** as
   the *sole* numeric forecasting brain and a layer of **LLM agents** doing the
   judgment around it.
2. **Why Chronos-2:** its **group-attention** mechanism does zero-shot in-context
   learning across instruments and covariates and is **SOTA on covariate-informed
   benchmarks** (arXiv:2510.15821) — exactly the channel where we expect MOEX's
   exploitable inefficiency to live. It outputs *distributions* (direction +
   magnitude + uncertainty), which is what risk-aware sizing needs.
3. **The math gate:** edge exists iff hit-rate `p > ½ + c/(2m)`; with our costs
   that's **~53.6% DA** to break even — why success thresholds sit at DA 0.53–0.56,
   and why we trade only the high-assurance tail of forecasts.
4. **Proposed agent layer (the design, §4–§5):** A1 Strategy (forecast→thesis),
   A2 Validator (kill bad forecasts), A3 News/Macro (independent veto), A4 Risk
   Manager (fractional-Kelly sizing + hard limits + live exits), A5 Up-Tuning
   Supervisor (decay monitor + champion/challenger re-tune). Chronos forecasts;
   agents decide; deterministic guardrails keep it safe; everything is logged and
   ablation-testable.
5. **Validation (§6, assumed passed):** zero-shot Chronos on MOEX, a 7-stage
   walk-forward significance study (DA + binomial/Wilson/bootstrap, amplitude,
   coverage, beat-the-baselines).
6. **Up-tuning (§7):** fine-tune Chronos on the last ~3 months, datasets sliced
   by regime characteristics, light hyperparameters; **deploy only via A5's
   champion/challenger gate** — better-with-significance or not at all.
7. **Where to read more:** `exp_plan.md` (plan), `wiki.md` (design),
   `current_state.md` (status), `2510.15821v1.pdf` (the model paper).
</content>
</invoke>
