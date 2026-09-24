# Chronos-2 as an alpha generator — pre-registration and results

**Question.** Do zero-shot Chronos-2 *quantile* forecasts, turned into cross-sectional signals, produce
net alpha on MOEX equities beyond classic strategies? There are two tracks:
- **Track A (return alpha):** location signals from the forecast distribution.
- **Track B (risk model):** the forecast width used as a volatility forecast.

This is a different question from the per-ticker directional-accuracy null in [FINDINGS.md](../../FINDINGS.md). Ranking ~60 names only needs relative skill, and a vol forecast needs no return skill at all.

Plan: [`tmp/plans/alpha_experiment.md`](../../tmp/plans/alpha_experiment.md). Code: [`alpha_lib.py`](alpha_lib.py) (pure functions, tested in [`tests/`](tests/)) and [`alpha_run.py`](alpha_run.py) (stages `data → forecast → dev → test → holdout`).

## Status

**PRE-REGISTRATION.** Everything in this section is frozen by the git commit that adds it. That commit comes *before* the `test` stage (2024) is run. Results are appended below it later, never edited into it.

<!-- PREREG_START -->
### Data (what the numbers are computed on)
- **Prices.** Daily prices are the **main-session close**: the last 10m bar starting ≤18:50 MSK, which for 2021–2024 is always the 18:40 closing-auction bar. It is dividend/split adjusted (`close_adj`). The `candles_1d` close is **not** used. It is the evening-session last print (~23:40) on ≈100% of 2021–2024 days (it matches the main close on only 0.2–1.2% of 2021/2023/2024 days), which is not a realistic fill.
- **Calendar.** Weekdays on which IMOEX printed a full main session *and* at least half the usual number of shares printed. This drops holidays, the 2022-02-28→03-23 closure (one gap return) and 2022-01-07 (IMOEX-only day). There is no forward-filling of holidays.
- **Universe (point-in-time).** A name needs at least 250 observed returns, a trailing 60-day median main-session traded value of at least 5M RUB, and a fresh print on the day. That gives 47–70 names after 2021 (median 52 in 2021, 65 in 2024) out of 70 ever eligible.
- **Benchmarks.**
  - IMOEX (main close) and MCFTR (total return, from ISS).
  - The CBR key rate (cbr.ru) as the risk-free rate. Long-only and buy-and-hold Sharpes are excess of it. Dollar-neutral books are self-financing, so their Sharpe is raw.
- **Realized variance (Track B target).** Main-session 10m squared returns plus the squared close→open overnight term. It averages 1.37× squared close-to-close returns (microstructure noise), which is why a level-scale-adjusted QLIKE is also required.

### Forecasts
- **Model and inputs.** Chronos-2 (`amazon/chronos-2`), zero-shot, univariate, target only (daily log returns), context 250, horizon 6, on the model's native 21-quantile grid. Anchors are every trading day 2021-01-04 → 2024-12-30: 990 anchors, 350,700 rows, every (anchor, eligible name) present. The model is called with `predict_quantiles`. No 2025+ data was loaded (it is truncated at read time), and forecasting refuses anchors ≥ 2025-01-01.
- **Crossing quantiles.** 9 of 350,700 rows had tiny crossings (<0.1% of the q01–q99 width, near the median). They are fixed by monotone rearrangement.

### Signals, books, costs (identical for Chronos and every baseline)
- **Chronos features** use the steps covered by the holding period (h=2..6 at the primary exec lag of 1):
  - `MED` = Σ q50
  - `SIG` = √Σ var, from the exact piecewise-linear quantile-function integral with flat tails
  - `MED_SIG` = MED/SIG
- **Classic baselines:** `mom_12_1`, `rev_5d`, `rev_1d`, `lowvol_60d`, `ar1` (rolling 250-day AR(1) forecast), equal-weight universe, IMOEX and MCFTR.
- **Long-short book:** cross-sectional rank weights, dollar-neutral **and** beta-neutral (trailing 250-day β to IMOEX), gross 1.
- **Long-only book:** equal-weight top quintile.
- **Rebalancing:** weekly, as 5 staggered tranches (one per weekday), with holdings drifting between rebalances.
- **Primary execution:** decide at close d, trade at the main close of d+1.
- **Costs:** 5 bps one-way (10 bps round trip) plus 5% p.a. borrow on shorts. Sweeps: costs 0/5/10/20 bps, borrow 0/5/10%, exec lag 0.

