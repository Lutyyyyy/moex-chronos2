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

### Further data corrections (2026-09-24, before Phase C)
- **Unpaid dividend:** MGNT's 560 RUB 9M2024 dividend (2025-01-09) was never approved: the EGM on 2024-12-26 failed for lack of quorum. It is excluded via `KNOWN_UNPAID_DIVIDENDS`.
- **Future record dates:** dividends whose record date falls after the last trading day are no longer applied. They had produced fake +3–8% jumps on 2026-09-17 for TATN, TATNP, NVTK, SIBN and BSPB, in the holdout panel only.
- **Verification:** the dev panel returns are byte-identical after these fixes.

All results below use the corrected data, over **ext_dev = 2021–2024** (2024 was merged into dev after the one-shot test, as pre-registered).

### Phase C: Chronos configuration sweep (ext_dev 2021–2024)
Sixteen configurations were run through the same frozen pipeline. The universe is the baseline's own evaluation mask, so coverage is 1.0 for all. Winners were selected by rules fixed in code before the sweep ran:
- **Track A:** the highest `fm_t_over_uni`, provided it exceeds 2. This is the Fama-MacBeth t of the config's MED_SIG, controlling for the uni Chronos signal plus mom, rev_5d, rev_1d, lowvol and size.
- **Track B:** the most negative scaled-QLIKE DM t vs uni, provided it is below −2. Only configs with a comparable target qualify.
- **Follow-up (C3b):** context lengths 128 and 512 were then re-run on each winner.

| Config | What changes vs uni | IC t | FM t | FM t over uni | Spanning t | Net Sharpe | QLIKE-sc DM t vs uni |
|---|---|---:|---:|---:|---:|---:|---:|
| uni | univariate, target only, context 250 | 6.37 | 2.70 | — | −0.15 | 1.17 | — |
| xl | cross_learning over the full cross-section | 5.47 | 3.18 | 1.88 | −1.02 | 1.01 | −3.77 |
| cov | past covariates: IMOEX return, own Δlog traded value | 6.39 | 3.51 | 2.60 | −0.22 | 1.26 | −3.15 |
| xl_cov | xl + cov | 6.20 | 3.23 | 2.61 | −0.40 | 1.47 | −1.41 |
| xl_sector | cross_learning within sectors | 5.99 | 3.07 | 2.52 | −0.50 | 1.19 | −1.86 |
| xl_market | cross_learning, with the market series (IMOEX, sector indexes, BR/Si/GD) added to the group | 5.70 | 3.44 | 2.39 | −0.95 | 1.19 | −3.72 |
| xl_liq | cross_learning within liquidity halves | 5.36 | 2.37 | 1.09 | −1.42 | 0.90 | **−5.23** |
| xl_rand20 | cross_learning within random ~20-name groups | 6.11 | 3.47 | 2.20 | −0.53 | 1.18 | −3.99 |
| cov_sector | cov + own-sector index return | 6.48 | 3.69 | 2.74 | 0.18 | 1.34 | −3.53 |
| **cov_fut** | cov_sector + Brent / USD-RUB / gold futures (roll-masked) | 6.96 | 4.70 | **4.09** | 0.82 | 1.57 | −4.47 |
| ctx64 / ctx128 / ctx512 | context length | 4.79 / 4.76 / 5.40 | 2.76 / 2.23 / 1.77 | 1.89 / 0.77 / −0.48 | −1.39 / −1.94 / −0.45 | 1.22 / 0.80 / 0.77 | 0.13 / −0.77 / 0.27 |
| resid | leave-one-out market-residual target | 5.77 | 3.35 | 2.22 | −0.20 | 1.82 | 1.23 |
| weekly | weekly-aggregated target | 5.39 | 3.18 | 2.28 | −0.34 | 1.24 | 1.61 |
| logprice | log-price target | 2.59 | 1.02 | 0.06 | −0.51 | −0.15 | 1.06 |
| cov_fut_ctx128 / 512 | C3b follow-up | 5.75 / 6.33 | 4.26 / 3.23 | 3.21 / 1.83 | −0.47 / 0.07 | 1.41 / 1.20 | −4.63 / −2.99 |
| xl_liq_ctx128 / 512 | C3b follow-up | 5.58 / 4.69 | 3.25 / 1.74 | 1.88 / 0.14 | −1.73 / −1.74 | 1.02 / 0.59 | −3.74 / −3.15 |

The full table, including IC means, QLIKE and pinball loss, is in `forecasting/runs/alpha_variants/configs_map.csv`.

**Winners (unchanged after C3b):** Track A = `cov_fut`, Track B = `xl_liq`.
- **No configuration has a net spanning alpha t above 0.82.** Covariates improve the ranking, cross-learning improves the return-based σ, and none of it adds net return beyond the classic books.

