# Findings: Chronos-2 on MOEX equities

Can a pretrained time-series foundation model, [Chronos-2](https://arxiv.org/abs/2510.15821), beat standard quant
tools on Moscow Exchange stocks? Three studies, each building on the last, with success criteria fixed before the
test data was used and held-out data opened only at the end. This document is the synthesis; each study has its
own detailed report.

| Study | Question | Verdict | Report |
|---|---|---|---|
| **3. Risk** | Does it improve VaR/ES, vol targeting, minimum-variance portfolios or hedging? | **Parity, no advantage.** Not worse than the best classical model for VaR/ES and hedging (pre-registered non-inferiority, p < 1e-5); no "better than" claim survives the multiple-testing correction | [`risk_experiment/`](forecasting/risk_experiment/README.md) |
| **2. Cross-sectional alpha** | Do its quantile forecasts rank stocks into a profitable long-short book? | **No tradable alpha.** Real rank IC (≈ 0.07), mostly known factors; the Chronos-specific part loses money net of costs | [`alpha_experiment/`](forecasting/alpha_experiment/README.md) |
| **1. Directional accuracy** | Does it call the sign of each ticker's next return? | **No.** A replicated null across ~10 axes | [`forecasting/`](forecasting/README.md) |

## 1. Directional accuracy: a replicated null

The first question was the simplest: can zero-shot Chronos-2, with its cross-series attention, predict the
direction of MOEX returns? Directional accuracy (DA) was tested across ~10 axes (daily / 1h / 10-minute
resolution, multivariate vs. univariate grouping, raw vs. adjusted prices, context 35 / 100 / 250 bars,
cross-sector and single-sector baskets, and lead-lag structure) with walk-forward windows, naive baselines,
Benjamini-Hochberg correction and gates fixed before each run. The bar that matters is DA ≈ 0.536, the
break-even after trading costs.

- **Basket gate:** in eight runs (three resolutions, three context lengths), multivariate attention never beat
  univariate forecasting: |ΔDA| ≤ 0.0018 and 0 of 64 cells BH-significant in each.
- **Lead-lag:** a market-factor-residualized screen found 20 significant pairs on 2020–23; **0 of 20 replicated**
  on 2023–24 (best p_bh 0.70). Chronos on the same 18 tickers: mean DA 0.49–0.50.
- **Sectors:** 24 single-sector configs; one BH-significant cell, with the wrong sign.
- **The one exception:** UNAC at context 100 (DA 0.60–0.64, p_bh 0.0002) was re-tested on a fresh 2024-11 →
  2026-09 window. It fell to 0.545–0.569 (p_bh 0.26), and was traced to a one-ticker momentum regime, not a
  cross-asset dependency.

Chance-level DA (≈ 0.49–0.51) throughout, and 10-minute returns show no autocorrelation for the model to have
missed. The value of this study is that the process demonstrably could have caught an edge; the next question
was whether Chronos's forecast *distribution*, rather than its direction, carries usable information.

## 2. Cross-sectional alpha: Chronos-2 quantiles as signals and as a volatility model

Study 1 asked whether Chronos-2 can call each ticker's direction. A portfolio manager asks something different: do its **quantile forecasts**, turned into cross-sectional signals, earn net alpha beyond standard factors, or make a better volatility model? This follow-up tested that question in [`forecasting/alpha_experiment/`](forecasting/alpha_experiment/README.md).

**Setup.**
- **Data:** a daily panel on the **main-session close** (18:40 closing auction). 47–70 point-in-time-eligible liquid names.
- **Forecasts:** 21-quantile forecasts at every trading day.
- **Books:** weekly-rebalanced, beta-neutral long-short and long-only books, with 5 bps costs plus borrow.
- **Tests:** Fama-MacBeth and net spanning regressions against momentum / reversal / low-vol / AR(1) books. For volatility, QLIKE against intraday realized variance.
- **Protocol:** a pre-registered one-shot 2024 test, then an improvement wave on 2021–2024 with a trial ledger (238 rows). The 2025–26 holdout was reserved for study 3.

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

## 3. Risk: VaR, vol targeting, minimum-variance portfolios and hedging

Study 2 found Chronos-2 a good volatility model that log-HAR matches. The last open question was
whether that makes it useful for **risk decisions**, and whether calibration, mixing with classical models,
multivariate input, covariates or LoRA fine-tuning give it an edge. This study, in
[`forecasting/risk_experiment/`](forecasting/risk_experiment/README.md), used the sealed 2025–26 holdout.

**Setup.**
- **Uses:** 1-day VaR/ES at 5% for every stock (FZ0 loss); vol targeting an equal-weight book to 10%
  (Fleming-Kirby-Ostdiek performance fee); a long-only minimum-variance portfolio (realized 5-day variance);
  hedging each stock with the IMOEX future (hedged 5-day variance).
- **Arms:** zero-shot Chronos on returns, log realized variance and both jointly; calibrated and FHS versions;
  fixed, fitted and regime-dependent mixtures with the best classical model; a one-factor covariance model;
  market/macro covariates; and LoRA fine-tuning on Colab with yearly refits trained only on past data.
  Classical rivals: RiskMetrics/EWMA, GARCH(-t), FHS, HAR and log-HAR variants, rolling OLS beta.
- **Protocol:** all selection on 2021–24 (265 trials in the ledger), then a pre-registration committed before
  any holdout forecast existed, then one evaluation on 2025-01 → 2026-09 (395–433 forecast dates per use).
  - Family A, "better than": beat EWMA/RiskMetrics **and** GARCH (L1), then the best classical model (L2), plus a
    calm-day VaR claim (R); Holm-corrected across uses.
  - Family B, "not worse": non-inferiority against the best classical model, with margins fixed on dev.

**Result: parity with the best classical risk models, no demonstrated advantage.**

![Holdout: Chronos vs classical](docs/figures/risk_holdout_forest.png)

| Confirmatory claim (holdout) | Statistic | Raw p | After Holm |
|---|---|---|---|
| Not worse, VaR/ES (margin 0.063 FZ0) | mean(C − B) −0.012, upper 95% bound +0.003 | 8e-17 | ✅ pass |
| Not worse, hedging (margin +0.5 pp vol) | upper 95% bound 1.3e-5 vs margin 6.6e-5 | 8e-6 | ✅ pass |
| L1 VaR/ES: beats RiskMetrics and GARCH-t | t −1.87 / −2.37 | 0.031 | ❌ (needs ≤ 0.010) |
| R: VaR beats FHS log-HAR on calm days | t −1.31 (381 days) | 0.095 | ❌ |
| L1 vol targeting / GMV / hedging | see the table below | 0.71 / 0.92 / 0.48 | ❌ |

| Use (holdout) | Chronos arm | Best classical | Baselines |
|---|---|---|---|
| VaR/ES, FZ0 (lower is better) | **−3.082** (LoRA Chronos + FHS log-HAR mix) | FHS log-HAR −3.070 | GARCH-t −3.043, RiskMetrics −3.032 |
| 5% VaR hit rate (Kupiec p) | 4.77% (0.056) | 4.98% (0.90) | RiskMetrics 5.35% (0.004), GARCH-t 5.65% (1e-7) |
| Vol targeting, fee of Chronos (bps/yr) | one-factor Chronos | −128 vs log-HAR on portfolio RV | +243 vs EWMA, −72 vs GARCH |
| Minimum-variance portfolio, annual vol | 17.74% (LoRA Chronos + log-HAR mix) | **EWMA 16.85%** | GARCH 18.29% |
| Hedging, hedged annual vol | **31.13%** (Chronos + log-HAR mix, calibrated) | rolling OLS beta 31.30% | EWMA 31.14%, GARCH 31.62% |

- **Not worse, confirmed:** for VaR/ES and hedging, Chronos (mixed with a classical model) is not meaningfully
  worse than the best classical model, and has the best point estimate in both (not significant: t −1.34 and
  −1.01).
- **Not better:** no "better than" claim survives the Holm correction.
- **Where it loses:** plain EWMA stays best for minimum-variance portfolios, and GARCH and a log-HAR portfolio
  model beat the Chronos vol-targeting book.

**Which variants helped (dev, 2021–24).**
- **Mixing** Chronos 50/50 with a classical model beat Chronos alone in every use; three of the four frozen
  Chronos arms are such mixtures (the fourth, for vol targeting, is a one-factor covariance model).
- **Multivariate input** (returns and log realized variance forecast jointly) was the best zero-shot source for
  VaR; its LoRA fine-tuned version was frozen for VaR and minimum-variance.
- **No measurable gain:** past covariates (IMOEX, Brent, USD/RUB and gold volatility), a Chronos model of the
  correlation side (market and residual variance), and fine-tuning on log-RV alone.
- **Only weak baselines were beaten significantly** on dev (RiskMetrics, GARCH-t, GARCH); against the best
  classical model every use was within noise.

**The dev period over-stated Chronos, and the holdout caught it.**
- **Calm-day VaR:** Chronos beat FHS log-HAR on calm days with dev t −4.0; the pre-registered holdout claim gave
  t −1.3 (p 0.095). A winner's curse from picking the best of 265 variants.
- **Fine-tuning:** multivariate LoRA fine-tuning (returns and log-RV jointly) beat zero-shot Chronos in 21 of 22
  arms on 2022–24. On the holdout the VaR gain reversed sign (t +1.07) and the GMV gain was insignificant.
  Fine-tuning on log-RV alone never helped.
- **Regimes:** "better in calm, worse in stress" held on dev; on the holdout it reversed for GMV.

## What the evaluation discipline caught

Each of these would have become a reported "finding" without the safeguard that caught it:

| Safeguard | What it caught |
|---|---|
| Discovery/confirmation split + BH | A lead-lag shortlist where 19 of 20 pairs shared the same 3-bar lag: a market factor (lag-3 autocorrelation ≈ 0.16), not pairwise structure. Residualization kept 2 of 20 |
| Fresh holdout + mechanism check | UNAC's DA 0.60–0.64 clearing every gate; on new data 0.545–0.569, explained by UNAC's own momentum after a +157% spike (a naive sign rule rose and fell the same way) |
| Dry run of the holdout code on dev | An evaluation universe that silently dropped the 2022 crash months (regime mixtures undefined there); fixed and re-scored before the holdout opened |
| Single-use pre-registered holdout | A calm-day VaR edge with dev t −4.0 that gave t −1.3 out of sample; a fine-tuning gain in 21 of 22 dev arms that reversed sign for VaR |
| Target-tracking checks | A median-based calibration that left vol-targeted books at 18–20% instead of 10% (χ²-like ratios need the mean) |
| Data audits | A daily "close" that is the evening-session print; dividend adjustments one day late before 2023-07-31; holiday forward-fill creating fake zero returns (see the study 1 report for their effect) |

## Bottom line and limitations

Chronos-2 has no directional edge and no tradable alpha on MOEX, and for risk it reaches, but does not beat, the
best classical tools, at a much higher compute cost (a GPU for fine-tuning and a transformer forward pass per
forecast date, against closed-form or small-regression classical models).

- **One market, one period:** MOEX equities, 2020–2026, a universe selected by current liquidity (survivorship).
  Nothing here is assumed to generalize.
- **Detection, not deployment:** a null at these sample sizes does not rule out a narrow, regime-specific edge.
- **Power:** the 2025–26 holdout is short; "not significant" in the superiority tests was the expected outcome for
  most uses, which is why non-inferiority was pre-registered alongside them.
- **Pretraining overlap:** it is unknown whether MOEX series were in Chronos-2's training data.
