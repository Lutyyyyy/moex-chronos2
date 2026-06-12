# Stage 0 — smoke run scratchpad

## Pointer
- Config: `configs/stage_0_smoke.yaml`
- Output dir: `runs/stage_0_smoke/`
- Started: 2026-06-12
- Status: PASSED (pipeline validated end-to-end)

## Goals
- End-to-end pipeline executes on a fresh Drive cache.
- Cache populated for core 12 daily, 2024-H1.
- Output schema (`metrics.csv`, `metrics_aggregate.csv`, `summary.json`, `plots/*.png`) matches what downstream stage runners expect to read.
- Sanity bounds: aggregate DA in [0.40, 0.60]. Anything outside is a sign bug.

## Configuration deviations from plan
- `context_len` lowered `250 → 60`. The 2024-H1 daily window yields only 127 business
  days; with `context_len=250 > panel length`, `walk_forward_anchors` produced 0 windows
  and metrics crashed on an empty preds frame (`KeyError: 'id'`). 60 fits the panel and
  gives ~62 candidate windows, capped to `max_windows=40`. Revisit for Stage 1 (longer window).

## Run log
| Date | Sub-id | Notes |
|------|--------|-------|
| 2026-06-12 | stage_0_smoke | run 001: crashed — context_len>panel → 0 windows → KeyError 'id'. |
| 2026-06-12 | stage_0_smoke | run 002: PASSED. context_len=60 → 40 windows. Logs: `runs/stage_0_smoke/output_002.md`. |

## Top-line numbers
(from `runs/stage_0_smoke/summary.json`)
```json
{
  "stage_id": "stage_0_smoke",
  "n_windows": 40,
  "mean_da_primary": 0.4785,
  "median_da_primary": 0.475,
  "cells_signif_05": 0,
  "mean_pearson_primary": 0.0424,
  "mean_coverage_primary": 0.7639
}
```
Primary horizons = [2, 3, 5]. All within sanity bounds — no statistical claim expected at this scale.

## Per-horizon DA
(from `runs/stage_0_smoke/metrics_aggregate.csv`, 12 cells/horizon)
| horizon | mean_da | median_da | mean_pearson | mean_spearman | mean_amp | mean_cov | n_signif_05 |
|---------|---------|-----------|--------------|---------------|----------|----------|-------------|
| 1 | 0.475 | 0.475 | -0.022 | 0.002 | 0.284 | 0.746 | 0 |
| 2 | 0.488 | 0.488 | 0.052 | 0.073 | 0.298 | 0.777 | 0 |
| 3 | 0.467 | 0.450 | 0.007 | -0.014 | 0.200 | 0.733 | 0 |
| 5 | 0.481 | 0.475 | 0.068 | 0.083 | 0.251 | 0.781 | 0 |

## Plots checked
- [x] da_heatmap.png
- [x] da_vs_last.png
- [x] corr_hist.png
- [x] amplitude.png
- [x] coverage.png
- [x] examples.png

## Observations
- DA sits at ~0.47–0.49 across all horizons (≈ coin flip); 0 of 48 cells significant at 0.05 (BH).
  Correct for a 40-window / 127-day daily smoke — no edge expected, none found.
- `amp_ratio ≈ 0.20–0.30` ≪ 1.0: median forecast amplitude is ~4–5× smaller than realised
  returns. Chronos is heavily regressing daily returns toward zero. Expected for a near-random
  target; worth watching as a calibration signal in later stages, not a bug.
- `coverage ≈ 0.73–0.78` vs the q10–q90 nominal 0.80 — slightly narrow bands, consistent with
  the amplitude shrinkage. Acceptable at this sample size.
- Pipeline fixes landed in `basic_cells.ipynb` (single source of truth):
  1. Negative cache for ISS empties — dead/out-of-window FORTS contracts now cached as zero-row
     parquet (`CACHE-NEG`), so each empty key hits ISS at most once. `_iss_candles` raises on
     transport failure so outages aren't poisoned into the cache.
  2. `prefetch_one` prints one status line per key (CACHE / CACHE-NEG / ISS / ISS-EMPTY / FAIL)
     with full path + row count.
  3. `per_cell_metrics` returns empty frame on empty/column-less preds (graceful 0-window exit).
  4. Correlation guarded against constant input (kills the divide / ConstantInputWarning spam
     from the all-zero baseline).

## Decision / Next
- Pipeline runs clean and output schema is correct → proceed to Stage 1 (full daily study).
- For Stage 1: use a longer history so `context_len` can return toward the planned 250 without
  starving the walk-forward window count.
