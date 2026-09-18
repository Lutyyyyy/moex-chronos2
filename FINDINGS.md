# Findings: zero-shot Chronos-2 on MOEX equities

**Headline result: a rigorous, replicated null.** Across ~10 independent axes — universe
composition, time resolution (daily / 1h / 10m), grouping (multivariate vs. univariate
attention), price adjustment (raw close vs. dividend/split-adjusted), context length
(35 / 250 bars), sector homogeneity, and cross-ticker lead-lag structure — zero-shot
Chronos-2 shows no directional edge on MOEX equity returns beyond chance. Every gate,
pre-registered before the run, failed. This document reports that result and the
methodology behind it, because for a study like this the methodology *is* the
contribution: the value isn't "did it make money," it's whether the process would have
caught a real edge if one had been there.

## Why this is a meaningful negative result, not just "it didn't work"

A negative result is only informative if it comes with evidence the test had teeth. Four
things earn that here:

- **Pre-registered stopping rules.** Every experiment's success criterion — ΔDA (directional
  accuracy) > 0 AND at least one Benjamini-Hochberg-significant cell favoring the tested
  arm AND that arm beating naive baselines — was fixed before the run, not chosen after
  looking at results.
- **Multiple-comparisons correction applied consistently.** Every experiment family that
  tests more than one (ticker, horizon) cell is BH-corrected. This mattered in practice: see
  "A methodological trap, caught in real time" below.
- **Discovery/confirmation splits with verified non-overlapping dates**, for every
  hypothesis-generating step (lead-lag pair screening). Candidates are never evaluated on
  the data used to find them.
- **A caught methodology bug**, not just a clean pipeline. The lead-lag discovery step
  initially produced a shortlist dominated by one spurious pattern; the bug was found,
  diagnosed, and fixed before any confirmation run used the flawed shortlist (details
  below).

## Method

