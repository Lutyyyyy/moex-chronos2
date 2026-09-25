# MOEX × Chronos-2

Can a pretrained time-series foundation model, [Chronos-2](https://arxiv.org/abs/2510.15821), beat standard
quant tools on Moscow Exchange stocks? The model is tried zero-shot, calibrated, mixed with classical
models and LoRA fine-tuned. The repo runs three studies, each with success criteria written down before
the test data was touched and a holdout period opened only at the end.

| Study | Question | Answer |
|---|---|---|
| **1. Directional accuracy** ([directional_experiment](forecasting/directional_experiment/README.md)) | Does Chronos-2 predict the *sign* of the next return? | **No.** A replicated null across ~10 axes: resolution, grouping, price adjustment, context length, sectors, lead-lag. |
| **2. Return alpha** ([alpha_experiment](forecasting/alpha_experiment/README.md)) | Do its quantile forecasts rank stocks well enough for a profitable long-short book? | **No tradable alpha.** The rank IC is real (0.07 on 2021–23, 0.09 on 2024), but it is mostly known factors (low-vol, momentum, AR(1)) in disguise. The Chronos-specific part has net Sharpe −0.38 and no spanning alpha. |
| **3. Risk** ([risk_experiment](forecasting/risk_experiment/README.md)) | Does it help with VaR/ES, vol targeting, minimum-variance portfolios or hedging? | **Parity, no advantage** (pre-registered holdout 2025–26). Not worse than the best classical model for VaR/ES and hedging (both non-inferiority claims pass, p < 1e-5), with the best point estimate in both, but no "better than" claim survives the multiple-testing correction. Dev-period edges (calm-day VaR, LoRA fine-tuning) shrank or vanished out of sample. |

Short version: **[docs/summary.md](docs/summary.md)** (two pages). Synthesis of all three studies:
**[FINDINGS.md](FINDINGS.md)**. Paper-style report with figures: **[docs/report/report.pdf](docs/report/report.pdf)** (8 pages).

![Chronos vs classical risk models, holdout](docs/figures/risk_holdout_forest.png)

_Risk study, holdout 2025-01 → 2026-09 (opened once): loss difference of the frozen Chronos arm vs the best
classical model and the standard baselines, with 95% confidence intervals (left of 0 means Chronos is better)._

## How the studies were run
- **Protocol:** all selection on a development period, with success criteria fixed before the test data was
  used; every variant tried is logged in a trial ledger (238 trials in the alpha study, 265 in the risk
  study); multiple testing corrected with Benjamini-Hochberg or Holm. The risk study's pre-registration was
  committed before its holdout was opened, the holdout was evaluated once with code that refuses a second run,
  and its claims are split into "better than weak baselines", "better than the best classical model" and
  "not worse" (non-inferiority with margins fixed on dev).
- **Tests:** Diebold-Mariano and Giacomini-White with Newey-West errors; FZ0 and Acerbi-Szekely for VaR/ES;
  Kupiec and Christoffersen coverage tests; performance fees for vol targeting; Fama-MacBeth and spanning
  regressions for alpha.
- **Models:** Chronos-2 in univariate, cross-learning, multivariate and covariate modes, calibrated, mixed with
  classical models, and LoRA fine-tuned on Colab with yearly refits trained only on past data. Classical
  rivals: EWMA/RiskMetrics, GARCH(-t), filtered historical simulation, HAR and log-HAR, rolling OLS beta,
  momentum / reversal / low-vol factors.
- **Data issues handled** (own pipeline on MOEX AlgoPack, with tests): the feed's daily close is an
  evening-session print, so daily prices are rebuilt from main-session 10-minute bars; dividend adjustment
  timing, including an announced dividend that was never paid; holiday forward-fill removed (it created zero
  returns); futures returns masked across contract rolls; the Epps bias of realized covariance from
  asynchronous 10-minute trades.
- Problems found during the work, and what each would have turned into without the check that caught it, are
  listed in [FINDINGS](FINDINGS.md#what-the-safeguards-caught).

## Repository layout
```
data_pipeline/            MOEX AlgoPack extraction: candles, covariates, universe selection, price adjustment; tests
forecasting/
  directional_experiment/          study 1: report, runner + cell library, 71 configs, per-run results/
  alpha_experiment/                study 2: code, tests, pre-registration, results/
  risk_experiment/                 study 3: code, tests, Colab LoRA bundle builder, results/
docs/                     2-page summary (summary.md), PDF report (report/, LaTeX source + figure script), figures
```

An earlier fine-tuning attempt through AutoGluon was paused and is not part of this repo (see
the study 1 report, [directional_experiment](forecasting/directional_experiment/README.md)). Study 3's LoRA fine-tuning replaces it.

## Reproducing
Install with `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt` (Python 3.12).

No market data is included, because MOEX AlgoPack data can't be redistributed. With an AlgoPack key in
`data_pipeline/.env`:
1. **Data:** run `data_pipeline/` (see [docs/usage.md](data_pipeline/docs/usage.md)).
2. **Directional accuracy:** in `forecasting/directional_experiment/run.ipynb`, point `CONFIG_PATH` at a file under `configs/`.
3. **Alpha study:** `forecasting/alpha_experiment/run_all.sh`.
4. **Risk study:** `forecasting/risk_experiment/risk_run.py <stage>` (stages are listed at the end of the
   file). LoRA runs in Colab from a generated bundle (`colab/make_bundle.py`).
5. **Tests** (offline, no data needed): `pytest data_pipeline forecasting/alpha_experiment/tests
   forecasting/risk_experiment/tests`.

Result tables (small CSVs) are committed under each study's `results/`. Figures regenerate with
`forecasting/risk_experiment/make_figures.py`.
