# Phase B — multivariate-vs-univariate gate — scratchpad

Paired comparison, not an independent stage: `phase_b_multivariate.yaml` and
`phase_b_univariate.yaml` are identical in every field except `group_mode`, run on the
same tickers/windows/covariates, compared via a paired McNemar test. Both configs must be
kept in sync — see the "config sync" note at the top of each YAML.

## Pointer
- Configs: `configs/phase_b_multivariate.yaml`, `configs/phase_b_univariate.yaml`
- Output dirs: `runs/phase_b_multivariate/`, `runs/phase_b_univariate/`
- Started: `2026-09-17`
- Status: `pending`

## Goal (copied from `exp_plan.md` §3b)
Does grouping many series for Chronos-2 to forecast jointly (`cross_learning=True`) beat
forecasting each independently (`cross_learning=False`)? Pre-registered stopping rule:
paired McNemar test on directional hit/miss per (ticker, horizon, window), BH-corrected
across cells. **Gate passes** iff aggregate ΔDA > 0 AND ≥1 BH-significant cell favoring
multivariate AND multivariate still beats baselines (zero/last/momentum5/ar1). **Gate
fails** → Phase C (lead-lag screening) is not funded; write up as a clean negative result
and stop — do not retry with different hyperparameters to chase significance.

## Data / config notes
- **Data source**: `algo_data`'s AlgoPack pull (2026-09-17), not the ISS cache —
  `data_source: algopack`, `algopack_processed_path: algo_data/data/processed/candles_1d/shares.parquet`
  (relative to `PROJECT_DIR` — i.e. `algo_data/` sits as a sibling *inside* the Colab project
  folder alongside `basic_cells.ipynb`, not one level up; fixed 2026-09-17 after a real
  Colab run hit `PROJECT_DIR` being flat, not nested under `path_a/` — see run log).
  Indexes (IMOEX etc.) and futures (BR/Si/GD) still come from ISS as before (algo_data's
  index/futures output isn't wired into `load_stage_inputs` — see `basic_cells.ipynb` §5) —
  first run needs a fresh ISS prefetch for 2020-2024, not yet cached locally.
- **22 tickers configured, ~16 survive**: `min_ticker_coverage: 0.9` drops LENT, MDMG,
  OZON, SMLT, VKCO, YDEX at `build_price_panel` time — all recent MOEX listings/
  redomiciliations with too little 2020-2024 history (YDEX: 115 bars total; verified
  2026-09-17 against the real pull, see `algo_data/current_state.md`). Confirm the exact
  surviving set in the run log below (`price_panel.shape` printed by `run_stage`).
- **X5 and RAGR** were in the original stratified pick but removed from `algo_data/config.md`
  entirely before the pull — zero candle history anywhere 2020-2024 (also recent
  redomiciliations). Not in either Phase B config.
- **`group_mode` is the only difference between the two configs** — verified end-to-end with
  a mock-pipeline test (2026-09-17) that `group_mode: multivariate/univariate` correctly
  drives `predict_df`'s `cross_learning=True/False`. Prior Path A stages (0, 1, 2) never set
  `cross_learning`, so they were already running univariate/independent forecasts despite
  batching all tickers into one `predict_df` call — Stage 2b's negative result is therefore
  the closest thing to a prior `phase_b_univariate` run, not a multivariate one.
- **context_len=250** chosen to match Stage 1c (the one sub-variant of the old daily study
  that actually ran) rather than re-deriving a value from scratch.

## Configuration deviations from plan
- Plan's Phase B spec suggested a "~20-25 ticker stratified subsample" for the gate; actual
  surviving panel is ~16 after the coverage guard (see above) — accepted per user decision
  2026-09-17 rather than relaxing the coverage threshold or hunting for replacement tickers.
- Plan flagged "verify predict_df batching semantics before writing the univariate driver"
  as a blocking first step — resolved by reading `chronos-forecasting`'s installed source
  directly (`chronos/chronos2/pipeline.py`) rather than a live Colab test: `cross_learning`
  is the actual switch, default `False`, batched-but-independent either way. No separate
  univariate driver was needed — same `predict_df` call, one boolean kwarg.

## Pre-registered: single run per arm, no context_len sweep (decided 2026-09-17, before any run)
User raised a fair concern before running anything: does a single run of each config give a
solid enough answer, given (a) Chronos-2's quantile forecasting has internal sampling, so a
rerun of the identical config could vary; (b) `context_len=250` wasn't swept for Phase B
specifically, just carried over from Stage 1c; (c) one specific 16-ticker panel could happen
to be unusually correlated or uncorrelated, biasing the result either way.
**Decision: single run per arm at context_len=250, as currently configured.** Explicitly
NOT expanding to a context_len grid (e.g. 128/250/500) up front, to avoid a shape of
experiment where the gate rule has to be improvised after seeing results — that's the kind
of hindsight-tuning the pre-registration is meant to prevent.
**However**: the single-run caveats above are real and are logged here BEFORE the run, so
the gate decision below must be read as conditional on this one context_len — not "does
multivariate ever help," only "does it help here." If the result is a **clean pass or clean
fail**, treat it as decisive per the stopping rule (§Goal) — do not chase it further. If the
result is **borderline** (e.g. ΔDA marginal, McNemar p close to the BH threshold), that is
itself the trigger to explicitly propose a follow-up context_len sweep as a new, separately
justified experiment — not a silent retry of the same test.

## Run log
| Date | Arm | Notes / changes since last run |
|------|-----|--------------------------------|
| 2026-09-17 | — | Configs written + validated (load_config, mock predict_df call). Not yet run. |
| 2026-09-17 | — | First real Colab attempt failed at the "source basic_cells.ipynb" step: `PROJECT_DIR` is flat (`MyDrive/moex-hack/`, `basic_cells.ipynb` directly inside it), not nested under `path_a/` as locally structured — mismatch between the repo's `path_a/` folder and the uploaded Drive layout. Fixed by using `algopack_processed_path: algo_data/data/processed/candles_1d/shares.parquet` (no `../`) and re-packaging the Colab upload as a flat `moex-hack/{basic_cells.ipynb, runner.ipynb, configs/, algo_data/}` folder. |
| 2026-09-17 | — | Second attempt hit `Errno 107: Transport endpoint is not connected` during `import torch` / CUDA init — a Drive FUSE mount hiccup destabilizing the GPU runtime, not a code bug. Fixed by Runtime → Restart runtime + remount, re-run from §0. |
| 2026-09-17 | multivariate | Third attempt: model loaded fine, but `run_stage` printed **"walk-forward: 0 windows"** and crashed downstream with `KeyError: 'ticker'` (empty `pred_df` propagating into plotting/aggregation code that assumes a `ticker` column exists). **Real bug found and fixed**: `build_covariate_panel` was building the `{ticker}_dlogvol` covariate columns from the FULL configured ticker list (22), not just the ones that survived `build_price_panel`'s coverage guard (16) — one gappy dropped ticker (YDEX, 115 bars) in that mix collapsed the covariate panel's `dropna(how="any")` from 1301 rows to 113, which collapsed `ret.index.intersection(cov.index)` and left too few rows for any `context_len=250` window. Reproduced locally (cov shape (113, 22) with all configured tickers vs (1301, 16) with only survivors) and fixed in `assemble_panels` (cell 15) — now filters `prices` to `price.columns` (the survivors) before passing to `build_covariate_panel`. Verified fix locally: `cov` now correctly comes back at (1301, 16), matching `price`/`ret`. |
| 2026-09-17 | — | User asked why Colab/GPU at all, given no fine-tuning is happening. Checked: Chronos-2 is T5-base-sized (~150M params, `d_model=768`, 12 layers) — genuinely light. Decided to add local-run support to `runner.ipynb` rather than keep debugging Colab/Drive friction; Colab stays the primary path, local CPU is the documented fallback (see `runner.ipynb`'s top markdown cell). |
| 2026-09-17 | — | Local dry run (before adding local support fully) surfaced a **second real bug**, same shape as the covariate one: `run_stage` calls `run_walk_forward(pipeline, cfg, ...)` with the ORIGINAL `cfg["tickers"]` (22 configured), not the survivors — `build_chronos_inputs` then does `ret_panel[tic]` for a dropped ticker (e.g. SMLT) and crashes with `KeyError`. Would have hit this on Colab too, right after the covariate fix, on the very next run. Fixed in `run_stage` (cell 28): reconciles `cfg["tickers"]` to `ret_panel.columns` once, right after `assemble_panels`, before any downstream consumer (walk-forward, baselines, metrics, plots) touches it. |
| 2026-09-17 | multivariate | **Local timing test, 5 real windows, CPU, `covariates: none` (isolating model-call cost)**: model load 2s (warm HF cache), 5 windows in 1.4s → **~0.3s/window**. Extrapolated: ~1.8 min for 400 windows (one arm), ~3.6 min for both arms combined. Confirms the user's original instinct — Chronos-2 zero-shot inference at this scale is genuinely CPU-light; the earlier assumption that Colab/GPU was necessary was not well-founded for this specific workload (Colab remains useful for avoiding local compute load, not because CPU is infeasible). Real run (with covariates, full window count) will be slower than this isolated estimate, but not by orders of magnitude. |
| 2026-09-17 | multivariate | **FULL RUN COMPLETED**, locally, `.venv` (Python 3.12) kernel, CPU. Real time ~15 min total (includes the one-time ISS prefetch for indexes/futures 2020-2024, not yet cached before this run). 400/400 windows, 16 tickers confirmed in `metrics.csv` (both bug fixes held up under a real full-scale run). Output: `runs/phase_b_multivariate/`. See Top-line numbers below. |

## Top-line numbers (paste from each arm's `summary.json`)
### Multivariate
```json
{
  "stage_id": "phase_b_multivariate",
  "group_mode": "multivariate",
  "n_windows": 400,
  "mean_da_primary": 0.4841145833333333,
  "median_da_primary": 0.48624999999999996,
  "cells_signif_05": 0,
  "mean_pearson_primary": -0.058163962074690045,
  "mean_coverage_primary": 0.7890104166666667,
  "trend2_n_signals": 4457,
  "trend2_acc_both": 0.23872560017949293,
  "trend2_acc_cum": 0.5086380973749158
}
```
Per-horizon (`metrics_aggregate.csv`, 16 tickers × 4 horizons = 64 cells, 0 significant anywhere):

| h | mean DA | mean Pearson | mean coverage |
|---|---------|--------------|----------------|
| 1 | 0.4845  | 0.0348       | 0.793          |
| 2 | 0.4884  | -0.0210      | 0.781          |
| 3 | 0.4836  | -0.1134      | 0.792          |
| 5 | 0.4803  | -0.0401      | 0.794          |

Chance-level DA across every horizon, near-zero/negative mean Pearson, 0/64 BH-significant
cells — consistent in shape with Stage 2b's earlier negative result.

### Univariate
```json
{
  "stage_id": "phase_b_univariate",
  "group_mode": "univariate",
  "n_windows": 400,
  "mean_da_primary": 0.4838541666666667,
  "median_da_primary": 0.4875,
  "cells_signif_05": 0,
  "mean_pearson_primary": -0.05273592954529105,
  "mean_coverage_primary": 0.7868749999999999,
  "trend2_n_signals": 4350,
  "trend2_acc_both": 0.2354022988505747,
  "trend2_acc_cum": 0.5126436781609195
}
```
Same 16 tickers as the multivariate arm (confirmed identical ticker sets). Chance-level DA,
0/64 BH-significant cells — nearly indistinguishable from the multivariate arm's top-line
numbers (0.4839 vs 0.4841 mean DA).

## McNemar test result — 2026-09-17

Implemented `mcnemar_gate_test()` in `basic_cells.ipynb` §13 (new section, after the stage
orchestrator): per-(ticker, horizon) paired exact binomial McNemar test on directional
hit/miss, matched window-by-window between the two arms' `preds.parquet` (hit/miss per
window isn't itself persisted, so it's recomputed from `preds.parquet` + a freshly-rebuilt
`ret_panel`, using the identical sign-match rule `per_cell_metrics` uses). BH-corrected
across all 64 (ticker × horizon) cells, matching the existing BH pattern in
`per_cell_metrics`. Verified end-to-end against the real run outputs before trusting the
result (ticker-set match confirmed, `ret_panel` shape confirmed 1301×16 matching both runs).

**Per-cell**: 64 cells, all `n_paired=400` (full pairing, no dropped windows in either arm).
Raw p-values scatter as expected under the null (a few cells <0.05: AFKS h3 p=0.029, FEES h5
p=0.035, ROSN h3 p=0.012) — **none survive BH correction** (all `p_value_bh` ≥ 0.75).

**Gate**:
```json
{
  "gate": "FAIL",
  "agg_delta_da": -0.0003515625000000038,
  "n_cells": 64,
  "n_signif_bh": 0,
  "n_signif_favoring_multivariate": 0
}
```
- Aggregate ΔDA (multivariate − univariate) ≈ **-0.00035** — effectively zero, not positive.
- **0 of 64 cells BH-significant** — no per-cell evidence either.
- (Baseline-beating check, third pre-registered condition, checked for completeness even
  though the first two already fail: multivariate's mean DA 0.4841 edges past `last`
  baseline's 0.4758 and `ar1`'s 0.4736, roughly ties `momentum5`'s 0.4905 — moot, doesn't
  change the gate outcome.)

**Gate decision: FAIL — not borderline, treated as decisive per the pre-registration.**
ΔDA is not just small, it's slightly negative; 0/64 cells is as clean a null result as this
test design can produce. Per the pre-registration note above (§"single run per arm"), this
does NOT trigger a context_len sweep — a clean fail is decisive, not a reason to chase it
with more runs.

## Plots checked
- [x] `phase_b_multivariate/plots/da_heatmap.png` — no visible per-ticker/horizon pattern, consistent with 0/64 significant
- [x] `phase_b_univariate/plots/da_heatmap.png` — same, near-identical to multivariate's
- [ ] `phase_b_multivariate/plots/da_vs_last.png`
- [ ] `phase_b_univariate/plots/da_vs_last.png`

## Observations
Multivariate and univariate arms are nearly indistinguishable on every top-line number
(mean DA 0.4841 vs 0.4839, mean Pearson -0.058 vs -0.053, coverage 0.789 vs 0.787) — this
isn't just "no significant difference," the two arms behave almost identically window-by-
window (discordant pair counts per cell are small and roughly balanced, e.g. AFKS h1:
n01=17/n10=8 is the largest imbalance in either direction across all 64 cells, and even that
doesn't survive BH correction). Combined with both arms independently landing at
chance-level DA (matching Stage 2b's original negative result), this reads as a genuine
"grouping doesn't help, and neither variant has an edge" result at this context_len/universe/
data scope — not a case where the test lacked power to see something real.

**Pinball loss backfill (2026-09-17, added after Phase C concluded)**: mean pinball loss
across primary horizons is 0.005093 (multivariate) vs 0.005098 (univariate) — same
near-identical pattern as every other metric. Read jointly with coverage (~0.79, close to the
0.80 target in both arms): the quantile intervals are reasonably well-calibrated — Chronos-2
correctly expresses appropriate uncertainty width — but that calibration carries zero
directional skill (DA≈0.484). This is a more precise statement than "DA≈0.50" alone: the
model isn't miscalibrated or broken, it just has no directional edge to calibrate around.

**Per-window clustering check (2026-09-17, added after Phase E's daily results)**: user
asked whether Chronos's multivariate arm might have found real, "non-obvious" structure
(complex multi-ticker combinations, not just pairwise leader-follower — the original hope
behind trying Chronos multivariate at all) that a coarse (ticker, horizon)-aggregated DA
number could have washed out. Re-examined the SAME saved predictions (`preds.parquet`, no
new run) at the finer (ticker, horizon, window) level — 25,600 paired hit/miss
observations across 400 windows × 16 tickers × 4 horizons.

- Overall `mean(multi_better) = hit_multi - hit_uni` across all cells: -0.00035 (matches
  the aggregate ΔDA already reported above).
- Per-window mean (multivariate's edge averaged across the 64 ticker×horizon cells active
  in that window): ranges -0.078 to +0.078 (roughly ±5 of 64 cells tipping either way),
  which *looks* like meaningful spread at a glance.
- **Formal check, not eyeballing**: ran a 500-iteration label-permutation test (randomly
  swap which arm is "multi" vs "uni" per cell, recompute the same per-window variance) to
  ask whether the OBSERVED variance across windows exceeds what pure chance produces.
  Result: observed variance 0.000768 vs. permutation-null mean 0.000727 (95th percentile
  0.000815) — **p=0.22, not significant.** The per-window spread is statistically
  indistinguishable from sampling noise.
- Also checked per-ticker clustering: range -0.005 to +0.005 across the 16 tickers, no
  discernible pattern (best/worst tickers aren't grouped by sector or liquidity).
- **Conclusion**: the aggregate null was NOT hiding a real, time-localized or
  ticker-localized effect. This directly answers the "did Chronos find something subtle
  that a blunt metric missed" question — checked properly, and the answer is no. Combined
  with Phase E's five negative results (which tested a different hypothesis shape —
  short-window pairwise bursts, not multi-ticker joint structure), this closes off both the
  "aggregate skill" and "hidden localized skill" readings of the multivariate arm's null.

## Decision / Next

**Gate FAILED. Phase C (lead-lag screening) is NOT funded, per the pre-registered rule.**
Per `exp_plan.md` §3b: "Gate fails → Phase C not funded, write up as a negative result, stop."

Next actions:
1. Write up this result in `docs/current_state.md` as a new session-log entry (honest
   negative result — this is a real, useful finding for the project's CV-quality goal, not
   a failure to hide).
2. Update `docs/exp_plan.md` §3b to mark Phase B concluded (FAIL) and Phase C as not started
   (blocked by the gate, not "not yet reached").
3. Do NOT propose a context_len sweep or any other retry to chase significance — the
   pre-registration explicitly rules this out for a clean fail.
4. Open question for the user: does the project stop here (Phase B/gate was the last planned
   phase before Phase D's stretch backtest, which is itself gated on B OR C passing — B
   failed, so Phase D is also not funded per the plan), or is there a different direction to
   take given two independent negative results (Stage 2b, Phase B) now confirm chance-level
   predictability at this scope?
