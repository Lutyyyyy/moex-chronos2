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

### 2024 test gate: run once on 2026-09-24, after pre-registration commit `f3ee7e3`

| Leg | Statistic | 2024 value | Threshold | Verdict |
|---|---|---:|---:|---|
| A1 | IC Newey-West t (mean IC 0.096) | **3.54** | > 2 | pass |
| A2 | net spanning alpha t (−1.9% p.a.) | **−0.55** | > 2 | **FAIL** |
| A3 | Fama-MacBeth Chronos t | **2.61** | > 2 | pass |
| B1 | DM p, Chronos better: raw vs EWMA / GARCH; scaled vs EWMA / GARCH | 0.71 / 0.99; 1.00 / 0.049 | all < 0.05 | **FAIL** |
| B2 | bootstrap p, Chronos low-vol book > EWMA twin (ΔSharpe −0.63) | 0.86 | < 0.05 | **FAIL** |

**Track A: FAIL. Track B: FAIL.** Neither track earns a "useful alpha generator" claim.

### What the 2024 numbers say

**Track A**

The Chronos ranking signal is **informative but not monetizable beyond known factors**.
- **IC:** mean IC 0.096. That is higher than any classic signal in 2024 (mom 0.050, lowvol 0.080, ar1 0.070).
- **Incremental information:** it keeps a significant Fama-MacBeth coefficient after controlling for momentum, reversal, low-vol and size (t=2.61). A3 did better than its predicted power of 0.17.
- **The book:** the beta-neutral long-short book earned gross Sharpe 1.82 and **net 1.06** at 10 bps round trip plus 5% borrow.
- **Why it is not alpha:**
  - **AR(1) does better net.** The AR(1) baseline, essentially the trailing-250-day mean, earned **net 1.16** with 9.7× turnover against Chronos's 26×. Chronos's cost breakeven is 25 bps one-way, versus 76 bps for AR(1).
  - **The returns are spanned.** The Chronos net returns load on the AR(1) book (β=0.58, t=3.0) and low-vol (β=0.21, t=4.8), leaving an alpha of −1.9% p.a. (t=−0.55).
  - **It is small even before costs.** Post-hoc and not gated: the *gross* spanning alpha is only +1.8% p.a. (t=0.56) in 2024 and +3.5% (t=1.47) on dev.
- **Long-only:** the top quintile beat the equal-weight universe by +6.4% p.a. (IR 0.86, CAPM alpha t=0.84). This is not significant, in a year when IMOEX (price) fell 7.0% and MCFTR (total return) rose 1.6%, while cash at the key rate earned 17.6%. So every long-only book had a negative excess return.

**Track B**

Chronos's return-based σ is **not a better risk model** than EWMA or GARCH(1,1).
- **Raw QLIKE:** it loses to GARCH (DM t=+2.3, Chronos worse) and ties EWMA.
- **Level-adjusted QLIKE:** it beats GARCH narrowly (p=0.049) but loses clearly to EWMA (t=+3.6).
- **Calibration broke in 2024:** the 1-step q05 hit rate was 6.6% and q10 12.2% (Kupiec p≈0), versus 5.0% and 10.0% on dev. The quantiles were too narrow in a rising-volatility year.
- **Economic value:** no economic use beat its EWMA twin.

**Reading.**
- **Track A:** the per-ticker directional null in FINDINGS.md does *not* carry over to cross-sectional ranking, where Chronos has real IC. Most of that IC is a repackaging of trend/drift and low-vol that a one-line AR(1)/momentum rule captures more cheaply. The incremental part is statistically detectable (A3) but too small, and too expensive to trade at weekly frequency, to add alpha (A2).
- **Track B:** zero-shot Chronos σ from daily returns is no better than a 1990s EWMA.

Detailed tables are in `forecasting/runs/alpha_test/` (gitignored, reproducible with `alpha_run.py test` after deleting that dir; the code refuses a silent rerun). The trial ledger has all 8 dev trials and 6 test rows.

### Data corrections found after the v1 test (2026-09-24), before any re-run

A second data audit, prompted by review of the v1 results, found two real bugs. Both affected v1's dev and test numbers equally for Chronos and every baseline.

**1. Dividend adjustment one trading day late before 2023-07-31** (in `data_pipeline`)
- **Cause:** the poptimizer `day` field is the *register* date, but it was used as the ex-date.
- **Effect:** under T+2 settlement the price gap happens one trading day earlier. So `close_adj` carried a spurious −div / +div pair around every pre-T+1 dividend.
  - Across 133 events with yield above 2%, the mean was −5.0% then +6.8%.
  - The worst case was GAZP 2022-10: −20.7%, then +36.8%.
