# Stage 1 — daily, full Path A study — scratchpad

> Single source of running notes for Stage 1 — what was actually run, what came out, what to tweak.

## Pointer
- Config: `configs/stage_1_daily.yaml`
- Output dir: `runs/<stage_id>/` (one per sub-run: `stage_1a..d`)
- Started: 2026-06-12
- Status: running — **1c (ctx250) done**; 1a/1b/1d pending

## Goals (copied from `exp_plan.md` §Stage 1)
1. Per (ticker, horizon) DA + binomial p — does any cell clear p<0.05 after BH correction?
2. Identify the context-length sweet spot from the 4-point grid (mean DA, mean corr per ctx).
3. Quantile calibration: how far is observed q10–q90 hit-rate from 0.8?

**Success criterion**: at least one (ticker, horizon) cell with DA ≥ 0.56 at p<0.05 (post-BH),
AND Chronos beats B1 (last/persistence) on aggregate DA across the core 12.

## Run plan — context grid sweep
Daily, core 12, IMOEX/MOEXOG/MOEXMM/MOEXFN/RGBI + BR/Si/GD covariates, `covariates: full`,
`date 2021-01-01 → 2026-04-30`, `horizon 5`, eval h∈{1,2,3,5}, `shift 1`, `max_windows 400`.
Run 4 sub-variants by editing **only** `context_len` + `stage_id` in `configs/stage_1_daily.yaml`:

