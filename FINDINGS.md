# Findings: Chronos-2 on MOEX equities

**Headline result: a rigorous, replicated null.** Across ~10 independent axes — universe
composition, time resolution (daily / 1h / 10m), grouping (multivariate vs. univariate
attention), price adjustment (raw close vs. dividend/split-adjusted), context length
(a full log-spaced sweep: 35 / 100 / 250 bars), sector homogeneity, and cross-ticker
lead-lag structure — zero-shot Chronos-2 shows no directional edge on MOEX equity returns
beyond chance. Every gate, pre-registered before the run, failed. This document reports
that result and the methodology behind it, because for a study like this the methodology
*is* the contribution: the value isn't "did it make money," it's whether the process would
have caught a real edge if one had been there.

Two follow-ups extend the question beyond direction. A cross-sectional study found real ranking skill
(IC ≈ 0.07) but no net alpha beyond standard factors. A risk study found that Chronos reaches, but does
not beat, the best classical models for VaR/ES and hedging on a pre-registered 2025–26 holdout (both
sections below).

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
- **Caught methodology traps, not just a clean pipeline.** The lead-lag discovery step
  initially produced a shortlist dominated by one spurious pattern; the bug was found,
  diagnosed, and fixed before any confirmation run used the flawed shortlist. Later, the
  context-length sweep independently produced one BH-significant ticker (UNAC) at exactly
  one of three tested context lengths — rather than report it, a fresh out-of-sample
  holdout was pulled and run specifically to test it. The effect weakened but didn't fully
  vanish, so rather than stop at "not BH-significant," the mechanism was traced directly to
  a transient, idiosyncratic momentum regime in UNAC's own price history — not a cross-asset
  dependency, which is what the test was actually built to detect. Both are the same lesson,
  caught and resolved the same way (details below).

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
| Daily, ctx=100 | 400 | 64 | 0 | −0.0005 | FAIL |
| Daily, ctx=35 | 400 | 64 | 0 | −0.0001 | FAIL |
| 1h, ctx=250 | 400 | 64 | 0 | +0.0003 | FAIL |
| 1h, ctx=100 | 400 | 64 | 0 | +0.0018 | FAIL |
| 1h, ctx=35 | 400 | 64 | 0 | +0.0014 | FAIL |
| 10-minute, ~2mo window (2023) | 400 | 64 | 0 | −0.0010 | FAIL |
| 10-minute, ~2mo window (2024) | 400 | 64 | 0 | +0.0010 | FAIL |

Eight independent runs, across three resolutions and a full log-spaced context-length sweep
(35 → 100 → 250 bars). In every case, aggregate ΔDA is within noise of zero
(|ΔDA| ≤ 0.0018) and zero of the 64 tested cells survives BH correction. Multivariate and
univariate arms are not just "not significantly different" — they track each other almost
window-by-window.

**Lead-lag confirmation (discovery → confirmation, close_adj):**

- Discovery (2020-02-21 → 2023-06-30, 55-ticker panel, market-factor residualized):
  14,850 (pair, lag, direction) tests, 20 BH-significant (q<0.05, capped at top 20 by |r|).
- Confirmation (2023-07-01 → 2024-12-30, strictly out-of-sample): each shortlisted pair
  re-tested independently, own BH correction within the 20-pair family.
- **Result: 0/20 pairs replicate.** Best uncorrected p-value (AFLT→UNAC, lag 1, p=0.058)
  does not survive BH correction (p_bh=0.70). Several pairs' correlation sign flips
  entirely out-of-sample (e.g. AFLT→PHOR, lag 2: r=−0.217 in discovery → r=−0.066 in
  confirmation) — the exact failure mode a discovery/confirmation split exists to catch.
- Basket-wide Chronos-2 run on the same 18-ticker shortlist at three context lengths — 35,
  100, and 250 bars — mean DA 0.49–0.50 at all three, and 0/72 cells BH-significant at
  ctx=35 and ctx=250. ctx=100 is the one exception — see below.

This pattern — real correlations at discovery, disappearing under out-of-sample
BH-corrected re-test — repeated across every resolution tried (daily, 1h, and the earlier
raw-close version of this same test).