- **Fix:** `ex_date_from_record` derives the ex-date from the settlement regime (T+2 → T+1 switch on 2023-07-31).
- **Missing records added:** 5 verified dividends that the dump lacked (SVCB ×2, WUSH ×2, RUAL).
- **Verified after the fix** on 288 events: adjusted returns the day before and after the ex-date are ≈0 (±0.2%). The ex-day residual of +1.0–1.6% is the expected gross-vs-after-tax dividend gap.
- **Not changed:** same-date multiple rows in the dump were checked. They are genuine separate declarations or components that sum to the official amount, not duplicates.

**2. Calendar dropped 9 real trading days** (in `alpha_lib.trading_calendar`)
- **Which days:** the 2022-03-24..30 shortened reopening sessions, and the official working Saturdays 2021-02-20, 2024-04-27, 2024-11-02 and 2024-12-28.
- **Cause:** the rule required a bar at or after 18:30 on a weekday. The new rule is at least 20 IMOEX main-session bars on any day.
- **Also changed:** the index-only-day filter threshold went from 50% to 20% of the usual share prints. This still drops 2022-01-07 (0 prints) and keeps the partial 2022-03-24/25 reopening (49%).
- **Effect on the panel:** 1,240 → 1,249 days. The v1 panel is kept in `forecasting/runs/alpha_data_v1/`.

**Consequences**
- The v1 gate numbers above were computed on the uncorrected data. They stay as recorded and are not edited.
- A corrected-data re-run of the same frozen pipeline has **not** been run yet. It will re-use 2024, and must be reported as such.
- The rebuilt `close_adj` also changes the inputs of every earlier experiment in `FINDINGS.md` that used `close_adj`. Their recorded results were not recomputed.

### Corrected-data re-run of the frozen v1 pipeline (2026-09-24): **same verdict**

Code, gate, selection rules and thresholds are identical to the pre-registration. Only the two data bugs above were fixed.
- **Forecasts:** 999 anchors and 353,772 rows, all present. One row had crossing quantiles (v1 had 9, all GAZP around the spurious dividend spike).
- **Primaries:** the frozen rules re-selected the same ones, `MED_SIG` and `lowvol_factor` (dev DSR 0.924 and ≈0, N=4 each).
- **Disclosure:** this **re-uses 2024**. It is reported as a data-corrected replication, not as a fresh test. Outputs are in `forecasting/runs/alpha_{dev,test}/`; v1 is kept in `*_v1/`. Ledger tags: `v1c_dev`, `v1c_test`.

| | v1 (uncorrected) | **v1c (corrected)** |
|---|---:|---:|
| Dev IC (NW t) | 0.068 (5.78) | 0.069 (5.75) |
| Dev spanning alpha t / FM t | −0.32 / 1.80 | 0.14 / 2.01 |
| **A1** 2024 IC NW t (mean IC) | 3.54 (0.096) | **3.21** (0.088) — pass |
| **A2** 2024 net spanning alpha t (p.a.) | −0.55 (−1.9%) | **−0.97** (−3.4%) — **FAIL** |
| **A3** 2024 Fama-MacBeth t | 2.61 | **2.18** — pass |
| 2024 Chronos long-short net / gross Sharpe | 1.06 / 1.82 | 0.81 / 1.58 |
| 2024 AR(1) long-short net Sharpe | 1.16 | 1.16 |
| Chronos turnover p.a. / cost breakeven | 26× / 25 bps | 26× / 20 bps |
| Long-only active vs equal-weight (IR, CAPM t) | +6.4% (0.86, 0.84) | +4.1% (0.55, 0.52) |
| **B1** DM p raw vs EWMA / GARCH; scaled vs EWMA / GARCH | 0.71 / 0.99; 1.00 / 0.049 | 0.73 / 0.98; 1.00 / 0.25 — **FAIL** |
| **B2** bootstrap p (ΔSharpe vs EWMA twin) | 0.86 (−0.63) | 0.81 (−0.48) — **FAIL** |
| 2024 q05 / q10 hit rate (dev) | 6.6% / 12.2% (5.0 / 10.0) | 6.7% / 12.2% (5.1 / 10.1) |

**Reading.** Correcting the data made Chronos slightly *worse* relative to the baselines. The spurious dividend reversals had been a small source of apparent predictability. The conclusions stand:
- **Track A:** real cross-sectional IC with a small incremental component (Fama-MacBeth t≈2). The net long-short book is spanned by the AR(1)/trailing-mean and low-vol books at 2.7× their turnover.
- **Track B:** Chronos σ from daily returns is not better than EWMA or GARCH(1,1), and its tails were too narrow in 2024.

### Next

The holdout (2025-01 → 2026-09) is **still sealed**. The improvement wave (plan Part 3, re-prioritized: Chronos-mimic, combination, turnover control, cross_learning, residual target, RV target for Track B) runs next on 2021–2024 corrected data.