| Sub-id | context_len | stage_id |
|--------|-------------|----------|
| 1a | 64  | `stage_1a_daily_ctx64`  |
| 1b | 128 | `stage_1b_daily_ctx128` |
| 1c | 250 | `stage_1c_daily_ctx250` (config's current default) |
| 1d | 500 | `stage_1d_daily_ctx500` |

## Configuration deviations from plan
None yet. (Config is verbatim from `exp_plan.md` §Stage 1.)

## Pre-run checks (lessons from Stage 0)
- **context_len vs panel length**: Stage 0 crashed because `context_len 250 > 127` daily bars
  → 0 windows → `KeyError 'id'`. Here the panel is ~5.3y daily ≈ 1300 business days, so all four
  ctx values (≤500) leave ≥800 windows before the 400 cap. **Still confirm `walk-forward: N windows`
  with N ≥ 200 in the log before trusting any sub-run's metrics.**
- Watch for **`WARN ... intra-contract bars with |log_return|>0.20`** from the FORTS resolver —
  if it prints, front-month selection picked a thin-day contract; escalate before trusting metrics.
- First run will prefetch Stage 1's own date range (different from Stage 0); negative-cache markers
  from Stage 0 don't cover it. Expect a fresh batch of `ISS` / `ISS-EMPTY` lines, then `CACHE`/`CACHE-NEG` on re-runs.

## Run log
| Date | Sub-id | Notes / changes since last run |
|------|--------|--------------------------------|
| 2026-06-12 | stage_1c | ctx250. Clean: 400 windows, panel (1388×12). FORTS resolver flagged 1 genuine spike (Si 2022-03-02, real RUB crash — kept). Log: `stag_1c_output_001.md`. |
| - | stage_1a/1b/1d | not yet run |

## Top-line numbers (paste from each sub-run's `summary.json`)
```
1a (ctx64):  {}
1b (ctx128): {}
1c (ctx250): {"n_windows":400, "mean_da_primary":0.4906, "median_da_primary":0.4862,
              "cells_signif_05":0, "mean_pearson_primary":-0.0117, "mean_coverage_primary":0.7981}
1d (ctx500): {}
```

## Per-horizon DA (paste from each `metrics_aggregate.csv`)
### 1a — ctx 64
| h | mean DA | median DA | n_signif (BH 0.05) | mean Pearson | mean coverage |
|---|---------|-----------|--------------------|--------------|---------------|

### 1b — ctx 128
| h | mean DA | median DA | n_signif (BH 0.05) | mean Pearson | mean coverage |
|---|---------|-----------|--------------------|--------------|---------------|

### 1c — ctx 250
| h | mean DA | median DA | n_signif (BH 0.05) | mean Pearson | mean coverage | mean amp |
|---|---------|-----------|--------------------|--------------|---------------|----------|
| 1 | 0.481 | 0.484 | 0 | 0.019 | 0.795 | 0.162 |
| 2 | 0.496 | 0.496 | 0 | 0.032 | 0.801 | 0.144 |
| 3 | 0.477 | 0.473 | 0 | -0.085 | 0.797 | 0.127 |
| 5 | 0.498 | 0.496 | 0 | 0.018 | 0.796 | 0.113 |

Baselines (all-h / primary-h mean DA): momentum5 **0.501 / 0.505** (best), chronos 0.488 / 0.491,
last 0.484 / 0.485, ar1 0.482 / 0.484, zero 0.05 (artifact — sign(0) never matches). No baseline has
any BH-significant cell either; momentum5's best raw cells (ROSN h3 p=0.007, MOEX/GMKN h2) die under BH.

### 1d — ctx 500
| h | mean DA | median DA | n_signif (BH 0.05) | mean Pearson | mean coverage |
|---|---------|-----------|--------------------|--------------|---------------|

## Context-length sweet spot (goal 2)
| context_len | mean DA (primary h) | mean Pearson (primary h) | vs B1 (last) on aggregate DA | n_windows |
|-------------|---------------------|--------------------------|------------------------------|-----------|
| 64  | | | | |
| 128 | | | | |
| 250 | 0.491 | -0.012 | +0.006 (0.491 vs 0.485) — beats B1 by a hair, loses to momentum5 (0.505) | 400 |
| 500 | | | | |

## Plots checked (per sub-run)
- [ ] `plots/da_heatmap.png`
- [ ] `plots/da_vs_last.png`
- [ ] `plots/corr_hist.png`
- [ ] `plots/amplitude.png`
- [ ] `plots/coverage.png`
- [ ] `plots/examples.png`

## Observations
- **1c (ctx250): no directional edge.** Primary DA 0.491, 0/48 cells BH-significant (min q=0.995).
  Pearson ≈ 0 (h3 even −0.085). Daily close-to-close returns look unpredictable to Chronos here.
- **Best simple signal is momentum5**, not Chronos: primary DA 0.505, h=2 DA 0.525. A weak 2-day
  return-autocorrelation effect that Chronos is *not* exploiting. Still fails BH (best raw cell
  ROSN h3 DA 0.563 p=0.007 → q=0.32). So nothing clears significance, but the ranking is informative.
- **Amplitude shrinkage intensified**, not eased, with longer history: |pred|/|true| ~0.11–0.16
  (Stage 0 was ~0.25), and it *decreases* with horizon. Yet coverage ≈ 0.80 (nominal). Reading:
  Chronos correctly emits wide, near-zero-centered daily-return distributions — point forecasts are
  tiny because the target is ~unpredictable, and the quantile bands are honest about that.
- Calibration is the one clear win at scale: coverage 0.795–0.801 across all horizons (vs 0.76 in smoke).
- Data: 1 genuine FORTS spike flagged (Si 2022-03-02, post-invasion RUB crash). Real, single bar, kept.

## Decision / Next
- **Complete the context grid** before any verdict — run 1a (64), 1b (128), 1d (500) (edit `context_len`
  + `stage_id`, ~2 min each). If DA stays ~0.49 and 0 significant across the grid, the daily conclusion is
  firm: **Chronos has no directional edge on daily MOEX returns, and underperforms a 5-day momentum rule.**
- Then proceed to Stage 2 (60m) — the prototype's "first 2–3 bars predictive" effect was intraday, so the
  real test of the hypothesis is at 60m/10m, not daily. Daily is expected to be the hardest case.
- Carry the best ctx (by DA/Pearson) forward as the "best interval" knob for Stages 4–7 regardless.