### Frozen v1 primaries (selected on dev 2021–2023 by rules fixed in code before any dev result)
| Track | Primary | Selection rule | Dev evidence at selection |
|---|---|---|---|
| A | **`MED_SIG`**, beta-neutral long-short, exec lag 1 | highest dev IC Newey-West t among {MED, MED_SIG} | IC 0.068, NW t 5.78; net Sharpe 1.46; **DSR 0.941 (N=4) → below 0.95, "weak going in"** |
| B | **`lowvol_factor`**: long-short rank book on −σ̂_Chronos vs the identical book on −σ̂_EWMA | largest dev net-Sharpe gain over the EWMA twin | gain +0.011 Sharpe (bootstrap p=0.46); DSR 0.012 (N=4) |

### Pre-registered 2024 gate (evaluated once; the code refuses a second run)
**Track A passes only if all three hold** for the primary on 2024, at exec lag 1:
- **A1:** mean daily rank IC vs the forward 5-day (d+2..d+6) log return has Newey-West (lag 8) t > 2.
- **A2:** net-of-cost **spanning alpha**. Regress the Chronos long-short net daily returns on the five classic long-short net returns plus IMOEX (Newey-West lag 10); the intercept must have t > 2.
- **A3:** the **Fama-MacBeth** Chronos coefficient has t > 2, controlling for mom_12_1, rev_5d, rev_1d, lowvol_60d and size (log median traded value), with Newey-West lag 8.

**Track B passes only if both hold:**
- **B1:** Chronos 5-day variance beats **both** EWMA(0.94) **and** GARCH(1,1) on QLIKE against realized variance, with Diebold-Mariano one-sided p < 0.05 for each, on raw **and** on dev-scale-adjusted QLIKE. This is an intersection-union test, so there is no multiplicity correction.
- **B2:** the frozen use beats its EWMA twin on net Sharpe, with stationary-bootstrap one-sided p < 0.05.

**Reported, not gated:** the full baseline Sharpe table, cost/borrow/lag sweeps (the exec-lag-0 sweep reuses the lag-1 universe mask), long-only active return / information ratio / CAPM alpha, IC ex-Feb–Apr-2022 (dev), HAR baselines, and VaR coverage.

### Power and dev-based expectations (stated before the test)
- **A1:** the 2024 IC standard error is ≈ 0.020, so the minimum detectable IC at t=2 is **0.040**. If the true IC equals dev's 0.068, power is ≈ 0.91.
- **A2 will very likely fail.** On dev, the spanning alpha is t = −0.32. The Chronos book's returns are explained by low-vol (t=6.6), 1-day continuation (−rev_1d, t=−4.0) and momentum (t=1.9). The classic signals explain 49% of MED_SIG's cross-sectional variance (rank correlation 0.53 with ar1, 0.49 with mom, −0.26 with rev_5d).
- **A3:** the dev Fama-MacBeth t is 1.80 over 731 days. Scaled to 247 test days, the expected t is ≈ 1.05, so power is ≈ **0.17**.
- **B1 will very likely fail.** On dev, Chronos is *worse* than EWMA (DM t=+2.35) and GARCH (t=+4.61) on raw QLIKE and tied after scaling. Its unconditional 1-step quantile calibration is excellent (q05 hit rate 0.0501, q10 0.1003, Kupiec p 0.95 / 0.82), but 21.5% of names reject Christoffersen independence.
- **Reading a fail:** a Track A fail means "no *incremental* alpha detectable in one year beyond known factors". It does not mean "Chronos has no IC". The Chronos IC is real on dev, but it is largely a known-factor mixture.

### Trials and holdout
- **Ledger.** Every evaluated Chronos variant is logged in [`trial_ledger.csv`](trial_ledger.csv). Re-runs of the same variant are not new trials.
- **After the test.** 2024 merges into dev for the Wave-1 improvements (plan Part 3). The **2025-01→2026-09 holdout** is opened once, at the end, for ≤2 pre-declared candidates per track, with Holm correction within each track.
- **Caveat.** The holdout window was previously used for one 18-ticker directional check (UNAC). That was not a portfolio test, so the contamination is mild.

### Deviations from the approved plan (all made before any test-period number was seen)
- **Model call:** `predict_quantiles` (a list of 1-D arrays) instead of `predict_df`. It is the same model call and avoids synthetic timestamps.
- **Data loading:** `alpha_lib` reads the Parquet directly and has its own 20-line ISS fetch for MCFTR, instead of sourcing all 45 cells of `lib.ipynb`. This keeps the library importable and testable.
- **Smoke run:** it used all eligible names instead of 10 tickers, so every downstream statistic had a real cross-section.
- **Fixes found in checks:**
  - the 2022-01-07 calendar fix
  - quantile rearrangement
  - a pandas-3 NaN-counting bug in VaR coverage (a regression test was added)
  - a HAR floor of 10% of its monthly level instead of 1e-8
<!-- PREREG_END -->

## Results

_(appended after the test stage)_