### Step 3: improvements on the winners (and on uni and cov for reference)
- **Chronos-mimic.** A causal rolling cross-sectional regression of MED_SIG on cheap trailing statistics of each name's own history. The *extended* mimic adds the covariate information Chronos saw:
  - trailing 250-day β to IMOEX;
  - traded-value dynamics;
  - own-sector index trend;
  - per-name exposure × trend of BR, Si, GD and IMOEX.

  The residual, `chronos_minus_mimic_ext`, is the Chronos-specific part, and it goes through the identical evaluation. **Caveat (independent review):** the mimic is linear, so the residual is an *upper bound* on Chronos-specific skill. It can include nonlinear use of the same inputs.
- **Combination.** A causal rolling Fama-MacBeth-weighted composite of the classic signals, with and without Chronos.
- **Turnover control.** EMA smoothing (half-life 5/10/21 days) and monthly rebalancing.

| Signal | uni | cov | **cov_fut (winner A)** | xl_liq (winner B) |
|---|---|---|---|---|
| Chronos: FM t / spanning t / net SR | 2.70 / −0.15 / 1.17 | 3.51 / −0.22 / 1.26 | 4.70 / 0.82 / 1.57 | 2.37 / −1.42 / 0.90 |
| Mimic out-of-sample R² (plain / extended) | 0.45 / — | 0.44 / 0.47 | 0.44 / 0.47 | 0.39 / 0.42 |
| Mimic: net SR / spanning t | 1.99 / 1.56 | 2.04 / 1.73 | 2.06 / 1.44 | 2.17 / 1.58 |
| Chronos − mimic: FM t | 0.69 | 1.72 | 2.76 | 0.26 |
| **Chronos − extended mimic: FM t / spanning t / net SR** | — | 1.49 / −1.41 / −0.67 | **2.47 / −0.43 / −0.38** | 0.31 / −2.18 / −1.29 |
| Combo: Chronos mean weight / alpha over classic combo t | 0.0007 / −0.55 | 0.0010 / −0.36 | 0.0020 / −0.12 | 0.0007 / −1.69 |
| Best turnover-controlled variant (spanning t) | hl5: 0.42 | hl5: 0.77 | hl5: 1.46 | hl5: 0.40 |

**Quantile-shape signals.** These are skew, up/down asymmetry, tail weight, downside and P(up) from the 21 quantiles.
- On uni, the shape signals' Chronos-specific FM t values range from −1.33 to +1.09, so none is significant.
- On cov_fut, only P(up) is strong: IC t 7.05, and its specific part has FM t 3.65. But P(up) is another reading of the same location forecast. Controlling for MED_SIG its FM t is 1.68, and its spanning t is 0.84.
- Robust-spread σ (IQR-based) is no better than the moment-based σ.

**Return-based σ, calibrated** (step 3 vol calibration, a causal rolling scale). Calibration helps Chronos itself: DM t vs raw is −2.3 (cov_fut) and −2.2 (xl_liq). When EWMA and GARCH are calibrated the same way, Chronos is **not better**: DM t is −0.88 / −0.30 (cov_fut) and −0.95 / −0.74 (xl_liq).

### `cov_fut` robustness checks (diagnostics, not new trials; [`diagnostics/covfut_stability.py`](diagnostics/covfut_stability.py))
- **Look-ahead audit: clean.**
  - The ISS daily closes of the sector indexes (MOEXOG/MM/FN) and of IMOEX equal the ≤18:50 main-session close on 99–100% of 2020–2024 days.
  - The futures use the same ≤18:50 window, and returns across a contract roll are masked.
  - The zero-filled covariate share on ext_dev is BR 4.8%, Si 1.6%, GD 1.6%.
  - An independent code review found the covariate slicing, the mimic fit and the evaluation masks causal and identical across configs.
- **Stability:** FM t over uni by year is 2021 2.34, 2022 2.63, 2023 1.73, 2024 1.93, and 3.46 excluding Feb–Apr 2022.
- **Cost / lag sweep:** the long-short spanning t at 0 / 5 / 10 / 20 bps is 1.71 / 0.82 / −0.07 / −1.82 at lag 1, and 1.52 / 0.67 / −0.18 / −1.85 at lag 0. It is **never above 2, even at zero cost.**