**A second false positive, caught and then confirmed caught, at ctx=100.** The ctx=100
basket-wide run was the one exception to "0/72 cells significant": UNAC came back
BH-significant at all four evaluated horizons (DA 0.60–0.64, p_bh as low as 0.0002), and its
DA at every horizon beat every baseline (`last`, `momentum5`, `ar1`, all ≤0.56). Taken alone,
that clears every leg of this project's own pre-registered per-pair gate. But UNAC is on the
confirmation shortlist precisely because it is also tested at context lengths 35 and 250 on
the identical ticker, tickers, and confirmation window — and it was null at both:

| context_len | n windows | UNAC DA (h1) | p (BH-corrected) |
|---|---:|---:|---:|
| 35 | 350 | 0.523 | 0.9998 |
| 100 | 285 | 0.635 | 0.0002 |
| 250 | 135 | 0.585 | 0.5210 |

That alone was suggestive but not decisive — a within-window stability check (splitting the
285 ctx=100 confirmation windows into halves/quarters) showed the effect held up internally
(DA 0.59–0.66 in every sub-period), which is not what a single lucky cluster of windows
would look like. So rather than settle this on the same data from three different angles,
the actual test was run: the same 18-ticker family, at ctx=100, on a completely fresh
window — 2024-11-01 to 2026-09-17, entirely new calendar time, fetched via a dedicated
`data_pipeline` pull specifically for this check (385 windows, more than either original
run). **Result: UNAC's DA drops to 0.545–0.569** — still the top 4 cells of 72 tested, but
none of its four horizons survive BH correction (best p_bh=0.26, nowhere near 0.05), nor
does any other ticker in the family.

0.55 DA is not nothing, and treating "p_bh>0.05" as the whole answer would be too quick —
that was pointed out directly, and it was fair to push back on. Two things resolve it
properly. First, base rate: under a pure global null (no ticker has any real relationship),
the single-cell raw p for UNAC's best holdout horizon (h=2, DA=0.569, p≈0.008) is genuinely
low — but across 72 independently tested cells, `1 − (1 − 0.008)^72 ≈ 44%`. Close to a coin
flip's worth of chance that *some* cell in a family this size looks this extreme even if
nothing real is happening anywhere. Second, and more decisive: **what actually produced the
original hit is identifiable, and it isn't a cross-asset dependency.**

UNAC's own return series shows why. In the original confirmation window (2023-07-01 to
2024-12-30), UNAC's lag-1 return autocorrelation is **0.222** — unusually high (vs. 0.054 in
the discovery window and 0.068 in the holdout). The cause is visible directly in the price:
UNAC spiked **+157% in a single month** (Aug 2023: 0.77 → 1.99) and then trended down in
nearly every following month through May 2024 (−7%, −13%, −31%, +18%, −10%, −5%, −15%,
−33%...) — a real, sustained, one-directional move, not noise. A `context_len=100` window is
long enough to pick up a multi-month trend like that and short enough for it to dominate the
lookback. A trivial, one-line rule with zero cross-asset information — "yesterday's return
sign predicts the 2-day-ahead return sign" — gets **DA=0.535 on that same confirmation
window**, in the same direction as Chronos's edge, just weaker. That same naive rule gets
**DA=0.478 (below chance) on the holdout window**, where UNAC's return autocorrelation had
reverted to ordinary levels and its sign-autocorrelation actually went slightly negative
(mean-reverting). Chronos's DA on UNAC rose and fell in exactly the same pattern (0.60 → 0.55)
as this zero-information momentum baseline (0.535 → 0.478), which is the signature of a
model partially riding a transient, idiosyncratic trend in one ticker's own price history —
not evidence of a lead-lag relationship to the other tickers, indexes, or futures this test
was actually designed to detect.

This closes the question the only way that actually could: not by arguing about the
existing data harder, but by testing on data nobody had looked at yet, and then checking the
mechanism rather than stopping at the corrected p-value. It's the same lesson the
market-factor bug taught, demonstrated a second time end-to-end — a result that clears every
pre-registered gate criterion on its own numbers, and that still looks like "the best result
in the run" even after replication weakens it, can still be explained by something with
nothing to do with the hypothesis being tested.

