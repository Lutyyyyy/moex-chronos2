You are working in the MOEX Chronos-2 project. Do not invent missing project behavior. If a required implementation detail is not discoverable from the files, add a clear `TODO/ASK` note in `current_state.md` and stop only for that specific unknown.

Context:
- Path A already exists as a zero-shot Chronos-2 pipeline.
- `basic_cells.ipynb` is the reusable cell library.
- `runner.ipynb` is the universal notebook that sources `basic_cells.ipynb`, reads YAML config, and runs stages end-to-end.
- `exp_plan.md` says Path B must reuse Path A cache/panel build/walk-forward/evaluation structure and compare fine-tuned Chronos-2 against the zero-shot baseline.
- `B_plan_v1.md` has been reworked into `B_plan_v2_cross_learning.md`; use it as the Path B implementation spec.
- For Path B, forecast horizons are `1/2/3`, `prediction_length=3`, and fine-tuning is only for `10m` and `60m`.

Task:
Extend the project with Path B fine-tuning while preserving the Part A structure.

Hard requirements:
1. Keep the same project style and directory pattern as Path A:
   - `runs/` must remain the run-output root.
   - `scratchpads/` must remain the human log root.
   - configs must be inherited from Part A stage configs and extended for Path B, not replaced by unrelated configs.
   - create and maintain `current_state.md` at project root.
   - Path B outputs should live under `runs/path_b/...`.
   - Path B scratchpads should live under `scratchpads/path_b/...`.
2. Extend `basic_cells.ipynb`; do not create a disconnected implementation.
3. Create a fine-tuned runner notebook, preferably `runner_path_b.ipynb`, with the same operational style as `runner.ipynb`:
   - locate project;
   - source `basic_cells.ipynb`;
   - load config;
   - run Path B;
   - inspect tables and plots inline.
4. Implement B0–B4 from `B_plan_v2_cross_learning.md`.
5. Every B1–B4 implementation cell/function must expose an explicit boolean `cross_learning` flag:
   - default main arm: `cross_learning=True`;
   - optional diagnostic arm: `cross_learning=False`;
   - controlled by config:
     ```yaml
     path_b:
       cross_learning_main: true
       cross_learning_diagnostics: false
     ```
   - when diagnostics are off, run only `[true]`;
   - when diagnostics are on, run `[true, false]`.
6. Do not hide `cross_learning` inside a shared defaults dict. It must be visible in the hyperparameters and in run metadata for B1–B4.
7. Preserve Path A’s frozen representation:
   - same ticker universe;
   - same canonical long-form input;
   - same walk-forward windows;
   - same covariates selected by Part A;
   - same quantiles `[0.1, 0.5, 0.9]` unless the config already says otherwise;
   - same metric package, adapted to horizons `[1, 2, 3]`.
8. B0 must run AutoGluon Chronos-2 zero-shot as a harness reference.
9. B1–B4 must train only fine-tuned candidate configurations, not a zero-shot model in the same `hyperparameters` block.
10. Runner must run optimizations first, then compare all fine-tuned runs with B0 zero-shot predictions.

Documentation constraints:
- Use official AutoGluon TimeSeries + Chronos-2 docs for the exact valid AutoGluon API names.
- Use `hyperparameters={"Chronos2": {...}}`.
- Use `fine_tune=True` for fine-tuned runs.
- Use LoRA for the initial runs (`fine_tune_mode="lora"`).
- Use explicit `fine_tune_lr`, `fine_tune_steps`, `fine_tune_batch_size`, `context_length`, `fine_tune_context_length`, `cross_learning`, and `batch_size`.
- Keep `enable_ensemble=False` unless an explicit config asks otherwise.
- Use AutoGluon verbosity/log capture and Python timing; do not invent a nonexistent progress API. Wrap Path B loops in `tqdm`.

Implementation steps:

