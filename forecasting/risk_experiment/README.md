# Chronos-2 as a risk model: pre-registration and results

**Question.** Is Chronos-2 useful for **risk** on MOEX equities, where the alpha experiment ([`../alpha_experiment/`](../alpha_experiment/README.md)) found return alpha not tradable? Chronos is tested zero-shot, calibrated, mixed with classical models, with multivariate [return, log-RV] input, and LoRA fine-tuned. If it is useful, is that in calm regimes, stress regimes, or both, and what exactly helps?

**Uses:**
- **U1:** 1-day VaR/ES (FZ0 loss, coverage tests, Basel traffic light).
- **U2:** vol targeting (Fleming-Kirby-Ostdiek performance fee).
- **U3:** minimum-variance portfolio (realized variance).
- **U4:** hedging with IMOEX futures (hedged variance).

**Claims (per use):**
- **L1:** beats EWMA **and** GARCH.
- **L2:** beats the best classical arm.
- Both are tested once on the sealed 2025-01 → 2026-09 holdout, after a pre-registration commit.

## Status

**Stage R0 (scaffold).** [`risk_lib.py`](risk_lib.py) holds the pure functions, tested in [`tests/`](tests/) with synthetic canaries. It covers:
- VaR/ES from the quantile grid;
- FZ0; Kupiec, Christoffersen and Acerbi-Szekely tests; Basel traffic light;
- the real-time stress indicator and the Giacomini-White test;
- conformal calibration and FHS;
- rolling and regime mixtures;
- GMV, the performance fee, and hedge ratios.

No data has been evaluated yet. The pre-registration block will be added here before any holdout forecast exists.

Plan: `tmp/plans/risk_experiment.md` (v3, kept locally).
