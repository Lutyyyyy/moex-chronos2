# MOEX × Chronos-2: two-page summary

**Question.** Can a pretrained time-series foundation model, Amazon's Chronos-2, beat standard quant tools on
Moscow Exchange stocks: for direction, for alpha, or for risk?

**Answer.** No edge in any of the three. For risk, it reaches the level of the best classical models (a
confirmed non-inferiority result), but not beyond. Every claim was pre-registered and tested on data held out
until the end, and the held-out data overturned two promising dev-period results.

## The three studies

| Study | Test | Result |
|---|---|---|
| 1. Directional accuracy | Does Chronos-2 call the sign of the next return, per ticker? ~10 axes (resolution, grouping, price adjustment, context, sectors, lead-lag), 70 configs, 2025 holdout | **No.** Chance-level, replicated null |
| 2. Return alpha | Do its quantile forecasts rank stocks into a profitable long-short book, beyond momentum/low-vol/AR(1)? One-shot 2024 test + 20-configuration sweep, 238 logged trials | **Real IC (0.07–0.09), no tradable alpha.** Mostly known factors; the Chronos-specific part loses money net of costs |
| 3. Risk | VaR/ES, vol targeting, minimum-variance portfolio, hedging; zero-shot, calibrated, mixed, multivariate, covariates, LoRA fine-tuned. 265 logged dev trials, pre-registered 2025–26 holdout opened once | **Parity, no advantage.** Not worse than the best classical model for VaR and hedging; not significantly better anywhere |

## Risk study: the holdout (2025-01 → 2026-09)

| Use | Chronos (frozen arm) | Best classical | Verdict |
|---|---|---|---|
| 1-day VaR/ES (FZ0, lower is better) | **−3.082** | FHS log-HAR −3.070 | not worse ✅ (p 8e-17); better not significant (t −1.34) |
| Hedging with the IMOEX future (hedged vol) | **31.13%** | rolling OLS beta 31.30% | not worse ✅ (p 8e-6); better not significant (t −1.01) |
| Minimum-variance portfolio (vol) | 17.74% | **EWMA 16.85%** | worse, not significant |
| Vol targeting (fee vs EWMA) | +243 bps/yr | log-HAR on portfolio RV: Chronos trails by 128 bps | no claim |

![Holdout: Chronos vs classical](figures/risk_holdout_forest.png)

**What the holdout overturned.**
- **Calm-day VaR edge:** dev t −4.0 → holdout t −1.3 (pre-registered claim, p 0.095). The best of 265 variants
  looks better than it is.
- **LoRA fine-tuning:** better than zero-shot in 21 of 22 dev arms → reversed sign for VaR on the holdout.

**What mattered in the model setup.** The forecast target and the use of the output, not how series are
grouped: log realized variance rather than returns, and a 50/50 mix with a classical model. Cross-ticker
attention did not help direction, ranking or VaR, and joint return + variance forecasting helped VaR slightly
while hurting volatility forecasts ([FINDINGS, section 4](../FINDINGS.md#4-which-chronos-2-modes-worked)).

## How it was done
- **Data** (own pipeline on MOEX AlgoPack, with tests):
  - the daily "close" in the feed is an evening-session print, so prices are rebuilt from main-session
    10-minute bars;
  - dividend adjustment timing, including an announced dividend that was never paid;
  - holiday forward-fill removed (it creates fake zero returns);
  - futures roll masking;
  - the Epps bias of realized covariance from asynchronous 10-minute trades.
- **Protocol:**
  - selection only on dev, with every variant logged;
  - pre-registration committed before the holdout; the code refuses to open the holdout without it, or a
    second time;
  - claims separated into "better than weak baselines", "better than the best classical model"
    (Holm-corrected) and "not worse" (non-inferiority with margins fixed on dev).
- **Statistics:** Diebold-Mariano and Giacomini-White tests with Newey-West errors, FZ0 scoring and the
  Acerbi-Szekely backtest for VaR/ES, Kupiec and Christoffersen coverage tests, Fleming-Kirby-Ostdiek
  performance fees, stationary bootstrap, a real-time stress-regime rule.
- **Models:** Chronos-2 in univariate, cross-learning, multivariate and covariate modes; conformal and rolling
  calibration; forecast mixtures; a one-factor covariance model; LoRA fine-tuning on Colab (GPU/CPU parity
  checked, yearly refits trained only on past data). Classical rivals: EWMA/RiskMetrics, GARCH(-t), filtered
  historical simulation, HAR and log-HAR, rolling OLS beta.

## Mistakes found and fixed before the holdout
- An evaluation universe that silently dropped the 2022 crash months (caught by a dry run of the holdout code).
- A median-based calibration bias (vol-targeted books ran at 18–20% instead of 10%).
- A spurious market-factor artifact in the directional study.

All are documented with before/after tables in the study READMEs.

## Links
Repository README · study READMEs under `forecasting/` · result tables under each study's `results/` ·
figures regenerate with `forecasting/risk_experiment/make_figures.py`.