A. Add Path B config helpers in `basic_cells.ipynb`
- Add a config-normalization function, for example `normalize_path_b_config(cfg)`, that:
  - ensures `path_b.enabled`;
  - ensures `path_b.intervals_to_test` is `[10, 60]` or inherited single `[cfg["interval"]]` if the config is interval-specific;
  - sets `prediction_length=3` / `horizon=3`;
  - sets `eval_horizons=[1,2,3]`;
  - sets `primary_horizons=[1,2,3]`;
  - sets default `cross_learning_main=True`;
  - sets default `cross_learning_diagnostics=False`;
  - sets `num_val_windows=3`, `refit_every_n_windows=1`, and `val_step_size=cfg["walk_forward"]["shift"]`.
- Add `get_cross_learning_values(cfg)` returning `[True]` or `[True, False]`.

B. Add AutoGluon data adapters
- Implement conversion from the existing Path A panel outputs to AutoGluon `TimeSeriesDataFrame`.
- Use existing Path A `assemble_panels(...)`, `build_chronos_inputs(...)`, and walk-forward anchors where possible.
- Map:
  - item id column to AutoGluon item id;
  - timestamp to timestamp;
  - target returns to `target`;
  - known future covariates to `known_covariates_names`;
  - past covariates as columns in train data when AutoGluon/Chronos-2 supports them.
- If there is ambiguity about which Path A covariates are known-future vs past-only in the current notebook, implement the safe existing split:
  - calendar covariates are known future;
  - market/index/futures/volume covariates are past-only;
  - write the decision to `current_state.md`.

C. Add Path B run directory helpers
- Create immutable run directories:
  ```text
  runs/path_b/{interval}/{step_id}/{run_id}/
  ```
- Each run directory must contain:
  - `config.yaml`;
  - `hyperparameters.json`;
  - `predictor/` or AutoGluon model directory;
  - `preds/preds.parquet`;
  - `metrics.csv`;
  - `metrics_aggregate.csv`;
  - `summary.json`;
  - `logs/fit.log`;
  - `plots/`.
- Create/update append-only:
  ```text
  runs/path_b/path_b_runs.csv
  ```

D. Add B0–B4 hyperparameter builders
- Implement:
  - `make_b0_hyperparameters(cfg, cross_learning)`
  - `make_b1_hyperparameters(cfg, cross_learning)`
  - `make_b2_hyperparameters(cfg, cross_learning)`
  - `make_b3_hyperparameters(cfg, steps, lr, fine_tune_batch_size, cross_learning)`
  - `make_b4_hyperparameters(cfg, reference_lora_config, cross_learning, batch_size)`
- Use the exact B-plan logic:
  - B0: `fine_tune=False`;
  - B1: LoRA, lr `1e-5`, steps `300`, ft batch `8`;
  - B2: same as B1, seeds `[1,2,3]`;
  - B3 staged grid:
    ```yaml
    fine_tune_steps: [100, 300, 1000]
    fine_tune_lr: [1e-5, 3e-5]
    fine_tune_batch_size: [8, 16]
    ```
  - B4 batch-size grid:
    ```yaml
    batch_size: [32, 64, 128]
    ```
- Make sure run IDs include `cross_learning`.

E. Add Path B experiment runner
- Implement `run_path_b_experiment(...)`:
  - build AutoGluon `TimeSeriesPredictor`;
  - fit with `hyperparameters`;
  - time fit and prediction separately;
  - save logs;
  - predict on the exact same evaluation windows as Path A;
  - write predictions in the same schema as Path A metrics expect;
  - compute metrics using existing metric functions;
  - save metrics, summary, plots, metadata.
- Implement `run_path_b(cfg_path, steps=("b0","b1","b2","b3","b4"))`:
  - load and normalize config;
  - build/reuse Path A panels;
  - run B0 first;
  - run B1, B2, B3;
  - select `REFERENCE_LORA_CONFIG` after B3 using the existing comparison table, not inside the training loop;
  - run B4 using that reference config;
  - aggregate comparisons after all runs.

