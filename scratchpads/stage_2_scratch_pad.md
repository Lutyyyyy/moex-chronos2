# Stage 2 — 60m intraday, Path A — scratchpad

> Single source of running notes for Stage 2 — what was actually run, what came out, what to tweak.
> First sub-variant run is **2b (ctx600)**; config lives in `runs/stage_2b_60m_ctx600/config.yaml`
> (no `configs/stage_2*.yaml` checked in yet — bump one when the grid is formalised).

## Pointer
- Config snapshot: `runs/stage_2b_60m_ctx600/config.yaml`
- Output dir: `runs/stage_2b_60m_ctx600/`
- Started: 2026-06-15
- Status: **2b (ctx600) done** — pipeline fixes landed, full 500-window run clean.

## Goals (Stage 2 = intraday test of the core hypothesis)
The prototype's "first 2–3 bars look predictive" effect was **intraday**, so 60m (and later 10m)
is the real test, not daily (Stage 1, which had no edge by design). Specifically:
1. Per (ticker, horizon) DA + binomial p — any cell clear p<0.05 after BH?
2. **2-bar trend agreement** (`trend2_metrics`, new this stage): when Chronos predicts a 2-bar
   trend (sign of bar1 == sign of bar2, +,+ / -,-), how often does reality agree — strict `both`
   (chance 0.25) and cumulative `cum` (chance 0.50)?
3. Quantile calibration: observed q10–q90 hit-rate vs 0.8.

## Configuration (stage_2b_60m_ctx600)
- interval 60, core 12 tickers, indexes IMOEX/MOEXOG/MOEXMM/MOEXFN, futures BR/Si/GD, `covariates: full`
- `date 2023-01-01 → 2026-04-30`, `context_len 600`, `horizon 5`, eval h∈{1,2,3,5}, primary {2,3,5}
- `walk_forward: shift 4, max_windows 500`
- Panel: price/ret (6943×12), cov (6943×19). 6943 ≈ business_days×8 → session grid is 8 bars/day
  (10:00–17:00); holidays/illiquid bars are `ffill`ed (see Data-quality note below).

## Pipeline fixes landed this stage (in `basic_cells.ipynb`)
1. **future_df timestamp mismatch → ~half the windows silently dropped.** The MOEX session grid
   is not a single regular frequency (17h overnight / ~65h weekend gaps), so Chronos rejected every
   horizon crossing a day boundary ("future_df timestamps do not match the expected prediction
   timestamps"). In run **001 only 251/500 windows survived, and all 251 were 11:00 anchors** — a
   pure time-of-day bias, not just a halving.
   Fix: `predict_df(..., validate_inputs=False)` + relabel outputs positionally to the real
   `fut_idx` (predict_df consumes future covariates by row order; verified vs Chronos-2 docs).
   Run **002: 500/500 windows.**
2. **New metric `trend2_metrics`** → `metrics_trend2.csv` + `trend2_*` keys in `summary.json`.
3. **Example plot made readable.** First added an `n_hist=40` history lead-in; then switched the
   x-axis to **positional bar-index** (gaps collapsed) — on a real-datetime axis the 17h/65h
   non-trading gaps were drawn as straight diagonal connectors spanning >50% of the width, which
   looked like the price was "auto-filling" linearly. Pure cosmetics; metrics unaffected.

## Run log
| Date | Sub-id | Notes / changes since last run |
|------|--------|--------------------------------|
| 2026-06-15 | 001 | First full attempt. 251/500 windows (rest failed on day-boundary timestamp check) — biased to 11:00 anchors. Surfaced the 3 issues above. |
| 2026-06-15 | 002 | After fixes: 500/500 windows, trend2 metric, readable example plot. Log: `stage_2b_output_002`. |

## Top-line numbers (paste from `summary.json`, run 002)
```
{"n_windows":500, "mean_da_primary":0.485, "median_da_primary":0.49,
 "cells_signif_05":0, "mean_pearson_primary":-0.00065, "mean_coverage_primary":0.799,
 "trend2_n_signals":4902, "trend2_acc_both":0.2393, "trend2_acc_cum":0.4963}
```

## Per-horizon DA (`metrics_aggregate.csv`, run 002)
| h | mean DA | median DA | n_signif (BH 0.05) | mean Pearson | mean Spearman | mean amp | mean coverage |
|---|---------|-----------|--------------------|--------------|---------------|----------|---------------|
| 1 | 0.489 | 0.493 | 0 | -0.020 | 0.021 | 0.087 | 0.785 |
| 2 | 0.487 | 0.488 | 0 |  0.017 | 0.032 | 0.078 | 0.749 |
| 3 | 0.480 | 0.485 | 0 | -0.008 | 0.013 | 0.082 | 0.819 |
| 5 | 0.488 | 0.493 | 0 | -0.011 | 0.009 | 0.071 | 0.829 |

## 2-bar trend agreement (`metrics_trend2.csv`, run 002)
- Pooled: 4902 trend signals, **acc_both 0.239** (vs 0.25 chance), **acc_cum 0.496** (vs 0.50 chance).
- Per-ticker: no ticker beats chance significantly; the only sub-0.05 p is **NLMK acc_cum 0.541
  (p=0.052)** — borderline and uncorrected, dies under any multiple-testing adjustment.
- Signal rate is very high (0.74–0.92): Chronos almost always predicts a consistent 2-bar sign
  (because the per-bar median has a stable tiny sign per series), but that sign carries no edge.

## Plots checked (run 002)
- [x] `plots/examples.png` — median tilt now visible; positional x-axis (no fake diagonal ramps).
- [ ] `plots/da_heatmap.png`
- [ ] `plots/da_vs_last.png`
- [ ] `plots/corr_hist.png`
- [ ] `plots/amplitude.png`
- [ ] `plots/coverage.png`

## Observations
- **No directional edge at 60m, same verdict as daily.** Primary DA 0.485, 0/48 cells BH-signif,
  Pearson ≈ 0. The "first 2 bars predictive" intraday hypothesis is **not** supported at 60m:
  trend2 acc_both 0.239 < 0.25, acc_cum 0.496 ≈ coin flip.
- **Calibration holds** (coverage 0.75–0.83, near nominal 0.80) and amplitude shrinkage is strong
  (|pred|/|true| ~0.07–0.09) — Chronos emits honest, wide, near-zero-centered return distributions;
  point forecasts are tiny because 60m returns look unpredictable to it.
- Flat median in price space is expected (cumsum of ~0 median returns), not a bug — confirmed the
  legacy prototype targets log-returns identically.

## Data-quality note (NOT fixed — deferred by decision)
Panel `ffill`s holidays/illiquid bars → artificial **zero log-returns** injected into `ret_panel`,
which are then scored as targets (flat segments in plots). Minority of bars; left as-is for now.
Options if revisited: drop ffilled bars from eval target, or mask zero-return holiday bars in metrics.

## Decision / Next
- 60m gives the same "no edge" verdict as daily. Before closing Stage 2, optionally sweep
  `context_len` (e.g. 250/600) and confirm stability, but expectation is flat.
- Proceed to **Stage 3 (10m)** — the finest interval, last place the intraday hypothesis could hold.
- If 10m is also flat, the cross-interval conclusion is firm: **Chronos-2 zero-shot has no
  directional edge on MOEX returns at any tested interval**, while staying well-calibrated.
