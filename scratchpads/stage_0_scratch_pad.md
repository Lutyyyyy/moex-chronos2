# Stage 0 — smoke run scratchpad

## Pointer
- Config: `configs/stage_0_smoke.yaml`
- Output dir: `runs/stage_0_smoke/`
- Started: TBD
- Status: pending

## Goals
- End-to-end pipeline executes on a fresh Drive cache.
- Cache populated for core 12 daily, 2024-H1.
- Output schema (`metrics.csv`, `metrics_aggregate.csv`, `summary.json`, `plots/*.png`) matches what downstream stage runners expect to read.
- Sanity bounds: aggregate DA in [0.40, 0.60]. Anything outside is a sign bug.

## Configuration deviations from plan
None. This config is verbatim from `exp_plan.md` §Stage 0.

## Run log
| Date | Sub-id | Notes |
|------|--------|-------|
| -    | stage_0_smoke | not yet run |

## Top-line numbers
*(to be filled after first run — paste contents of `runs/stage_0_smoke/summary.json`)*

## Per-horizon DA
*(paste rows from `metrics_aggregate.csv` once available)*

## Plots checked
- [ ] da_heatmap.png
- [ ] da_vs_last.png
- [ ] corr_hist.png
- [ ] amplitude.png
- [ ] coverage.png
- [ ] examples.png

## Observations
*(fill after the run)*

## Decision / Next
- If pipeline runs clean → proceed to Stage 1 (full daily study).
- If any stage fails: log the exception here and patch `basic_cells.ipynb` (single source of truth).