F. Add comparison utilities and plots
- Implement:
  - `collect_path_b_runs(...)`;
  - `compare_path_b_to_b0(...)`;
  - `choose_reference_candidate(...)`;
  - `load_hyperparameters(...)`;
  - `append_path_b_run_row(...)`.
- Fill `runs/path_b/path_b_runs.csv` with at least:
  ```text
  run_id, step_id, parent_run_id, seed, train_universe_id, eval_universe_id,
  interval, context_length, prediction_length, fine_tune, fine_tune_mode,
  fine_tune_lr, fine_tune_steps, fine_tune_batch_size, batch_size,
  cross_learning, num_val_windows, n_items_train, n_rows_train,
  fit_seconds, predict_seconds, primary_score, primary_score_b0, delta_vs_b0,
  score_h1, score_h1_b0, delta_h1_vs_b0,
  score_h2, score_h2_b0, delta_h2_vs_b0,
  score_h3, score_h3_b0, delta_h3_vs_b0,
  coverage, coverage_b0, delta_coverage_vs_b0,
  overfit_flag, runtime_flag, selected_candidate, notes
  ```
- Reuse existing Part A plots for each candidate:
  - `da_heatmap`;
  - `corr_hist`;
  - `amplitude`;
  - `coverage`;
  - `forecast_examples`.
- Add comparison plots:
  - `delta_by_run.png`;
  - `delta_by_horizon.png`;
  - `delta_by_ticker_heatmap.png`;
  - `runtime_vs_delta.png`;
  - `coverage_candidate_vs_b0.png`;
  - `cross_learning_batch_stability.png`.

G. Add `runner_path_b.ipynb`
- Same sections as the existing runner:
  1. locate project on Drive;
  2. source `basic_cells.ipynb`;
  3. choose config;
  4. run Path B;
  5. inspect outputs and display all plots.
- Default config path should be a Path B config derived from Part A 10m or 60m config, not a synthetic unrelated config.
- Include a switch:
  ```python
  PATH_B_STEPS = ("b0", "b1", "b2", "b3", "b4")
  summary = run_path_b(CONFIG_PATH, steps=PATH_B_STEPS)
  ```

H. Add config examples
- Create examples such as:
  - `configs/path_b_10m.yaml`
  - `configs/path_b_60m.yaml`
- They must inherit/copy the corresponding Part A config fields and add:
  ```yaml
  path_b:
    enabled: true
    output_root: runs/path_b
    scratchpad_root: scratchpads/path_b
    current_state_path: current_state.md
    intervals_to_test: [10]   # or [60]
    prediction_length: 3
    eval_horizons: [1, 2, 3]
    primary_horizons: [1, 2, 3]
    cross_learning_main: true
    cross_learning_diagnostics: false
    num_val_windows: 3
    refit_every_n_windows: 1
  ```

I. Maintain `current_state.md`
- Create the file if missing.
- Add:
  - current task;
  - files changed;
  - assumptions inherited from Path A;
  - unresolved questions;
  - last completed step;
  - next command to run.
- Update it after implementing the cells and after creating the runner.

Acceptance checks:
1. `basic_cells.ipynb` still supports existing Part A runner calls.
2. `runner.ipynb` remains usable for Path A.
3. `runner_path_b.ipynb` can source `basic_cells.ipynb` and call `run_path_b`.
4. B1–B4 all have explicit `cross_learning` flags in both hyperparameters and run metadata.
5. Turning `path_b.cross_learning_diagnostics` from `false` to `true` adds `cross_learning=False` diagnostic runs without code edits.
6. B4 no longer uses any stale `B5_*` names.
7. All Path B comparisons use horizons `[1,2,3]`, not `[2,3,5]`.
8. Fine-tuned runs do not include a zero-shot arm in the same hyperparameter block.
9. Runner produces default plots for B0 and every fine-tuned candidate, plus comparison plots.
10. `runs/path_b/path_b_runs.csv` contains metric deltas versus B0.
