# Path A archive

Concluded or superseded material, kept for reference — not part of the active pipeline.
Nothing here is read by `basic_cells.ipynb`, `runner.ipynb`, or any active config.

**2026-09-17: the whole numbered-stage scheme (stage_0 ... stage_7) is retired.** The
project pivoted from a linear stage sequence (single zero-shot model, one stage at a time)
to gated phases (A: universe/data, B: multivariate-vs-univariate gate, C: lead-lag
screening, D: stretch backtest — see `docs/exp_plan.md`). Configs going forward are named
`phase_b_*.yaml`, `phase_c_*.yaml`, etc., written when each phase's implementation starts
— none exist yet.

## `legacy_notebooks/`

- `moex_chronos2_pipeline.ipynb` — original prototype notebook. The single-window prototype
  ("first 2-3 predicted bars look accordant with real movement") that motivated the whole
  Path A framework. Superseded by `basic_cells.ipynb`'s reusable cell library.
- `Chronos2_Roma.ipynb` — earlier univariate experiments + a Kronos model comparison.

Already marked "legacy reference, don't develop new logic here" in `docs/index.md` before
this archive existed; moved here 2026-09-17 to keep `path_a/` limited to the active pipeline.

## `concluded_stages/`

Configs + scratchpads for stages that ran to completion with a written-up result. The actual
run output (metrics, plots, `summary.json`) stays live at `runs/<stage_id>/` — only the
config snapshot and running notes moved here, once a stage had nothing left to add.

- `stage_0_smoke.yaml` + `stage_0_scratch_pad.md` — Stage 0 smoke test. **PASSED 2026-06-12**:
  pipeline validated end-to-end, 40 windows, DA~0.48 (correctly a coin-flip at 127-day daily
  scale, no claim intended). See `runs/stage_0_smoke/`.
- `stage_2_60m.yaml` + `stage_2_scratch_pad.md` — Stage 2, 60m intraday, `context_len=600`
  (sub-variant 2b; 2a=300 and 2c=1000 were never run). **Concluded 2026-09-something**: clean
  negative result, DA≈0.485, 0/48 BH-significant cells, Pearson≈0. This result triggered the
  project's pivot (see `docs/current_state.md` session entry 14). See `runs/stage_2b_60m_ctx600/`.
- `stage_1_daily.yaml` + `stage_1_scratch_pad.md` — Stage 1, daily bars. **Superseded by the
  pivot 2026-09-17, not concluded normally**: only sub-variant 1c (context_len=250) had been
  run at pivot time; 1a/1b/1d were never run. Whatever 1c's output shows stays live at
  `runs/stage_1_daily*/` (folder name per its config's `stage_id`) as a partial record, but
  the stage-based plan it belonged to is retired — Phase B's multivariate/univariate gate
  replaces it rather than continuing the 1a/1b/1d sequence.
- `stage_3_10m.yaml`, `stage_4_sector.yaml`, `stage_5_covariates.yaml`, `stage_6_stability.yaml`,
  `stage_7_holdout.yaml` — **never run.** Planning artifacts for the old linear-stage sequence
  (finer intervals, sector splits, covariates, stability checks, holdout — all written before
  the pivot). Superseded wholesale by the Phase A–D structure; archived rather than continued.

## Why archive instead of delete

These are genuine records of what was tried and what was learned (including the negative
results that motivated the pivot) — deleting them would lose that trail. Archiving keeps
`path_a/`'s active surface limited to what's still in play, without discarding history.