### Vol track: Chronos on realized variance
- **RV target (`rvtarget`).** Chronos run on the log realized-variance series, with the E[exp] quantile integral for the level. Raw QLIKE:

  | Model | QLIKE |
  |---|---|
  | chronos_rv_xl | **0.501** |
  | chronos_rv_uni | 0.504 |
  | HAR-RV | 0.648 |
  | GARCH | 0.729 |
  | HAR-daily | 0.765 |
  | Chronos return-based xl | 0.810 |
  | EWMA | 0.853 |

  chronos_rv_xl beats EWMA, GARCH, HAR-daily and HAR-RV with DM t −3.6 / −2.6 / −2.6 / −5.1, and the result holds after calibration.
- **Economic value (`rvecon`).** The four Track B uses (low-vol factor, inverse-vol equal weight, vol-target overlays on equal weight and on momentum) were sized with each model's forecast. Chronos-RV beats EWMA in none of them (bootstrap p 0.33–0.98).
- **Attribution (`volattr`): log-HAR matches Chronos-RV.**
  - **Pooled + market log-HAR** has QLIKE 0.455, against 0.502 for Chronos-RV xl (DM t +0.78, not significant).
  - **Per-name log-HAR** has QLIKE 0.486 (DM t +1.35).
  - **Mechanism:** Chronos's edge over EWMA and GARCH comes from working in log space and pooling across names, and classical models can do both.
  - **By regime, against per-name log-HAR:** Chronos is better in calm years (2021 DM t −1.71, 2023 −1.60) and worse in the 2022 shock (+1.67). Against pooled + market log-HAR the per-year DM t values are −3.10 / +0.88 / −2.23 / +0.78 for 2021–2024. The pattern is the same: Chronos is better in calm years, but not in 2022 or 2024.
- **Encompassing test,** pre-registered in [`prereg_vol_encompassing.md`](prereg_vol_encompassing.md) (commit `00dfa0a`); code in [`vol_encompassing.py`](vol_encompassing.py).
  - **E1 passes:** regressing log 5-day RV on log Chronos-RV and log log-HAR(pooled+mkt) with Driscoll-Kraay errors gives b_Chronos 0.56 (t 4.33) against b_logHAR 0.30 (t 1.97). By year, Chronos's t is 7.2 / 2.5 / 8.0 / 5.6.
  - **E2 fails:** the equal-weight geometric combination has QLIKE 0.467 against log-HAR's 0.455 (DM t +0.43).
  - **Pre-registered verdict:** "statistically distinct but practically negligible". No holdout.
- **Calibration upper bound** (a diagnostic with hindsight in-sample fits, not a trial; [`diagnostics/vol_calib_bound.py`](diagnostics/vol_calib_bound.py)).
  - **QLIKE-optimal fits:** log-HAR alone 0.4362; Chronos alone 0.4607; the combination 0.4354, with weight 0.16 on Chronos and DM t −0.13 vs log-HAR.
  - **By year, combination vs log-HAR:** 2021 DM t −5.2, 2022 +0.4, 2023 −3.6, 2024 −5.9. There is a gain of about 2% in calm years, and the 2022 shock dominates the pooled mean.
  - **Calibrating log-HAR itself** gains about 4%, which is more than Chronos adds.

### Trials and multiplicity
The ledger holds **238 rows**: Track A 140 (dev 8, test 4, ext_dev 128) and Track B 98 (dev 8, test 8, ext_dev 82).
- The Track A winner's specific-part t of 2.47 is the best of 20 configurations. A Bonferroni bound over 20 would need |t| ≈ 3.0.
- The diagnostics and the calibration upper bound add no trials.

## Final verdict (2026-09-24): experiment CLOSED

- **Return alpha: not tradable.**
  - Chronos-2 quantile forecasts rank MOEX stocks with a real IC (0.07–0.08, t 6–7).
  - Most of it is a mixture of known factors that a linear mimic reproduces, and the mimic trades better.
  - The best configuration (`cov_fut`) keeps a Chronos-specific component (FM t 2.47, an upper bound given the linear mimic, and fragile after 20 configurations). That component has negative net Sharpe (−0.38) and no spanning alpha (t −0.43).
  - No variant tried (covariates, cross-learning, context, targets, quantile shapes, combination, turnover control) yields net alpha beyond the classic books, even at zero cost.
- **Vol forecasting: a good off-the-shelf model, matched by log-HAR.**
  - Chronos on log realized variance beats EWMA, GARCH and HAR, and carries information that log-HAR lacks, mostly in calm regimes.
  - But a well-specified log-HAR matches it on QLIKE, and no portfolio use shows an economic gain.
- **Holdout (2025-01 → 2026-09): never opened.** Per the user's decision, return alpha gets no holdout, and the window is reserved for the follow-up risk study (VaR/ES, vol targeting, minimum-variance portfolio and hedging; calibration, mixtures, multivariate targets and LoRA fine-tuning), planned in `tmp/plans/risk_experiment.md`.
