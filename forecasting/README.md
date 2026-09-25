# Study 1: directional accuracy of zero-shot Chronos-2

Part of the MOEX × Chronos-2 project. The project-level synthesis is in [`../FINDINGS.md`](../FINDINGS.md); the
two follow-up studies live in [`alpha_experiment/`](alpha_experiment/README.md) (cross-sectional alpha) and
[`risk_experiment/`](risk_experiment/README.md) (risk). This folder's top level holds study 1: the runner
[`run.ipynb`](run.ipynb), the cell library [`lib.ipynb`](lib.ipynb) and one YAML per run in [`configs/`](configs/)
(71 configs).

**Headline result: a rigorous, replicated null.** Across ~10 independent axes (universe composition, time
resolution (daily / 1h / 10m), grouping (multivariate vs. univariate attention), price adjustment (raw vs.
dividend/split-adjusted), context length (35 / 100 / 250 bars), sector homogeneity, and cross-ticker lead-lag
structure), zero-shot Chronos-2 shows no directional edge on MOEX equity returns beyond chance. Every gate,
pre-registered before its run, failed. For a study like this the methodology *is* the contribution: the question
is whether the process would have caught a real edge if one had been there.

## Why this is a meaningful negative result, not just "it didn't work"

A negative result is only informative if the test had teeth:
- **Pre-registered gates.** ΔDA (directional accuracy) > 0 AND at least one Benjamini-Hochberg-significant cell
  favoring the tested arm AND that arm beating naive baselines, fixed before each run.
- **Multiple-comparisons correction** on every family that tests more than one (ticker, horizon) cell.
- **Discovery/confirmation splits** with verified non-overlapping dates for every hypothesis-generating step:
  candidates are never evaluated on the data used to find them.
- **Traps caught, not just a clean pipeline.** A spurious market-factor pattern in the lead-lag screen was found
  and fixed before confirmation, and the one BH-significant ticker the context sweep produced (UNAC) was sent to
  a fresh holdout and explained rather than reported (both below).

## Method

