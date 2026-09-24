# MOEX × Chronos-2

Can a pretrained time-series foundation model, [Chronos-2](https://arxiv.org/abs/2510.15821), beat standard
quant tools on Moscow Exchange stocks? The model is tried zero-shot, calibrated, mixed with classical
models and LoRA fine-tuned. The repo runs three studies, each with success criteria written down before
the test data was touched and a holdout period opened only at the end.

| Study | Question | Answer |
|---|---|---|
| **1. Directional accuracy** ([FINDINGS.md](FINDINGS.md)) | Does Chronos-2 predict the *sign* of the next return? | **No.** A replicated null across ~10 axes: resolution, grouping, price adjustment, context length, sectors, lead-lag. |
| **2. Return alpha** ([alpha_experiment](forecasting/alpha_experiment/README.md)) | Do its quantile forecasts rank stocks well enough for a profitable long-short book? | **No tradable alpha.** The rank IC is real (0.07 on 2021–23, 0.09 on 2024), but it is mostly known factors (low-vol, momentum, AR(1)) in disguise. The Chronos-specific part has net Sharpe −0.38 and no spanning alpha. |
| **3. Risk** ([risk_experiment](forecasting/risk_experiment/README.md)) | Does it help with VaR/ES, vol targeting, minimum-variance portfolios or hedging? | **Holdout pending.** On 2021–24: on par with the best classical model in every use, never significantly better overall. Better than it for 1-day VaR on calm days, worse in the 2022 crash. LoRA fine-tuning on log-RV adds nothing measurable (the multivariate fine-tune is still running). |

<!-- RESULT: replace the Study 3 answer with the holdout verdict once the holdout is opened -->

![Chronos vs classical risk models, dev period](docs/figures/risk_dev_forest.png)

_Loss difference with a 95% confidence interval, per use (left of 0 means the first model is better).
Dev period 2021–24; the holdout figure is added once the holdout is opened._

## What the project demonstrates
- **Evaluation discipline:**
  - the pre-registration is committed before the holdout data is used;
  - the holdout is opened once, and the code refuses a second run;
  - a trial ledger counts every variant tried (238 in the alpha study, 204+ in the risk study);
  - multiple-testing correction (Benjamini-Hochberg, Holm);
  - claims keep "beats weak baselines" apart from "beats the best classical model".
- **Market-data engineering**, where several traps were not obvious:
  - The daily "close" in the data feed is the evening-session print, so the daily panel is rebuilt from
    main-session 10-minute bars.
  - Dividend adjustment timing, including a dividend that was announced but never paid.
  - Holiday forward-filling creates fake zero returns.
  - Futures returns across contract rolls must be masked.
  - Realized variance from asynchronous 10-minute trades is biased (the Epps effect).
- **Methods:**
  - forecast comparison with autocorrelation-robust tests (Diebold-Mariano, Giacomini-White, Newey-West);
  - proper scoring rules for VaR/ES (FZ0, Acerbi-Szekely);
  - economic value measured as a performance fee;
  - causal calibration and forecast mixtures;
  - LoRA fine-tuning on Colab, with yearly refits trained only on past data.
- **Honest negative results.** Bugs found mid-project are documented in each study's README:
  - a spurious market-factor artifact;
  - a median bias in single-series calibration;
  - an evaluation-universe gap that silently dropped the 2022 crash months.

## Repository layout
```
data_pipeline/            MOEX AlgoPack extraction: candles, covariates, universe selection, price adjustment; tests
forecasting/
  lib.ipynb, run.ipynb, configs/   study 1: config-driven directional-accuracy runs (70 configs)
  holdout_unac_experiment/         study 1: 2025 holdout confirmation
  alpha_experiment/                study 2: code, tests, pre-registration, results/
  risk_experiment/                 study 3: code, tests, Colab LoRA bundle builder, results/
docs/                     figures, design notes (lead-lag research), archive
```

An earlier fine-tuning attempt through AutoGluon was paused and is not part of this repo (see
FINDINGS.md, "Fine-tuning"). Study 3's LoRA fine-tuning replaces it.

## Reproducing
Install with `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt` (Python 3.12).

No market data is included, because MOEX AlgoPack data can't be redistributed. With an AlgoPack key in
`data_pipeline/.env`:
1. **Data:** run `data_pipeline/` (see [docs/usage.md](data_pipeline/docs/usage.md)).
2. **Directional accuracy:** in `forecasting/run.ipynb`, point `CONFIG_PATH` at a file under `configs/`.
3. **Alpha study:** `forecasting/alpha_experiment/run_all.sh`.
4. **Risk study:** `forecasting/risk_experiment/risk_run.py <stage>` (stages are listed at the end of the
   file). LoRA runs in Colab from a generated bundle (`colab/make_bundle.py`).
5. **Tests** (offline, no data needed): `pytest data_pipeline forecasting/alpha_experiment/tests
   forecasting/risk_experiment/tests`.

Result tables (small CSVs) are committed under each study's `results/`. Figures regenerate with
`forecasting/risk_experiment/make_figures.py`.