**Sector baskets** (4 sectors — oil & gas, metals & mining, financials, utilities — ×
{daily, 1h} × {context 35, 100, 250} = 24 configs, same McNemar gate as the basket-gate
family):

| Sector | Resolution/ctx | BH-sig cells | Gate |
|---|---|---:|---|
| Oil & gas | 1h, ctx=250 | 1/48 (ΔDA negative) | FAIL |
| all other 23 combinations | — | 0/N | FAIL |

Restricting to a single, economically homogeneous sector — the natural follow-up to "maybe
the basket gate's deliberately cross-sector basket hid a same-sector effect" — does not
change the outcome, at any of the three context lengths tested. One cell across all 24 ×
~40 tested cells reached BH significance, and even there the gate's other conditions
(aggregate ΔDA > 0) failed, which is the multi-part gate criterion doing exactly what it's
for: a lone significant cell in a large family is exactly what you'd expect by chance, and
the gate doesn't let it through alone.

**Resolution and context-length sweep.** Combining all of the above: the null holds at
daily, hourly, and 10-minute resolution, and across a full log-spaced sweep of context
length — 35 bars (≈7 trading weeks), 100 bars (≈20 weeks), and 250 bars (≈1 trading year).
No resolution or context choice recovered a signal any other choice missed; the one
apparent exception (UNAC at ctx=100, above) was checked against a fresh holdout window,
weakened substantially, and traced to a one-ticker momentum regime rather than the
cross-asset structure this sweep was designed to detect — exactly the kind of isolated hit
this design exists to catch and correctly explain away.

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

## Cross-sectional follow-up: Chronos-2 quantiles as alpha and as a risk model

The directional-accuracy null above asks whether Chronos-2 can call each ticker's direction. A portfolio manager asks something different: do its **quantile forecasts**, turned into cross-sectional signals, earn net alpha beyond standard factors, or make a better volatility model? This follow-up tested that question in [`forecasting/alpha_experiment/`](forecasting/alpha_experiment/README.md).

**Setup.**
- **Data:** a daily panel on the **main-session close** (18:40 closing auction). 47–70 point-in-time-eligible liquid names.
- **Forecasts:** 21-quantile forecasts at every trading day.
- **Books:** weekly-rebalanced, beta-neutral long-short and long-only books, with 5 bps costs plus borrow.
- **Tests:** Fama-MacBeth and net spanning regressions against momentum / reversal / low-vol / AR(1) books. For volatility, QLIKE against intraday realized variance.
- **Protocol:** a pre-registered one-shot 2024 test, then an improvement wave on 2021–2024 with a trial ledger (238 rows). The 2025–26 holdout was reserved for the risk study.

**Result: the per-ticker null does not carry over to ranking, but the ranking skill is not tradable.**
- **Real cross-sectional IC.** Chronos ranks stocks with IC 0.07–0.08 (t 6–7). In 2024 its IC (0.088–0.096) was higher than any classic signal's.
- **Mostly known factors.** A linear "mimic" on cheap trailing statistics reproduces about 45% of the signal, and it *trades better* than Chronos: net Sharpe 2.0 vs 1.2.
- **No net alpha.** The pre-registered 2024 net spanning-alpha leg failed (t −0.55; −0.97 on corrected data).
- **Nothing tried changed that.** The 20-configuration sweep covered cross-learning (4 grouping schemes), past covariates (index, sector, futures), context 64–512, and residual / weekly / log-price targets. Its best net spanning t was 0.82 (cov_fut).
- **Improvements on top of the winner didn't either.** Quantile-shape signals, combination with classic factors and turnover control were built afterwards. The best, an EMA-smoothed cov_fut signal, reached spanning t 1.46, still below 2. The winning configuration stays below 2 even at zero cost (t 1.71).
- **The best configuration.** Covariates with Brent, USD/RUB and gold futures keep a Chronos-specific component beyond a mimic given the same inputs (Fama-MacBeth t 2.47, an upper bound since the mimic is linear). But:
  - that component's own book loses money (net Sharpe −0.38);
  - its weight in a combination with classic factors is about 0.002;
  - a Bonferroni bound across the 20 configurations would need t ≈ 3.

