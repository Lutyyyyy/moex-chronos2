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
  `data_source: algopack`, `algopack_processed_path: ../algo_data/data/processed/candles_1d/shares.parquet`.
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
