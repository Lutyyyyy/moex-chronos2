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

## Top-line numbers (paste from each arm's `summary.json`)
### Multivariate
```
{}
```
### Univariate
```
{}
```

## McNemar test result (fill in once both arms have run)
- Discordant pairs (multivariate-right/univariate-wrong vs the reverse): `n01=?, n10=?`
- Test statistic / p-value:
- BH-corrected significant cells favoring multivariate:
- **Gate decision**: `PASS | FAIL` — reasoning:

## Plots checked
- [ ] `phase_b_multivariate/plots/da_heatmap.png`
- [ ] `phase_b_univariate/plots/da_heatmap.png`
- [ ] `phase_b_multivariate/plots/da_vs_last.png`
- [ ] `phase_b_univariate/plots/da_vs_last.png`

## Observations
What surprised us. What was expected. Per-ticker outliers.

## Decision / Next
Gate pass → begin Phase C design (discovery/confirmation split, `metric_window` enforcement
fix). Gate fail → write up negative result in `docs/current_state.md`, stop, do not proceed
to Phase C.