**Volatility: a good off-the-shelf model, matched by log-HAR.**
- **Return-based width:** Chronos's forecast width from daily returns is no better than EWMA or GARCH(1,1), and its tails were too narrow in 2024 (6.7% q05 hits).
- **Realized-variance target:** run on log realized variance, Chronos beats EWMA, GARCH and HAR (QLIKE 0.50 vs 0.65–0.85).
- **But log-HAR matches it:** a pooled log-HAR with a market term reaches QLIKE 0.455 (DM t +0.78). Chronos's edge came from working in log space and pooling across names, not from anything a classical model cannot do.
- **Distinct information, little practical gain:** a pre-registered encompassing test shows Chronos carries information log-HAR lacks (t 4.3), mostly in calm years. A fixed combination does not lower QLIKE, and no portfolio use showed an economic gain.

**Next:** whether Chronos is useful for **risk** (VaR/ES, vol targeting, minimum-variance portfolios, hedging). See the risk follow-up below.

## Risk follow-up: Chronos-2 for VaR, vol targeting, minimum-variance portfolios and hedging

The alpha follow-up found Chronos-2 a good volatility model that log-HAR matches. The last open question was
whether that makes it useful for **risk decisions**, and whether calibration, mixing with classical models,
multivariate input, covariates or LoRA fine-tuning give it an edge. This study, in
[`forecasting/risk_experiment/`](forecasting/risk_experiment/README.md), used the sealed 2025–26 holdout.

**Setup.**
- **Uses:** 1-day VaR/ES for every stock (FZ0 loss); vol targeting an equal-weight book to 10% (performance
  fee); a long-only minimum-variance portfolio (realized variance); hedging each stock with the IMOEX future
  (hedged variance).
- **Arms:** zero-shot Chronos on returns, log realized variance and both jointly; calibrated and FHS versions;
  fixed, fitted and regime-dependent mixtures with the best classical model; a one-factor covariance model;
  market/macro covariates; and LoRA fine-tuning on Colab with yearly refits trained only on past data.
  Classical rivals: RiskMetrics/EWMA, GARCH(-t), FHS, HAR and log-HAR variants, rolling OLS beta.
- **Protocol:** all selection on 2021–24 (265 trials in the ledger), then a pre-registration committed before
  any holdout forecast existed, then one evaluation on 2025-01 → 2026-09. Claims were "better than" (beats
  EWMA and GARCH, then the best classical model, Holm-corrected) and "not worse" (non-inferiority against the
  best classical model with margins fixed on dev).

**Result: parity with the best classical risk models, no demonstrated advantage.**
- **Not worse, confirmed.** For VaR/ES and hedging, Chronos (mixed with a classical model) is not meaningfully
  worse than the best classical model (non-inferiority p 8e-17 and 8e-6), and has the best point estimate in
  both (FZ0 −3.082 vs −3.070 for FHS log-HAR; hedged vol 31.13% vs 31.30% for rolling OLS beta).
- **Not better.** No "better than" claim survives the Holm correction. The closest: the VaR arm beats
  RiskMetrics and GARCH-t at raw p 0.031 (threshold 0.010).
- **Minimum-variance portfolios:** plain EWMA stays best (16.85% vs 17.74% annual vol for Chronos).
- **Vol targeting:** the Chronos one-factor book earns +243 bps/yr over EWMA but trails GARCH and a log-HAR
  portfolio model.

**The dev period over-stated Chronos, and the holdout caught it.**
- **Calm-day VaR:** Chronos beat FHS log-HAR on calm days with dev t −4.0; the pre-registered holdout claim gave
  t −1.3 (p 0.095). A winner's curse from picking the best of 265 variants.
- **Fine-tuning:** multivariate LoRA fine-tuning (returns and log-RV jointly) beat zero-shot Chronos in 21 of 22
  arms on 2022–24. On the holdout the VaR gain reversed sign (t +1.07) and the GMV gain was insignificant.
  Fine-tuning on log-RV alone never helped.