**Model.** [Chronos-2](https://arxiv.org/abs/2510.15821) (`amazon/chronos-2`), a pretrained
time-series foundation model used strictly zero-shot — no fine-tuning. It alternates *time
attention* (within one series) and *group attention* (across series in a batch), which
lets it use one ticker's recent path to inform another's forecast without retraining
(`cross_learning=True` in the underlying API). Every prediction is a full quantile forecast
(q10/q50/q90 used here), not a point estimate.

**Why this model.** The published benchmarks (fev-bench, GIFT-Eval, Chronos Benchmark II)
show Chronos-2 winning specifically on covariate-informed and multivariate tasks — the
capability this project needed to test. But those benchmarks are general-forecasting, not
financial, and financial returns are close to a martingale by construction. That gap between
"good at forecasting in general" and "good at forecasting *returns*" is precisely why this
project exists rather than trusting the benchmark numbers directly.

**Why the bar is ~0.536 DA, not 0.5.** For a single directional bet with round-trip cost `c`
and target move size `m`, expected value is positive only when hit-rate
`p > 0.5 + c/(2m)`. For illustrative retail-scale numbers (`c ≈ 0.10%` round-trip,
`m ≈ 1.4%`), that breakeven is `p* ≈ 0.536` — a model needs meaningfully better than 50/50
just to cover trading costs, let alone be worth deploying. This is why "chance-level DA"
(≈0.49–0.51 throughout this project) is reported as a clean failure, not a near-miss.

**Evaluation.** Walk-forward (not random) cross-validation: for each config, up to 400
non-overlapping-anchor windows are drawn from the panel, each producing a real forecast
evaluated against realized returns at the configured horizons. Metrics per (ticker,
horizon) cell: directional accuracy (DA), binomial p-value with Wilson confidence interval,
Pearson/Spearman correlation, quantile coverage. All multi-cell families are BH-corrected.
Baselines (zero, last, momentum-5, AR(1)) are computed on the identical windows.

**The three experiment families**

| Family | Question | Test |
|---|---|---|
| Basket gate | Does joint (multivariate) attention across a basket of tickers beat forecasting them independently? | Paired McNemar test, window-by-window, on identical configs differing only in `group_mode` |
| Lead-lag confirmation | Does any pair among a wide ticker universe show real lead-lag structure? | Pairwise lagged cross-correlation discovery screen → BH-corrected shortlist → re-tested on a strictly later, non-overlapping confirmation window |
| Sector basket | Does restricting the basket to one economically homogeneous sector (vs. Phase B's deliberately cross-sector basket) change the multivariate-vs-univariate answer? | Same McNemar gate as basket gate, applied per sector |

## A methodological trap, caught in real time

The lead-lag discovery screen's first run (unresidualized correlations) found 20
BH-significant candidate pairs — but 19 of the 20 shared the exact same lag (3 bars) across
otherwise economically unrelated tickers (oil/gas paired with retail, metals with
transport). That pattern doesn't look like genuine pairwise structure; it looks like a
shared factor. Checked directly: the panel-wide equal-weight market return has lag-3
autocorrelation ≈0.16 on that window, which alone explains a broad cluster of same-lag false
positives across pairs that merely share market exposure. The fix — leave-one-out
market-factor residualization applied before computing lagged correlations — changed the
shortlist substantially (only 2 of 20 pairs survived from the original list) and spread the
significant lags across 1–5 instead of clustering at 3. This is exactly the kind of
data-dredging trap a discovery/confirmation split with correction is designed to catch, and
here it caught something real before it reached the confirmation stage.

## Results

**Basket gate — multivariate vs. univariate (paired McNemar, BH-corrected):**

| Config | n windows | Cells (ticker×horizon) | BH-significant | Aggregate ΔDA | Gate |
|---|---:|---:|---:|---:|---|
| Daily, ctx=250 | 400 | 64 | 0 | −0.0011 | FAIL |
| Daily, ctx=35 | 400 | 64 | 0 | −0.0001 | FAIL |
| 1h, ctx=250 | 400 | 64 | 0 | +0.0003 | FAIL |
| 1h, ctx=35 | 400 | 64 | 0 | +0.0014 | FAIL |
| 10-minute, ~2mo window (2023) | 400 | 64 | 0 | −0.0010 | FAIL |
| 10-minute, ~2mo window (2024) | 400 | 64 | 0 | +0.0010 | FAIL |

Six independent runs, across three resolutions and two context lengths. In every case,
aggregate ΔDA is within noise of zero (|ΔDA| ≤ 0.0014) and zero of the 64 tested cells
survives BH correction. Multivariate and univariate arms are not just "not significantly
different" — they track each other almost window-by-window.

**Lead-lag confirmation (discovery → confirmation, close_adj):**

- Discovery (2020-02-21 → 2023-06-30, 55-ticker panel, market-factor residualized):
  14,850 (pair, lag, direction) tests, 20 BH-significant (q<0.05, capped at top 20 by |r|).
- Confirmation (2023-07-01 → 2024-12-30, strictly out-of-sample): each shortlisted pair
  re-tested independently, own BH correction within the 20-pair family.
- **Result: 0/20 pairs replicate.** Best uncorrected p-value (AFLT→UNAC, lag 1, p=0.058)
  does not survive BH correction (p_bh=0.70). Several pairs' correlation sign flips
  entirely out-of-sample (e.g. AFLT→PHOR, lag 2: r=−0.217 in discovery → r=−0.066 in
  confirmation) — the exact failure mode a discovery/confirmation split exists to catch.
- Basket-wide Chronos-2 run on the same 18-ticker shortlist: 135 windows, mean DA 0.501,
  0/72 cells BH-significant.

This pattern — real correlations at discovery, disappearing under out-of-sample
BH-corrected re-test — repeated across every resolution tried (daily, 1h, and the earlier
raw-close version of this same test).

**Sector baskets** (4 sectors — oil & gas, metals & mining, financials, utilities — ×
{daily, 1h} × {context 35, 250} = 16 configs, same McNemar gate as the basket-gate family):

| Sector | Resolution/ctx | BH-sig cells | Gate |
|---|---|---:|---|
| Oil & gas | 1h, ctx=250 | 1/48 (ΔDA negative) | FAIL |
| all other 15 combinations | — | 0/N | FAIL |

Restricting to a single, economically homogeneous sector — the natural follow-up to "maybe
Phase B's deliberately cross-sector basket hid a same-sector effect" — does not change the
outcome. One cell across all 16 × ~40 tested cells reached BH significance, and even there
the gate's other conditions (aggregate ΔDA > 0) failed, which is the multi-part gate
criterion doing exactly what it's for: a lone significant cell in a large family is exactly
what you'd expect by chance, and the gate doesn't let it through alone.

**Resolution and context-length sweep.** Combining all of the above: the null holds at
daily, hourly, and 10-minute resolution, and at both short (35-bar, ≈7 trading weeks) and
long (250-bar, ≈1 trading year) context lengths. No resolution or context choice recovered
a signal any other choice missed.

## Two additional checks, run directly against the pooled run data

**Does accuracy improve for the model's more confident (larger-magnitude) predictions?**
Pooling primary-horizon predictions across all eight basket-gate runs (153,600 forecasts)
and binning by predicted move size:

| Bin (by \|predicted return\|) | n | DA |
|---|---:|---:|
| Q1 (smallest) | 30,720 | 0.451 |
| Q2 | 30,720 | 0.477 |
| Q3 | 30,720 | 0.486 |
| Q4 | 30,720 | 0.493 |
| Q5 (largest) | 30,720 | 0.488 |

DA rises through Q1–Q4 as predicted move size grows, then drops slightly at Q5 — and no
bin reaches 0.5. There's a mild, monotonic-until-the-top relationship between confidence
and accuracy, but it never crosses chance, so it isn't a usable filter on its own.

**Is there short-horizon mean reversion Chronos could in principle be missing?** Checked
directly on the 10-minute panel (16 tickers, ~69,000 bars): mean lag-1 return
autocorrelation across tickers is −0.007 (range across tickers: −0.085 to +0.098), and the
probability consecutive bars share a sign is 46.8%, close to (if a little below) the
50% no-relationship baseline. There is no meaningful mean-reversion or momentum signal at
10-minute resolution in this universe for Chronos to have missed — the null result here is
consistent with the underlying data, not an artifact of the model failing to find something
that was there.

## What this doesn't rule out

Reused from this project's own design document
([`docs/transient_dependency_research.md`](docs/transient_dependency_research.md)), since it
applies equally to every result above: none of these experiments rule out dependencies that
exist only in short bursts, intraday delays that dissipate by the close, event- or
regime-conditioned dependencies, nonlinear or asymmetric relationships, dependencies
expressed in volatility/volume/order-flow rather than returns, a leader/follower/lag
structure that changes across regimes, or relationships outside the specific tickers, dates,
and fields tested here. A green cell on a DA heatmap is not itself evidence of a pairwise
dependency — with dozens of cells and hundreds of forecasts per cell, several values around
0.55 are expected by chance alone; this is the same lesson the discovery/confirmation split
exists to enforce, encountered independently in this project's own market-factor bug (above)
and re-confirmed by the lead-lag results.

An event-conditioned burst-detection follow-on (do dependencies appear briefly around large
moves, rather than persist across the full sample?) was also run, at both daily and hourly
resolution across three parameter settings. All three came back null as well.

## Fine-tuning (parallel track, paused)

A separate track fine-tuned Chronos-2 on the same MOEX panel via AutoGluon's
`TimeSeriesPredictor`, rather than using it zero-shot. The daily configuration ran
end-to-end on a real GPU; the intraday (10m/60m) configurations hit an unresolved
AutoGluon index-alignment bug. Given the zero-shot results above and the real overfitting/
leakage risk that fine-tuning for directional accuracy would carry without its own
dedicated held-out design, this track was deliberately paused rather than pushed through —
not published in this repository (kept local, working but incomplete), and named here as a
scoped decision rather than a hidden loose end.

## Limitations and future work

- **Scope.** All experiments use MOEX equities, 2020–2024 daily/2023–2024 intraday, a fixed
  universe selected by liquidity. Results do not generalize to other markets, periods, or
  ticker sets by assumption.
- **Detection vs. profitability.** This project tests for statistical dependency, not
  whether a deployable strategy exists. A basket-wide null does not by itself rule out a
  narrow, regime-specific edge too small for these test families to detect at the sample
  sizes used.
- **Calibration/volatility fine-tuning**, as opposed to directional fine-tuning, remains an
  open, more promising direction: Chronos-2's quantile output could in principle be
  recalibrated for volatility forecasting without the same overfitting risk directional
  fine-tuning carries. Not attempted here.
- **The context_len=100 sweep point** (log-spaced midpoint between the 35 and 250 bar
  configs already run) is staged as configs but not yet executed at time of writing.

## Engineering notes

The data pipeline ([`data_pipeline/`](data_pipeline/)) that feeds this project is a
self-contained sibling project: it pulls MOEX AlgoPack candle, order-flow, and
open-interest data into a reproducible, tested Parquet output, including a dividend/split
price-adjustment step added mid-project after a data-quality check found no prior result
had ever adjusted for corporate actions (verified via a direct scan of known dividend/split
events; the adjustment is additive — a new `close_adj` column alongside the untouched raw
`close`, so no earlier committed result changed). Its notebook is generated from tracked
Python source via a build script (never hand-edited), with an offline test suite (fake ISS
responses, no network access needed) run after every change.
