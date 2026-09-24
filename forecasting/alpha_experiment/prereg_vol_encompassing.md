# Pre-registration: does Chronos-RV carry vol information beyond log-HAR?

This file is written and committed before the test is run. Code: `vol_encompassing.py`.

**Motivation.** `volattr` found that `chronos_rv_xl` and `loghar_pooled_mkt` have indistinguishable QLIKE (DM t +0.78). They win in different regimes: Chronos is better in 2021 and 2023, log-HAR in the 2022 shock. So a combination might beat both. This test asks whether Chronos's forecast is *encompassed* by the best classical model.

**Setup.** It is fixed and identical to `stage_volattr`:
- **Period:** ext_dev 2021-01-01 → 2024-12-31. Signal dates come from `ic_dates(..., steps 1..5)`.
- **Mask:** the base eligibility mask, with every model's forecast non-missing. This is the same mask `m` as in `stage_volattr`.
- **Target:** y = log(Σ_{h=1..5} RV_{d+h}).
- **Forecasts:**
  - C = log(`chronos_rv_xl` 5-day variance forecast);
  - L = log(`loghar_pooled_mkt` forecast), cached in `alpha_improve/rvtarget/loghar_cache.parquet`.

**Primary test (E1: information).**
- **Regression:** pooled panel OLS of y = a + b_C·C + b_L·L.
- **Standard errors:** Driscoll-Kraay, meaning per-date score sums with Newey-West lag 8.
- **E1 passes if** b_C > 0 and t(b_C) > 2.

**Secondary test (E2: usefulness in the loss that matters).**
- **Combination:** a fixed equal-weight geometric combination, exp((C+L)/2). It has no fitted parameters.
- **Comparison:** QLIKE on the 5-day RV target against `loghar_pooled_mkt`.
- **E2 passes if** the Diebold-Mariano t is below −2 (the combination is better).

**Decision.**
- **E1 and E2 both pass:** "Chronos adds vol information that the best classical model misses, and it helps in practice". This makes it a candidate for the 2025+ holdout, which is still sealed and would need a separate pre-registration before it is opened.
- **E1 passes, E2 fails:** "statistically distinct but practically negligible". This is reported, but there is no holdout.
- **E1 fails:** the vol track is closed. Chronos-RV is encompassed by log-HAR.

**Reported, not gated:**
- b_C and t by year;
- the same regression against per-name `loghar`;
- b_C and t excluding Feb–Apr 2022.

**Trial count.** This adds 2 trials (E1 and E2) to `trial_ledger.csv` as track B, tag `S3volenc`.