- **Regimes:** "better in calm, worse in stress" held on dev; on the holdout it reversed for GMV.

**Engineering lessons worth keeping.**
- An evaluation that requires every arm to exist on a date silently dropped the 2022 crash months, because the
  regime mixtures had no values there. It was found by a dry run of the holdout code and fixed before the
  holdout opened (all dev tables re-scored, trials not re-counted).
- A median-based calibration of single-series forecasts is biased for χ²-like ratios (vol-targeted books ran at
  18–20% instead of 10%); it uses a rolling mean now.
- Fine-tuned forecasts start only in 2022, so they were spliced onto their zero-shot twins before 2022; otherwise
  every calibrated or mixed arm would have been undefined during the crash.

**Bottom line across the three studies:** Chronos-2 has no directional edge, no tradable alpha, and for risk it
reaches, but does not beat, the best classical tools, at a much higher compute cost.

## Fine-tuning (parallel track, paused)

A separate track fine-tuned Chronos-2 on the same MOEX panel via AutoGluon's
`TimeSeriesPredictor`, rather than using it zero-shot. The daily configuration ran
end-to-end on a real GPU; the intraday (10m/60m) configurations hit an unresolved
AutoGluon index-alignment bug. Given the zero-shot results above and the real overfitting/
leakage risk that fine-tuning for directional accuracy would carry without its own
dedicated held-out design, this track was deliberately paused rather than pushed through —
not published in this repository (kept local, working but incomplete), and named here as a
scoped decision rather than a hidden loose end. Fine-tuning was later done properly for the risk
follow-up (LoRA, yearly refits trained only on past data, its own held-out design); see *Risk follow-up*.

## Data caveats for the results above

Audits in the follow-up found issues that also touch the inputs of the experiments reported earlier in this document. Their recorded results were **not recomputed**.
- **The daily close is the evening print.** The `candles_1d` close is the evening-session last print (~23:40 MSK), not the main-session close. It matches the main close on only 0.2–1.2% of days in 2021, 2023 and 2024, and on about half the days in 2020 and 2022. The daily-resolution experiments above used it.
  - This is not a leak: all series are consistently timed.
  - It does mean the "close" in those tests is an evening-session print, not the main-session close a daily strategy would realistically trade at.
  - The follow-up uses the main-session close from 10-minute bars.
- **Dividend adjustment was one trading day late before 2023-07-31.** The poptimizer `day` field is the record date, not the ex-date. Under T+2 settlement this left a spurious −div / +div pair around every pre-T+1 dividend: for yields above 2% the mean was −5.0% then +6.8%, and the worst case was GAZP 2022-10 at −20.7% then +36.8%. Also fixed:
  - five dividends missing from the source were added;
  - one unpaid dividend (MGNT 2025-01) was removed;
  - record dates after the data end are no longer applied.

  Every `close_adj`-based result above (e.g. the lead-lag confirmation on `close_adj`) was computed on the uncorrected series.
- **Holiday rows.** The earlier pipeline puts each series on a regular grid with forward-fill (`to_regular_series` / `build_price_panel` in `forecasting/lib.ipynb`), so market holidays on that grid become zero-return rows. The follow-up uses an exchange-derived calendar with no forward-fill. The effect on the earlier directional-accuracy results was not measured.

## Limitations and future work

- **Scope.** All experiments use MOEX equities, 2020–2024 daily/2023–2024 intraday, a fixed
  universe selected by liquidity. Results do not generalize to other markets, periods, or
  ticker sets by assumption.
- **Detection vs. profitability.** This project tests for statistical dependency, not
  whether a deployable strategy exists. A basket-wide null does not by itself rule out a
  narrow, regime-specific edge too small for these test families to detect at the sample
  sizes used.
- **Calibration/volatility use and fine-tuning** were the open direction here, and have since been
  tested: see *Cross-sectional follow-up* (Chronos on realized variance is strong but matched by log-HAR)
  and *Risk follow-up* (calibrated, mixed and LoRA fine-tuned Chronos reaches, but does not beat, the best
  classical risk models on a pre-registered holdout).

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
