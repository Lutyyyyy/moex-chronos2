# Phase X — scratchpad

> Copy this template to `phase_<letter>_<name>_scratch_pad.md` when starting a new phase run.
> Single source of running notes for that run — what was actually run, what came out, what to tweak.

## Pointer
- Config: `configs/phase_<letter>_<name>.yaml`
- Output dir: `runs/<stage_id>/`
- Started: `<YYYY-MM-DD>`
- Status: `pending | running | done | blocked`

## Goals (copied from `exp_plan.md` §3b for quick reference)
- ...

## Configuration deviations from plan
List any knob that diverges from `exp_plan.md` and why.
- ...

## Run log
| Date | Sub-id | Notes / changes since last run |
|------|--------|--------------------------------|
| YYYY-MM-DD | phase_Xa | initial run |

## Top-line numbers (paste from `summary.json`)
```
{}
```

## Per-horizon DA (paste from `metrics_aggregate.csv`)
| h | mean DA | median DA | n_signif (BH 0.05) | mean Pearson | mean coverage |
|---|---------|-----------|--------------------|--------------|---------------|

## Plots checked
- [ ] `plots/da_heatmap.png`
- [ ] `plots/da_vs_last.png`
- [ ] `plots/corr_hist.png`
- [ ] `plots/amplitude.png`
- [ ] `plots/coverage.png`
- [ ] `plots/examples.png`

## Observations
What surprised us. What was expected. Per-ticker outliers.

## Decision / Next
What changes for the next stage. Or what blocks closing this one.