**Model.** [Chronos-2](https://arxiv.org/abs/2510.15821) (`amazon/chronos-2`), used strictly zero-shot. It
alternates *time attention* (within one series) and *group attention* (across the series in a batch), so one
ticker's recent path can inform another's forecast without retraining (`cross_learning=True`). Every prediction
is a quantile forecast (q10/q50/q90 used here).

**Why this model.** Published benchmarks (fev-bench, GIFT-Eval, Chronos Benchmark II) show Chronos-2 strongest on
covariate-informed and multivariate tasks, the capability tested here. They are general forecasting benchmarks,
though, and returns are close to a martingale by construction. The gap between "good at forecasting in general"
and "good at forecasting returns" is why this project exists rather than trusting the benchmark numbers.

**Why the bar is ~0.536 DA, not 0.5.** A directional bet with round-trip cost `c` and move size `m` has positive
expected value only when the hit rate `p > 0.5 + c/(2m)`. With `c ≈ 0.10%` and `m ≈ 1.4%`, `p* ≈ 0.536`. So the
chance-level DA seen throughout (≈0.49–0.51) is a clean failure, not a near-miss.

**Evaluation.** Walk-forward: for each config, up to 400 non-overlapping-anchor windows, each a real forecast
scored against realized returns at the configured horizons. Per (ticker, horizon) cell: DA with binomial p-value
and Wilson interval, Pearson/Spearman correlation, quantile coverage. Baselines (zero, last, momentum-5, AR(1))
use the identical windows. All multi-cell families are BH-corrected.

| Family | Question | Test |
|---|---|---|
| Basket gate | Does joint (multivariate) attention across a basket beat forecasting each ticker independently? | Paired McNemar test, window by window, on configs differing only in `group_mode` |
| Lead-lag confirmation | Does any pair in a wide ticker universe show real lead-lag structure? | Lagged cross-correlation screen → BH-corrected shortlist → re-test on a strictly later, non-overlapping window |
| Sector basket | Does a single homogeneous sector (vs. the cross-sector basket) change the multivariate-vs-univariate answer? | Same McNemar gate, per sector |

## A methodological trap, caught in real time

The first lead-lag discovery screen (unresidualized correlations) found 20 BH-significant pairs, but 19 of them
shared the same lag (3 bars) across unrelated tickers (oil/gas with retail, metals with transport). That is the
signature of a shared factor, not pairwise structure: the equal-weight market return had lag-3 autocorrelation
≈0.16 on that window. Leave-one-out market-factor residualization before the lagged correlations kept only 2 of
the 20 original pairs and spread the significant lags across 1–5. The discovery/confirmation design caught it
before it reached confirmation.

## Results

**Basket gate: multivariate vs. univariate (paired McNemar, BH-corrected)**

| Config | n windows | Cells (ticker×horizon) | BH-significant | Aggregate ΔDA | Gate |
|---|---:|---:|---:|---:|---|
| Daily, ctx=250 | 400 | 64 | 0 | −0.0011 | FAIL |
| Daily, ctx=100 | 400 | 64 | 0 | −0.0005 | FAIL |
| Daily, ctx=35 | 400 | 64 | 0 | −0.0001 | FAIL |
| 1h, ctx=250 | 400 | 64 | 0 | +0.0003 | FAIL |
| 1h, ctx=100 | 400 | 64 | 0 | +0.0018 | FAIL |
| 1h, ctx=35 | 400 | 64 | 0 | +0.0014 | FAIL |
| 10-minute, ~2mo window (2023) | 400 | 64 | 0 | −0.0010 | FAIL |
| 10-minute, ~2mo window (2024) | 400 | 64 | 0 | +0.0010 | FAIL |

Eight runs across three resolutions and three context lengths: |ΔDA| ≤ 0.0018 and 0 of 64 cells BH-significant
in every run. The two arms track each other almost window by window.

**Lead-lag confirmation (discovery → confirmation, close_adj)**
- Discovery (2020-02-21 → 2023-06-30, 55-ticker panel, market-factor residualized): 14,850 (pair, lag,
  direction) tests, 20 BH-significant (q < 0.05, capped at the top 20 by |r|).
- Confirmation (2023-07-01 → 2024-12-30, strictly out-of-sample): each pair re-tested, with its own BH correction
  within the 20-pair family.
- **Result: 0/20 pairs replicate.** The best uncorrected p (AFLT→UNAC, lag 1, p = 0.058) gives p_bh = 0.70.
  Several correlations shrink or flip out-of-sample (e.g. AFLT→PHOR, lag 2: r = −0.217 → −0.066).
- Basket-wide Chronos-2 on the same 18-ticker shortlist: mean DA 0.49–0.50 at ctx 35, 100 and 250, and 0/72
  cells BH-significant at ctx=35 and ctx=250. The same pattern held at daily, 1h and on raw close.

**UNAC at ctx=100: a second false positive, explained.** The ctx=100 run was the one exception: UNAC was
BH-significant at all four horizons (DA 0.60–0.64, p_bh as low as 0.0002) and beat every baseline (all ≤ 0.56),
which clears every leg of the per-pair gate. The same ticker and window were null at the other context lengths:

| context_len | n windows | UNAC DA (h1) | p (BH-corrected) |
|---|---:|---:|---:|
| 35 | 350 | 0.523 | 0.9998 |
| 100 | 285 | 0.635 | 0.0002 |
| 250 | 135 | 0.585 | 0.5210 |

The effect was stable within the window (DA 0.59–0.66 in every half and quarter of the 285 windows), so it was
tested on data nobody had looked at: the same 18-ticker family at ctx=100 on 2024-11-01 → 2026-09-17 (385
windows, from a dedicated `data_pipeline` pull; config
[`leadlag_confirm_adj_ctx100_holdout2025.yaml`](configs/leadlag_confirm_adj_ctx100_holdout2025.yaml)).
**UNAC's DA fell to 0.545–0.569**: still the top 4 of 72 cells, but no horizon survives BH (best p_bh = 0.26), and
no other ticker does either. Two checks close it:
- **Base rate.** The best holdout cell's raw p ≈ 0.008 (h=2, DA 0.569) is not rare in a family of 72:
  under a global null, `1 − (1 − 0.008)^72 ≈ 44%`.
- **Mechanism.** UNAC's lag-1 return autocorrelation was 0.222 in the confirmation window, vs 0.054 in discovery
  and 0.068 in the holdout: a +157% spike in August 2023 (0.77 → 1.99), then a decline in nearly every month
  through May 2024 (−7%, −13%, −31%, +18%, −10%, −5%, −15%, −33%…). A zero-information rule, "yesterday's sign
  predicts the 2-day-ahead sign", gets DA 0.535 on the confirmation window and 0.478 on the holdout: the same rise
  and fall as Chronos (0.60 → 0.55). Chronos was partly riding a transient momentum regime in one ticker's own
  history, not a lead-lag dependency, which is what this test was built to detect.

As with the market-factor bug, a result that clears every pre-registered gate can still be explained by
something unrelated to the hypothesis; a fresh holdout plus a mechanism check is what tells the difference.

**Sector baskets** (oil & gas, metals & mining, financials, utilities × {daily, 1h} × {ctx 35, 100, 250} = 24
configs, same McNemar gate)

| Sector | Resolution/ctx | BH-sig cells | Gate |
|---|---|---:|---|
| Oil & gas | 1h, ctx=250 | 1/48 (ΔDA negative) | FAIL |
| all other 23 combinations | — | 0/N | FAIL |

A homogeneous sector changes nothing: one BH-significant cell across 24 × ~40 tested, with negative aggregate ΔDA,
so the multi-part gate correctly rejects it as the lone chance hit a family this size produces.

**Resolution and context length.** The null holds at daily, hourly and 10-minute resolution and at 35 (≈7 weeks),
100 (≈20 weeks) and 250 bars (≈1 year). No choice recovered a signal another missed; the one exception (UNAC) is
explained above.

## Two additional checks on the pooled run data

**Is the model more accurate when it predicts larger moves?** Primary-horizon predictions from all eight
basket-gate runs (153,600 forecasts), binned by predicted move size:

| Bin (by \|predicted return\|) | n | DA |
|---|---:|---:|
| Q1 (smallest) | 30,720 | 0.451 |
| Q2 | 30,720 | 0.477 |
| Q3 | 30,720 | 0.486 |
| Q4 | 30,720 | 0.493 |
| Q5 (largest) | 30,720 | 0.488 |

DA rises with predicted size through Q4, dips at Q5, and never reaches 0.5: not a usable filter.

**Is there short-horizon structure Chronos could be missing?** On the 10-minute panel (16 tickers, ~69,000 bars)
the mean lag-1 return autocorrelation is −0.007 (range −0.085 to +0.098) and consecutive bars share a sign 46.8%
of the time, close to the 50% no-relationship baseline. There is no meaningful mean reversion or momentum at 10 minutes for Chronos to have missed.

## What this doesn't rule out

From the project's design document ([`docs/transient_dependency_research.md`](../docs/transient_dependency_research.md)):
none of these experiments rule out dependencies that exist only in short bursts, intraday delays that dissipate
by the close, event- or regime-conditioned or nonlinear relationships, dependencies in volatility, volume or
order flow rather than returns, lead/lag structure that changes across regimes, or anything outside the tickers,
dates and fields tested. An event-conditioned burst-detection follow-on (dependencies appearing briefly around
large moves), run at daily and hourly resolution under three parameter settings, was null as well.

## Running a config

Open [`run.ipynb`](run.ipynb), point `CONFIG_PATH` at any file under [`configs/`](configs/) and run all cells. Each
config is self-contained (tickers, dates, resolution, context length, baselines). It sources
[`lib.ipynb`](lib.ipynb) and reads the processed AlgoPack panels produced by [`../data_pipeline/`](../data_pipeline/).
The 2025 UNAC holdout is
[`configs/leadlag_confirm_adj_ctx100_holdout2025.yaml`](configs/leadlag_confirm_adj_ctx100_holdout2025.yaml).

## Data caveats for the results above

Audits during the alpha study ([`alpha_experiment/`](alpha_experiment/README.md)) found issues that touch the inputs of the experiments above. Their recorded results were **not recomputed**.
- **The daily close is the evening print.** The `candles_1d` close is the evening-session last print (~23:40 MSK), not the main-session close. It matches the main close on only 0.2–1.2% of days in 2021, 2023 and 2024, and on about half the days in 2020 and 2022. The daily-resolution experiments above used it.
  - This is not a leak: all series are consistently timed.
  - It does mean the "close" in those tests is an evening-session print, not the main-session close a daily strategy would realistically trade at.
  - The alpha and risk studies use the main-session close from 10-minute bars.
- **Dividend adjustment was one trading day late before 2023-07-31.** The poptimizer `day` field is the record date, not the ex-date. Under T+2 settlement this left a spurious −div / +div pair around every pre-T+1 dividend: for yields above 2% the mean was −5.0% then +6.8%, and the worst case was GAZP 2022-10 at −20.7% then +36.8%. Also fixed:
  - five dividends missing from the source were added;
  - one unpaid dividend (MGNT 2025-01) was removed;
  - record dates after the data end are no longer applied.

  Every `close_adj`-based result above (e.g. the lead-lag confirmation on `close_adj`) was computed on the uncorrected series.
- **Holiday rows.** The earlier pipeline puts each series on a regular grid with forward-fill (`to_regular_series` / `build_price_panel` in [`lib.ipynb`](lib.ipynb)), so market holidays on that grid become zero-return rows. The alpha and risk studies use an exchange-derived calendar with no forward-fill. The effect on the earlier directional-accuracy results was not measured.

## Fine-tuning (parallel track, paused)

An early attempt to fine-tune Chronos-2 for directional accuracy through AutoGluon was paused (an unresolved
intraday index-alignment bug, and no dedicated held-out design) and is not in this repository. Fine-tuning was
later done properly for the risk study ([`risk_experiment/`](risk_experiment/README.md)): LoRA, yearly refits trained only on past data, its own holdout.

## Engineering notes

The data pipeline ([`data_pipeline/`](../data_pipeline/)) that feeds this project is a
self-contained sibling project: it pulls MOEX AlgoPack candle, order-flow, and
open-interest data into a reproducible, tested Parquet output, including a dividend/split
price-adjustment step added mid-project after a data-quality check found no prior result
had ever adjusted for corporate actions (verified via a direct scan of known dividend/split
events; the adjustment is additive — a new `close_adj` column alongside the untouched raw
`close`, so no earlier committed result changed). Its notebook is generated from tracked
Python source via a build script (never hand-edited), with an offline test suite (fake ISS
responses, no network access needed) run after every change.
