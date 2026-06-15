# Path B — AutoGluon Chronos-2 Fine-Tuning Plan for MOEX

Companion plan to `exp_plan.md` and the Path A zero-shot pipeline.

Path B is not a separate research direction and not a search for accuracy by any possible means. Its purpose is narrower:

> Test whether AutoGluon fine-tuning of Chronos-2 improves the already validated Path A setup on the same data representation, same walk-forward windows, and same frozen evaluation package.

Part A is assumed to have already handled:

- ready-to-use pipeline from raw data to zero-shot Chronos-2 forecast;
- baseline comparison, including simple/statistical/linear baselines;
- metric design and the primary decision criteria;
- data representation choice, including whether OHLC-derived features are used;
- interval/context/covariate selection;
- final holdout definition.

Path B therefore changes only one family of things: **Chronos-2 training/fine-tuning configuration**.

---

## 1. Fixed assumptions inherited from Part A

Before Path B starts, Part A must provide a frozen configuration:

```yaml
path_a_locked:
  interval: <1d | 60m | 10m>
  prediction_length: 5
  context_length: <selected_context>
  primary_horizons: [2, 3, 5]
  cumulative_horizons: [5]
  universe_eval: <fixed evaluation universe, e.g. core12>
  covariate_set: <selected covariate set from Part A>
  data_format: <selected canonical feature schema from Part A>
  quantile_levels: [0.1, 0.5, 0.9]
  eval_metric_autogluon: <frozen continuous AutoGluon metric from Part A> -  metric for tuning ????
  decision_metrics: <frozen Path A evaluation package>
  holdout_start: <locked holdout date>
  holdout_end: <locked holdout date>
```

Path B must not change these during fine-tuning experiments. If a run changes covariates, data format, horizon, interval, evaluation universe, or metric definition, it is no longer a clean fine-tuning comparison and belongs back in Part A.

The only dataset-related dimension that Path B may vary is the **training universe size**. The evaluation universe remains frozen.

---

## 2. Core principle

Path B uses an experiment matrix, not per-run paired training.

B0 trains/runs the AutoGluon zero-shot reference once. Each later B-run trains/runs **one fine-tuned candidate configuration**. The comparison

```text
AutoGluon Chronos-2 zero-shot
vs
AutoGluon Chronos-2 fine-tuned candidate
```

happens only in the aggregation block, after both outputs have been written in the same schema. Fine-tuned B-runs should therefore not include a zero-shot model inside the same `hyperparameters` block.

The comparison must use:

- the same train/test split;
- the same walk-forward anchors;
- the same context length;
- the same future horizon timestamps;
- the same covariates;
- the same prediction post-processing;
- the same output schema;
- the same Path A evaluation code.

The intended difference between B-runs is controlled changes to the fine-tuning configuration.

### Important: experiment matrix, not elimination ladder

The B-steps below are ordered from cheapest to most complex, but they are **not** a sequential tournament where a worse option is killed immediately.

Correct interpretation:

```text
B0 verifies the harness.
B1–B7 define candidate experiment families.
Each candidate writes outputs independently.
All candidates are compared later in the aggregation block.
The final selected configuration is chosen after comparison, not inside the B-step runner.
```

This avoids path dependence such as “B3 was never run because B2 looked weak on one seed.” The order controls compute budgeting; it does not change the experiment definition.

There is one allowed exception: **within a parameter-search family**, such as B3, it is reasonable to choose a local reference configuration after all candidates in that family have been run and logged. This local reference is used to define later runs such as B4/B5/B6, but it does not delete the other candidates and it is not the final Path B selection. Final selection still happens in the aggregate comparison block.

A flat or negative result is still useful. If the cheap variants show no result but the next variant is inexpensive, it may still be run and logged. If the next variant is time-demanding, the absence of signal becomes a reason to pause rather than blindly spend compute.

---

## 3. Required AutoGluon interface and shared runner

Use AutoGluon `TimeSeriesPredictor` for both zero-shot and fine-tuned Chronos-2.

Do not compare:

```text
raw Chronos2Pipeline.predict_df from Path A
vs
AutoGluon fine-tuned predictor
```

because that mixes model changes with pipeline/preprocessing changes.

All B-steps should call the same runner. Individual B-steps should describe only:

```text
what hyperparameters change
which fit kwargs change, if any
which run plan is used, if not the default
```

### 3.1 Shared predictor constructor

```python
from autogluon.timeseries import TimeSeriesPredictor


def make_predictor(CFG, RUN_DIR):
    return TimeSeriesPredictor(
        prediction_length=CFG.prediction_length,
        target="target",
        known_covariates_names=CFG.known_covariates,
        quantile_levels=CFG.quantile_levels,
        eval_metric=CFG.eval_metric_autogluon,
        path=RUN_DIR,
    )
```

### 3.2 Shared experiment runner

The runner executes one candidate configuration and writes its outputs. It does **not** decide whether this configuration is better than previous configurations, and it does **not** delete or suppress worse configurations.

```python
def run_path_b_experiment(
    *,
    step_id: str,
    run_id: str,
    CFG,
    RUN_DIR,
    train_data,
    eval_windows,
    known_covariates_by_window,
    hyperparameters: dict,
    random_seed: int,
    fit_kwargs_extra: dict | None = None,
    hpo_kwargs: dict | None = None,
):
    fit_kwargs_extra = fit_kwargs_extra or {}
    run_dir = RUN_DIR / step_id / run_id

    predictor = make_predictor(CFG, run_dir / "autogluon")

    fit_kwargs = dict(
        train_data=train_data,
        hyperparameters=hyperparameters,
        enable_ensemble=False,
        random_seed=random_seed,
        **fit_kwargs_extra,
    )

    if hpo_kwargs is not None:
        fit_kwargs["hyperparameter_tune_kwargs"] = hpo_kwargs

    fit_timer = Timer()
    predictor.fit(**fit_kwargs)
    fit_seconds = fit_timer.elapsed()

    predictions = []
    predict_timer = Timer()
    for window in eval_windows:
        pred = predictor.predict(
            data=window.history,
            known_covariates=known_covariates_by_window.get(window.id),
        )
        predictions.append(convert_autogluon_output_to_path_a_schema(pred, window))
    predict_seconds = predict_timer.elapsed()

    predictions = concat_predictions(predictions)
    metrics = run_frozen_path_a_evaluation(predictions, CFG.decision_metrics)

    runtime = make_runtime_record(
        step_id=step_id,
        run_id=run_id,
        CFG=CFG,
        train_data=train_data,
        eval_windows=eval_windows,
        hyperparameters=hyperparameters,
        fit_seconds=fit_seconds,
        predict_seconds=predict_seconds,
    )

    write_path_b_outputs(
        run_dir=run_dir,
        cfg=CFG,
        hyperparameters=hyperparameters,
        fit_kwargs=fit_kwargs,
        hpo_kwargs=hpo_kwargs,
        metrics=metrics,
        predictions=predictions,
        predictor=predictor,
        runtime=runtime,
    )

    return {
        "step_id": step_id,
        "run_id": run_id,
        "metrics": metrics,
        "runtime": runtime,
        "run_dir": run_dir,
    }
```

If a B-step does not explicitly define a different running function, it uses `run_path_b_experiment(...)`.

### 3.3* What `write_path_b_outputs(...)` means

`write_path_b_outputs(...)` is not a model-selection function. It is a pure persistence/export function. It should write all artifacts needed to reproduce, compare, and audit one run.

Recommended implementation contract:

```python
def write_path_b_outputs(
    *,
    run_dir,
    cfg,
    hyperparameters,
    fit_kwargs,
    hpo_kwargs,
    metrics,
    predictions,
    predictor,
    runtime,
):
    run_dir.mkdir(parents=True, exist_ok=True)

    # 1. Exact configuration snapshot.
    # Includes frozen Part A fields, Path B fields, seed, dataset IDs,
    # fold/window IDs, and any paths used by the run.
    write_yaml(run_dir / "config_snapshot.yaml", cfg.to_dict())

    # 2. Model hyperparameters passed into AutoGluon.
    # Must preserve the exact Chronos2 block used for this run.
    write_json(run_dir / "hyperparameters.json", serialize_for_json(hyperparameters))

    # 3. Fit kwargs passed into predictor.fit(...), excluding train_data itself.
    # This records num_val_windows, val_step_size, refit_every_n_windows,
    # refit_full, random_seed, enable_ensemble, etc.
    fit_kwargs_export = remove_large_objects(fit_kwargs, keys=["train_data"])
    write_json(run_dir / "fit_kwargs.json", serialize_for_json(fit_kwargs_export))

    # 4. HPO settings if the run uses AutoGluon HPO; otherwise write null.
    write_json(run_dir / "hpo_kwargs.json", serialize_for_json(hpo_kwargs))

    # 5. Predictions in the same schema expected by Path A metric code.
    # This should include at least: window_id, item_id, timestamp/h_step,
    # model name, mean/median forecast, quantiles, and any indexing fields
    # needed to join realised values.
    predictions.to_parquet(run_dir / "predictions.parquet")

    # 6. Metrics produced by the frozen Path A evaluation package.
    # Prefer both detailed and summary outputs if available.
    metrics["by_ticker_horizon"].to_csv(run_dir / "metrics.csv", index=False)
    metrics["summary"].to_json(run_dir / "summary_metrics.json", indent=2)

    # 7. Runtime / size / hardware information.
    write_json(run_dir / "runtime.json", runtime)

    # 8. Human-readable run summary.
    # This is not the final decision; it is only a compact record of this run.
    write_json(
        run_dir / "summary.json",
        {
            "step_id": runtime["step_id"],
            "run_id": runtime["run_id"],
            "primary_metric": metrics["summary"].get("primary_metric"),
            "model_name": metrics["summary"].get("model_name"),
            "comparison_note": "comparison to B0 zero-shot is computed later in aggregate comparison",
            "fit_seconds": runtime["fit_seconds"],
            "predict_seconds": runtime["predict_seconds"],
            "notes": "candidate run; selection happens in aggregate comparison",
        },
    )

    # 9. Store or reference the AutoGluon predictor artifact.
    # AutoGluon already writes artifacts under predictor.path.
    # This file records where they are, so later code can reload the model.
    (run_dir / "model_artifact_path.txt").write_text(str(predictor.path))

    # 10. Optional reproducibility metadata.
    # Examples: git commit, notebook hash, package versions, CUDA/GPU info.
    write_json(run_dir / "environment.json", collect_environment_info())
```

Minimum required output files per run:

```text
config_snapshot.yaml
hyperparameters.json
fit_kwargs.json
predictions.parquet
metrics.csv
summary_metrics.json
runtime.json
summary.json
model_artifact_path.txt
environment.json
```

### 3.4 Shared fit kwargs

Default fit settings:

```python
FIT_DEFAULT = {
    "num_val_windows": CFG.num_val_windows,
    "val_step_size": CFG.walk_forward_shift,
    "refit_every_n_windows": 1,
}
```

For short intraday histories, reduce `num_val_windows` only if the shortest item does not have enough usable history.

### 3.5 Cross-learning default

For this project, `cross_learning=True` is part of the default Chronos-2 setup, not a late optional trick. The experiment is explicitly about whether Chronos-2 can use relationships among MOEX liquid assets, so the main candidate runs should keep cross-learning enabled.

Recommended default:

```python
CHRONOS2_DEFAULTS = {
    "cross_learning": True,
    "batch_size": 64,
}
```

B5 does **not** introduce cross-learning. B5 tests whether the cross-learning result is stable to batch size and, only as a diagnostic fallback, whether disabling cross-learning removes instability. If `cross_learning=False` performs better, this is an important negative finding about the multivariate/group-attention assumption, not the default target configuration.

---

## 4. Experiment matrix

The matrix is ordered from cheapest and least overfit-prone to most complex. Do not skip directly to full fine-tuning or HPO.

The detailed comparison logic is centralised in Sections 5 and 9. Therefore each B-step only states what changes and what output it contributes to the final comparison.

---

### B0 — AutoGluon zero-shot reproduction

Purpose: verify that AutoGluon zero-shot produces results consistent with the frozen Path A zero-shot baseline.

What changes:

```text
No fine-tuning. This is a harness check.
```

Hyperparameters:

```python
B0_HYPERPARAMETERS = {
    "Chronos2": {
        "fine_tune": False,
        "context_length": CFG.context_length,
        **CHRONOS2_DEFAULTS,
        "ag_args": {"name_suffix": "ZeroShot"},
    }
}
```

Run:

```python
result_b0 = run_path_b_experiment(
    step_id="b0_autogluon_zeroshot",
    run_id="seed_main",
    CFG=CFG,
    RUN_DIR=RUN_DIR,
    train_data=train_data,
    eval_windows=eval_windows,
    known_covariates_by_window=known_covariates_by_window,
    hyperparameters=B0_HYPERPARAMETERS,
    random_seed=CFG.seed,
    fit_kwargs_extra=FIT_DEFAULT,
)
```

Selection role:

```text
B0 is the only hard prerequisite. If it does not reproduce Path A zero-shot within expected tolerance, fix the harness before interpreting any fine-tuning result.
```

---

### B1 — Minimal LoRA smoke run

Purpose: provide the cheapest fine-tuned candidate.

What changes relative to B0:

```text
This run trains only one LoRA fine-tuned Chronos-2 candidate.
The zero-shot reference is not included here; it is B0.
```

Start with LoRA because it is cheaper and less overfit-prone than full fine-tuning.

Hyperparameters:

```python
B1_HYPERPARAMETERS = {
    "Chronos2": {
        "fine_tune": True,
        "fine_tune_mode": "lora",
        "fine_tune_lr": 1e-5,
        "fine_tune_steps": 300,
        "fine_tune_batch_size": 8,
        "context_length": CFG.context_length,
        "fine_tune_context_length": min(CFG.context_length, 2048),
        **CHRONOS2_DEFAULTS,
        "ag_args": {"name_suffix": "LoRA_Min"},
    }
}
```

Run:

```python
result_b1 = run_path_b_experiment(
    step_id="b1_lora_min",
    run_id="seed_main",
    CFG=CFG,
    RUN_DIR=RUN_DIR,
    train_data=train_data,
    eval_windows=eval_windows,
    known_covariates_by_window=known_covariates_by_window,
    hyperparameters=B1_HYPERPARAMETERS,
    random_seed=CFG.seed,
    fit_kwargs_extra=FIT_DEFAULT,
)
```

Selection role:

```text
B1 is the reference fine-tuned candidate. It is not automatically promoted or rejected here; it is compared with all other B-runs in the final aggregation block.
```

---

### B2 — Minimal LoRA repeatability check

Purpose: estimate training variance for the cheapest fine-tuned candidate.

What changes relative to B1:

```text
No hyperparameter change. Repeat B1 with several seeds.
```

Hyperparameters:

```python
B2_HYPERPARAMETERS = B1_HYPERPARAMETERS
B2_SEEDS = [1, 2, 3]
```

Run:

```python
results_b2 = []
for seed in B2_SEEDS:
    results_b2.append(
        run_path_b_experiment(
            step_id="b2_lora_repeatability",
            run_id=f"seed_{seed}",
            CFG=CFG,
            RUN_DIR=RUN_DIR,
            train_data=train_data,
            eval_windows=eval_windows,
            known_covariates_by_window=known_covariates_by_window,
            hyperparameters=B2_HYPERPARAMETERS,
            random_seed=seed,
            fit_kwargs_extra=FIT_DEFAULT,
        )
    )
```

Selection role:

```text
B2 estimates seed-to-seed noise. Later improvements should be interpreted relative to this noise floor.
```

---

### B3 — LoRA schedule sweep

Purpose: create candidate LoRA schedules and show whether the minimal setup underfits or overfits.

What changes relative to B1/B2:

```text
Only LoRA schedule parameters change: steps, learning rate, and fine-tune batch size.
```

Recommended staged grid:

```yaml
fine_tune_steps: [100, 300, 1000]
fine_tune_lr: [1e-5, 3e-5]
fine_tune_batch_size: [8, 16]
```

Do not search all combinations blindly at first. Use a staged sweep for compute control:

1. fix LR and batch size, sweep steps;
2. run LR variants around the best-looking step count;
3. run batch-size variants only if GPU memory, training instability, or runtime requires it.

Hyperparameter template:

```python
def make_b3_hyperparameters(*, steps, lr, fine_tune_batch_size):
    return {
        "Chronos2": {
            "fine_tune": True,
            "fine_tune_mode": "lora",
            "fine_tune_lr": lr,
            "fine_tune_steps": steps,
            "fine_tune_batch_size": fine_tune_batch_size,
            "context_length": CFG.context_length,
            "fine_tune_context_length": min(CFG.context_length, 2048),
            **CHRONOS2_DEFAULTS,
            "ag_args": {"name_suffix": f"LoRA_steps{steps}_lr{lr}_ftbs{fine_tune_batch_size}"},
        }
    }
```

Run:

```python
results_b3 = []
for params in B3_GRID_STAGED:
    results_b3.append(
        run_path_b_experiment(
            step_id="b3_lora_schedule",
            run_id=f"steps_{params.steps}_lr_{params.lr}_ftbs_{params.fine_tune_batch_size}",
            CFG=CFG,
            RUN_DIR=RUN_DIR,
            train_data=train_data,
            eval_windows=eval_windows,
            known_covariates_by_window=known_covariates_by_window,
            hyperparameters=make_b3_hyperparameters(**params),
            random_seed=CFG.seed,
            fit_kwargs_extra=FIT_DEFAULT,
        )
    )
```

Local reference selection:

B3 is a parameter-search family, so it should produce a local reference LoRA configuration for later runs. The important rule is that the choice is made **after all planned B3 candidates are run and written**, not inside the training loop.

Recommended procedure:

```python
b3_table = collect_path_b_runs(step_id="b3_lora_schedule")

REFERENCE_LORA_RUN_ID = choose_reference_candidate(
    runs=b3_table,
    primary_key="delta_vs_b0",
    stability_keys=[
        "overfit_flag",
        "delta_h2_vs_b0",
        "delta_h3_vs_b0",
        "delta_h5_vs_b0",
        "fit_seconds",
    ],
    preference="simplest_with_good_score",
)

REFERENCE_LORA_CONFIG = load_hyperparameters(REFERENCE_LORA_RUN_ID)
REFERENCE_LORA_STEPS = REFERENCE_LORA_CONFIG["Chronos2"]["fine_tune_steps"]
REFERENCE_LORA_LR = REFERENCE_LORA_CONFIG["Chronos2"]["fine_tune_lr"]
REFERENCE_LORA_FINE_TUNE_BATCH_SIZE = REFERENCE_LORA_CONFIG["Chronos2"]["fine_tune_batch_size"]
```

Selection role:

```text
B3 contributes all schedule candidates to the final comparison table. It also defines REFERENCE_LORA_CONFIG for later experiment families. This is a local reference, not a final winner. All B3 runs remain visible in aggregate comparison.
```

---

### B4 — Training universe expansion

Purpose: test whether more cross-series training data helps fine-tuning.

What changes relative to B1/B3:

```text
The training universe may expand. The evaluation universe stays frozen.
```

Hyperparameters:

```python
B4_HYPERPARAMETERS = REFERENCE_LORA_CONFIG  # usually selected locally from B3 after all B3 candidates are logged
```

Training-universe candidates are defined outside the matrix in Section 6.

Run:

```python
results_b4 = []
for universe_id, train_data_u in TRAINING_UNIVERSE_CANDIDATES.items():
    results_b4.append(
        run_path_b_experiment(
            step_id="b4_training_universe",
            run_id=f"universe_{universe_id}",
            CFG=CFG,
            RUN_DIR=RUN_DIR,
            train_data=train_data_u,
            eval_windows=eval_windows,  # frozen evaluation windows
            known_covariates_by_window=known_covariates_by_window,
            hyperparameters=B4_HYPERPARAMETERS,
            random_seed=CFG.seed,
            fit_kwargs_extra=FIT_DEFAULT,
        )
    )
```

Selection role:

```text
B4 tells whether a larger training universe improves the frozen evaluation universe. Extra series are useful only if they help the frozen evaluation task.
```

---

### B5 — Cross-learning and batch-size stability

Purpose: test whether the cross-learning result is stable to batch composition and batch size.

What changes relative to the local reference LoRA configuration:

```text
Main variants keep cross_learning=True and change inference batch_size.
One cross_learning=False variant may be run as a diagnostic fallback, not as the default experiment target.
```

Why cross-learning is not introduced here:

```text
For this project, cross_learning=True is the default in B0–B4 because the core hypothesis is that Chronos-2 can use dependencies among MOEX assets. B5 only checks whether that multivariate/group behavior is stable.
```

Fine-tuning batch size and inference batch size are separate knobs:

```text
fine_tune_batch_size = training minibatch size
batch_size           = inference/cross-learning batch size
```

Hyperparameter variants:

```python
def make_b5_hyperparameters(*, cross_learning, batch_size):
    hp = copy.deepcopy(REFERENCE_LORA_CONFIG)

    # Reference LoRA hyperparameters should contain one fine-tuned candidate, not a zero-shot arm.
    hp["Chronos2"]["cross_learning"] = cross_learning
    hp["Chronos2"]["batch_size"] = batch_size
    return hp

B5_GRID = [
    {"cross_learning": True,  "batch_size": 32,  "role": "main_stability"},
    {"cross_learning": True,  "batch_size": 64,  "role": "main_stability"},
    {"cross_learning": True,  "batch_size": 128, "role": "main_stability"},
    {"cross_learning": False, "batch_size": 64,  "role": "diagnostic_ablation"},
]
```

Run:

```python
results_b5 = []
for params in B5_GRID:
    results_b5.append(
        run_path_b_experiment(
            step_id="b5_cross_learning_stability",
            run_id=f"cross_{params['cross_learning']}_batch_{params['batch_size']}_{params['role']}",
            CFG=CFG,
            RUN_DIR=RUN_DIR,
            train_data=REFERENCE_OR_EXPANDED_TRAIN_DATA,
            eval_windows=eval_windows,
            known_covariates_by_window=known_covariates_by_window,
            hyperparameters=make_b5_hyperparameters(
                cross_learning=params["cross_learning"],
                batch_size=params["batch_size"],
            ),
            random_seed=CFG.seed,
            fit_kwargs_extra=FIT_DEFAULT,
        )
    )
```

Selection role:

```text
B5 should normally keep cross_learning=True and choose a stable batch_size. If cross_learning=False clearly performs better or is much more stable, report this as evidence against the cross-series assumption for the selected dataset.
```

---

### B6 — Full fine-tuning

Purpose: create a full fine-tuning candidate that updates all weights instead of LoRA adapters.

What changes relative to LoRA candidates:

```text
fine_tune_mode changes from "lora" to "full".
fine_tune_lr is reduced.
Other knobs are inherited from the local reference LoRA run, usually chosen from B3.
```

Full fine-tuning is more expensive and more overfit-prone, so it should be run only if the timing pilot suggests it is feasible or if LoRA gives enough signal to justify the cost.

Hyperparameters:

```python
B6_HYPERPARAMETERS = {
    "Chronos2": {
        "fine_tune": True,
        "fine_tune_mode": "full",
        "fine_tune_lr": 1e-6,
        "fine_tune_steps": REFERENCE_LORA_STEPS,
        "fine_tune_batch_size": REFERENCE_LORA_FINE_TUNE_BATCH_SIZE,
        "context_length": CFG.context_length,
        "fine_tune_context_length": min(CFG.context_length, 2048),
        "cross_learning": True,
        "batch_size": REFERENCE_BATCH_SIZE,
        "ag_args": {"name_suffix": "FullFT"},
    }
}
```

Run:

```python
result_b6 = run_path_b_experiment(
    step_id="b6_full_ft",
    run_id="full_ft_reference",
    CFG=CFG,
    RUN_DIR=RUN_DIR,
    train_data=REFERENCE_OR_EXPANDED_TRAIN_DATA,
    eval_windows=eval_windows,
    known_covariates_by_window=known_covariates_by_window,
    hyperparameters=B6_HYPERPARAMETERS,
    random_seed=CFG.seed,
    fit_kwargs_extra=FIT_DEFAULT,
)
```

Selection role:

```text
B6 contributes a high-capacity candidate. It is adopted only in the aggregate comparison if it justifies its extra runtime and overfitting risk.
```

---

### B7 — Narrow HPO

Purpose: refine a configuration after the useful region is roughly known. HPO is not a substitute for the matrix above.

What changes relative to the local reference manual configuration:

```text
Only learning rate and number of fine-tuning steps are searched.
```

Do not HPO-search:

```text
metric definition
covariate set
data format
horizon
interval
holdout window
evaluation universe
cross_learning default assumption
```

Those are Part A or experiment-design decisions and must remain frozen.

Hyperparameters:

```python
from autogluon.common import space

B7_HYPERPARAMETERS = {
    "Chronos2": {
        "fine_tune": True,
        "fine_tune_mode": REFERENCE_MODE,
        "context_length": CFG.context_length,
        "fine_tune_context_length": min(CFG.context_length, 2048),
        "fine_tune_lr": space.Real(LR_LO, LR_HI, log=True),
        "fine_tune_steps": space.Int(STEP_LO, STEP_HI),
        "fine_tune_batch_size": REFERENCE_FINE_TUNE_BATCH_SIZE,
        "cross_learning": True,
        "batch_size": REFERENCE_BATCH_SIZE,
        "ag_args": {"name_suffix": "HPO_FT"},
    }
}

B7_HPO_KWARGS = {
    "searcher": "bayes",
    "num_trials": 12,
}
```

Run:

```python
result_b7 = run_path_b_experiment(
    step_id="b7_hpo",
    run_id="bayes_lr_steps_12_trials",
    CFG=CFG,
    RUN_DIR=RUN_DIR,
    train_data=REFERENCE_OR_EXPANDED_TRAIN_DATA,
    eval_windows=eval_windows,
    known_covariates_by_window=known_covariates_by_window,
    hyperparameters=B7_HYPERPARAMETERS,
    random_seed=CFG.seed,
    fit_kwargs_extra=FIT_DEFAULT,
    hpo_kwargs=B7_HPO_KWARGS,
)
```

Selection role:

```text
B7 contributes an HPO candidate. It is adopted only if the aggregate comparison shows a non-marginal gain over simpler manual configurations.
```

---

### B8 — Final refit and locked holdout

Purpose: train the selected final configuration and evaluate it on the locked holdout.

What changes relative to the selected configuration:

```text
No model-search change. The selected configuration is refit once after all decisions are locked.
```

Final hyperparameters:

```python
FINAL_CONFIG = SELECTED_CONFIG_FROM_AGGREGATE_COMPARISON
```

Run:

```python
result_final = run_path_b_experiment(
    step_id="b8_final_holdout",
    run_id="final_refit_locked_holdout",
    CFG=CFG,
    RUN_DIR=RUN_DIR,
    train_data=FINAL_TRAIN_DATA,
    eval_windows=LOCKED_HOLDOUT_WINDOWS,
    known_covariates_by_window=known_covariates_by_window_holdout,
    hyperparameters=FINAL_CONFIG,
    random_seed=FINAL_SEED,
    fit_kwargs_extra={
        "num_val_windows": CFG.num_val_windows,
        "val_step_size": CFG.walk_forward_shift,
        "refit_every_n_windows": 1,
        "refit_full": True,
    },
)
```

Important caveats:

- `refit_full=True` retrains using all training data, including data that was previously held out for validation inside the training period.
- Use `refit_full` only after the configuration is locked.
- Do not use the final holdout window for selecting any knob.
- If external `tuning_data` is passed, AutoGluon disables multi-window backtesting and `refit_full`, so prefer internal validation windows unless there is a specific reason to provide `tuning_data`.

Final evaluation compares:

```text
zero-shot AutoGluon Chronos-2
vs
final fine-tuned AutoGluon Chronos-2
```

on the locked holdout windows using the frozen Part A evaluation package.

---

### One-page experiment matrix summary

| Step | Purpose | What changes | Main run object | Selection role |
|---|---|---|---|---|
| B0 | Harness check | AutoGluon zero-shot only | `B0_HYPERPARAMETERS` | Must reproduce Path A before any FT result is trusted |
| B1 | Minimal fine-tune candidate | Add LoRA, 300 steps, low LR | `B1_HYPERPARAMETERS` | Cheapest FT candidate |
| B2 | Repeatability | Same config, multiple seeds | `B2_HYPERPARAMETERS`, `B2_SEEDS` | Estimates seed noise floor |
| B3 | Schedule variants | Steps/LR/fine-tune batch size | `make_b3_hyperparameters(...)` | Candidate LoRA schedules + local `REFERENCE_LORA_CONFIG` |
| B4 | More training series | Training universe only | `B4_HYPERPARAMETERS` + universe candidates | Tests benefit of more cross-series training data |
| B5 | Cross-learning stability | `batch_size`, plus diagnostic `cross_learning=False` | `make_b5_hyperparameters(...)` | Checks stability of default cross-learning |
| B6 | Full FT candidate | `fine_tune_mode="full"`, lower LR | `B6_HYPERPARAMETERS` | High-capacity candidate |
| B7 | Narrow HPO candidate | LR/steps only | `B7_HYPERPARAMETERS`, `B7_HPO_KWARGS` | HPO candidate, compared against manual configs |
| B8 | Locked holdout | Refit final config | `FINAL_CONFIG` | Final confirmation only |

The most important discipline: **Path B does not redesign the experiment. It only tests whether AutoGluon fine-tuning improves the already validated Part A setup.**

---

## 5*. Logging, timing, and result comparison

This block is independent of the tuning type. It consumes Path B outputs from B0–B8 and decides whether anything was gained.

### 5.1 Required artifacts per run

Recommendations:

- Each candidate run should have its own immutable directory.
- Do not overwrite previous runs, even if the result is worse.
- Keep raw predictions, not only metrics. Metric definitions may need to be re-run without re-fitting.
- Store enough metadata to reload the AutoGluon predictor and reproduce the run.

Required files:

```text
config_snapshot.yaml
hyperparameters.json
fit_kwargs.json
hpo_kwargs.json
predictions.parquet
metrics.csv
summary_metrics.json
summary.json
runtime.json
model_artifact_path.txt
environment.json
```

### 5.2 Runtime measurement recommendations

Every run should record:

- `step_id`, `run_id`, seed, and training-universe ID;
- GPU name and relevant package versions;
- number of training items and rows;
- number of evaluation items and windows;
- prediction length and context length;
- fine-tuning mode, LR, steps, fine-tune batch size;
- cross-learning flag and inference batch size;
- validation-window settings;
- fit time, prediction time, and total time.

Use the first B1 LoRA run as the timing pilot. Treat measured runtime as more reliable than theoretical estimates.

For planning later variants, estimate roughly:

```text
estimated_total_time ≈ pilot_fit_time
                     × step_multiplier
                     × fold_multiplier
                     × validation_multiplier
                     × universe_size_multiplier
```

Use the estimate only for deciding whether a later step is reasonable to run. Do not use it as a result.

### 5.3 Comparison spreadsheet recommendations

Maintain one append-only table across all Path B runs:

```text
runs/path_b/path_b_runs.csv
```

Recommended columns:

```text
run_id
step_id
parent_run_id
seed
train_universe_id
eval_universe_id
interval
context_length
prediction_length
fine_tune
fine_tune_mode
fine_tune_lr
fine_tune_steps
fine_tune_batch_size
batch_size
cross_learning
num_val_windows
n_items_train
n_rows_train
fit_seconds
predict_seconds
primary_score
primary_score_b0
delta_vs_b0
score_h2
score_h2_b0
delta_h2_vs_b0
score_h3
score_h3_b0
delta_h3_vs_b0
score_h5
score_h5_b0
delta_h5_vs_b0
coverage
coverage_b0
delta_coverage_vs_b0
overfit_flag
runtime_flag
selected_candidate
notes
```

Recommendations:

- Use one row per run, not one row per experiment family.
- Keep `selected_candidate` false until the aggregate selection stage.
- Use generic `primary_score_*` names if Part A may later rename the final metric package.
- Add detailed per-ticker/per-horizon metrics as separate CSVs rather than forcing them into the main run table.

### 5.4 Plotting recommendations

The plots should help answer four questions:

```text
Did fine-tuning improve the frozen evaluation package?
Is the improvement broad or concentrated?
Is the improvement stable across seeds/folds?
How much runtime did the improvement cost?
```

Recommended plots for all runs:

- `delta_by_run.png`: each candidate run's score minus the B0 zero-shot reference score.
- `delta_by_horizon.png`: delta for h=2, h=3, h=5.
- `delta_by_ticker_heatmap.png`: ticker × horizon delta for selected candidate runs.
- `runtime_vs_delta.png`: fit time against metric lift.
- `coverage_candidate_vs_b0.png`: calibration comparison against the B0 zero-shot reference.

Recommended plots for specific experiment families:

- B2 repeatability: seed-to-seed distribution of metric deltas.
- B3 schedule sweep: heatmap or line plot of steps/LR against metric delta and overfitting flags.
- B4 universe expansion: metric delta against number of training items / rows.
- B5 cross-learning stability: batch size against metric delta with `cross_learning=True`; diagnostic comparison to `cross_learning=False`.
- B6 full FT: full FT vs best LoRA candidate, including runtime ratio.
- B7 HPO: trial score vs LR/steps, plus comparison against the best manual configuration.

Final comparison plots:

- `final_delta_by_ticker_horizon.png`
- `final_delta_distribution_by_window.png`
- `final_runtime_vs_gain.png`
- `final_candidate_ranking.png`

### 5.5 Result comparison and selection recommendations

Selection happens after candidate runs are logged, not inside individual B-step runners. However, local reference selection is allowed inside parameter-search families after the full family is complete. For example, B3 can choose `REFERENCE_LORA_CONFIG` for B4/B5/B6/B7 once all B3 variants are written to disk.

Distinguish three levels:

```text
run-level: train one candidate and write outputs; no selection
family-level: choose a local reference after all variants in that family are logged
project-level: choose final Path B candidate after aggregate comparison and holdout
```

Recommended comparison order:

1. **Harness validity**: B0 must reproduce AutoGluon zero-shot close enough to Path A zero-shot.
2. **Primary improvement**: rank all candidates by the frozen Part A primary score delta versus the B0 AutoGluon zero-shot reference.
3. **Stability**: prefer candidates whose improvement is consistent across seeds, folds, tickers, and horizons.
4. **Calibration and magnitude sanity**: reject or flag candidates whose probabilistic calibration or prediction magnitude becomes unstable.
5. **Runtime**: prefer a simpler/cheaper candidate if improvement is similar.
6. **Complexity penalty**: if LoRA and full FT are close, keep LoRA; if manual schedule and HPO are close, keep the manual schedule.
7. **Holdout confirmation**: the final selected candidate must be evaluated once on the locked holdout.

Useful selection outputs:

```text
candidate_ranking.csv
selected_candidate.json
selection_report.md
```

`selection_report.md` should explain:

- which candidate was selected;
- which candidates were rejected or left as inconclusive;
- whether the selected candidate improved over the B0 zero-shot reference;
- whether the improvement is large enough relative to seed/fold noise;
- runtime cost of the selected candidate;
- whether the result should proceed to final holdout.

A recommended selection rule:

```text
Choose the simplest candidate that improves the frozen Part A evaluation package over the B0 AutoGluon zero-shot reference, remains stable under overfitting checks, and has acceptable runtime. If no candidate improves but additional cheap runs remain, continue logging them. If no candidate improves and the remaining experiments are expensive, stop Path B and report a negative result.
```

---

## 6. Dataset sizes, candidate lengths, and transfer of choices

This section is a design plan, not a ticker-selection plan and not a filled cache inventory. The exact number of rows, missing bars, nonzero-return share, and effective training-window counts must be measured after the Part A cache is built.

The guiding principle is:

```text
- Section 6 controls only context-length instances, dataset-size feasibility checks, quality thresholds, and transfer rules.
- The ticker universe is inherited from Path A. Do not tune ticker-pack size inside Path B.
- The project goal is to catch local inefficiencies, so 10m and 60m are the primary regimes.
- 1d remains useful, but as a secondary low-frequency benchmark, not as the main local-inefficiency regime.
- After the context probe, transfer one reference context per interval into B2–B8.
```

---

## 6.1 Context-length intervals for local inefficiencies

Path B should test a **small interval** of plausible context lengths per frequency, not a single value. The instances should be interpretable:

```text
CTX_SHORT = intentionally short local-memory diagnostic
CTX_MAIN   = recommended default for the interval
CTX_LONG   = long-memory diagnostic inside the local-efficiency design
```

### 6.1.1 Main interpretation by interval

| Interval | Forecast horizon meaning with `H=5` | Role in local-inefficiency study | Decision |
|---|---|---|---|
| `10m` | h=2/3/5 means 20/30/50 minutes | Primary micro/local regime | Keep as primary. |
| `60m` | h=2/3/5 means 2/3/5 hours | Primary several-hours regime | Keep as primary. |
| `1d` | h=2/3/5 means 2/3/5 trading days | Secondary low-frequency benchmark | Keep, but shorten context. |

Do **not** replace `1d` with a separate “several-hours” regime. Several-hours inefficiency is already represented by `60m` at h=2/3/5. Replacing daily with another intraday frequency would duplicate the 60m experiment and would remove the useful daily benchmark.

### 6.1.2 Context instances to run

| Interval | Plausible local context interval | `CTX_SHORT` | `CTX_MAIN` recommended | `CTX_LONG` | Argumentation |
|---|---:|---:|---:|---:|---|
| `1d` | `20–128` | `20` | `64` | `128` | Daily local inefficiency should use weeks-to-months of memory, not a full trading year. `20` tests roughly one trading month, `64` is a quarter-like middle value, and `128` tests whether half-year memory helps without making 1d a regime-memory experiment. |
| `60m` | `64–512` | `128` | `256` | `384` | This is the clean several-hours regime. `128` keeps memory strongly recent, `256` gives enough repeated intraday patterns, and `384` tests broader intraday state. |
| `10m` | `256–1152` | `384` | `768` | `1152` | This is the main local/microstructure regime. `384` is a short local diagnostic, `768` is the recommended balance, and `1152` tests whether a few extra weeks of intraday behavior help. Very long contexts can add stale microstructure noise. |

### 6.1.3 Daily long-context diagnostic

The old daily value `250` should not be the default if the goal is local inefficiencies. `250` daily bars is roughly one trading year, so it mainly tests regime memory, seasonality, and macro-state adaptation.

Keep it only as a marked diagnostic:

```yaml
CTX_REGIME_MEMORY_DAILY*:
  interval: 1d
  context_length: 250
  role: "optional daily long-context diagnostic; not the local default"
```

Use this diagnostic only if the daily local contexts are weak or if Part A suggests daily performance is driven by slow regimes rather than short-term inefficiencies.

### 6.1.4 Recommended default

Use `CTX_MAIN` unless the context probe shows a clear reason to use `CTX_SHORT` or `CTX_LONG`.

```yaml
CTX_MAIN:
  1d: 64
  60m: 256
  10m: 768
```

---

## 6.2 Context length / dataset size ratios

This is the main feasibility question for Section 6. Since the ticker universe is fixed by Part A, the important quantity is not “how many tickers should we add?” but:

```text
Given N fixed target items and item length L, is context length C too large for the available dataset?
```

Definitions:

```text
N = number of target items inherited from Part A
L_i = usable train length of item i after regularization and train/eval split
C = context_length
H = prediction_length = 5
V = num_val_windows = 3
```

### 6.2.1 Hard and useful length ratios

Mechanical feasibility:

```text
min_length_hard = C + H * V = C + 15
```

This only prevents obvious technical failure. It does not mean the item is useful for fine-tuning.

Useful ratio checks:

| Ratio | Formula | Interpretation | Recommended band |
|---|---|---|---|
| Hard item ratio | `min(L_i) / C` | Does every fixed target item have enough history for the chosen context? | Must be `> 1`; practically `>= 1 + 15/C` |
| Useful item ratio | `min(L_i) / C` | Is the weakest item still useful, not only technically valid? | Prefer `>= 2` |
| Median item ratio | `median(L_i) / C` | Does a typical item provide several different contexts? | Prefer `>= 5` |
| Panel reservoir ratio | `sum_i max(0, L_i - C - H + 1) / (N * C)` | How many possible training windows exist relative to context width? | `20–50` acceptable, `>50` strong, `<20` risky |

The panel reservoir ratio is a planning heuristic, not a statistical guarantee. It detects when the context is so long that the fixed dataset produces too few distinct training contexts.

### 6.2.2 Plausible ratio implications under local contexts

Exact ratios must be computed after cache inspection. Before that, the expected qualitative picture is:

| Interval | Context instance | Ratio expectation | Practical implication |
|---|---|---|---|
| `1d` | `20 / 64 / 128` | Stronger than the old `250 / 500` setup | More aligned with local daily inefficiency; less risk of annual regime mixing. |
| `1d` | `250*` diagnostic | Usually feasible but conceptually different | Treat as regime-memory check, not as the local benchmark. |
| `60m` | `128 / 256 / 384` | Usually strong | Best representation of several-hour inefficiencies. |
| `10m` | `384 / 768 / 1152` | Usually strong because intraday data has many bars | Best representation of micro/local inefficiencies; long context must still pass overfitting checks. |

### 6.2.3 Dataset-size status table

| Field | Value / source | Purpose |
|---|---|---|
| Target universe | inherited from Part A | No ticker-pack choice in Section 6. |
| `N` target items | measured from Part A locked universe | Used in panel reservoir ratio. |
| Intervals | `1d`, `60m`, `10m` | All three are tested, but `10m` and `60m` are primary for local inefficiencies. |
| Context instances | `CTX_SHORT`, `CTX_MAIN`, `CTX_LONG` | Small context probe. |
| Optional diagnostic | `1d context=250*` | Daily regime-memory diagnostic only. |
| `L_min`, `L_median` per interval | measured after cache build | Used for hard/useful/median ratios. |
| Panel reservoir ratio per context | computed after cache build | Decides whether a context is feasible or risky. |
| Final `REFERENCE_CONTEXT_BY_INTERVAL` | selected after `B1_context_probe` | Passed to B2–B8. |

---

## 6.3 Thresholds and why they are needed

Thresholds are needed for auditability and comparability. They protect against fake predictability from missing bars, ffill-created zero returns, stale prices, bad candles, and unresolved jumps. In cross-learning mode, a problematic target series can affect other target series in the same batch, so quality diagnostics matter even when the target universe is fixed.

Because the target universe is fixed by Part A, these thresholds should usually produce **flags**, not silent ticker removal. If a fixed Part A ticker fails a threshold, the run should record the issue and follow the Part A drop/keep rule for that interval.

Use interval-specific thresholds because daily, hourly, and 10m data have different noise and missingness profiles.

### 6.3.1 Compact threshold rules

```text
Missing bars: measure missing share before forward-fill on the regularized session grid.
Useful history: hard minimum = C + 15; useful minimum = 2C; median target = 5C.
Nonzero-return share: low share flags stale or illiquid behavior.
Extreme jumps: inspection triggers, not automatic deletion rules.
```

A real market event is not a data error; an unresolved bad candle is.

### 6.3.2 Threshold summary table

| Check | `1d` threshold | `60m` threshold | `10m` threshold | What it means |
|---|---:|---:|---:|---|
| Missing share before ffill | `<= 2%` | `<= 3%` | `<= 5%` | Above this, ffill may contaminate returns. |
| Hard minimum length | `C + 15` | `C + 15` | `C + 15` | Minimum for `prediction_length=5`, `num_val_windows=3`. |
| Useful minimum length | `>= 2C` | `>= 2C` | `>= 2C` | Below this, the item is technically valid but weak for fine-tuning. |
| Median length target | `>= 5C` | `>= 5C` | `>= 5C` | Preferred dataset-size/context ratio for stable fine-tuning. |
| Nonzero-return share | `>= 90%` | `>= 75%` | `>= 65%` | Flags stale/flat series behavior. |
| Extreme absolute log-return inspection trigger | `> 25%` | `> 12%` | `> 8%` | Inspect for corporate action, bad candle, suspension/reopening, or genuine event. |
| Panel reservoir ratio | `>= 20` acceptable, `> 50` strong | same | same | Checks whether fixed dataset is large enough relative to context width. |

---


## 6.4 Validation settings

Use:

```python
NUM_VAL_WINDOWS = 3
VAL_STEP_SIZE = CFG.walk_forward_shift
REFIT_EVERY_N_WINDOWS = 1
```

Rationale:

```text
num_val_windows = 3 is a good compromise between validation stability and runtime.
More validation windows increase training cost and are not the main object of Path B.
```

`auto` is allowed only as a fallback or explicitly logged diagnostic if AutoGluon rejects the planned validation setting for short histories. It should not silently replace `num_val_windows = 3`.

External `tuning_data` should be avoided unless there is a specific reason, because it changes validation/refit behavior and makes comparison less clean.

---


## 6.5 Final recommended defaults

If Part A does not force a different choice, start Path B with:

```yaml
path_b_section_6_defaults:
  intervals_to_test: [1d, 60m, 10m]
  primary_local_intervals: [10m, 60m]
  secondary_interval: 1d
  target_universe: inherited_from_path_a
  choose_new_tickers_in_path_b: false

  prediction_length: 5
  num_val_windows: 3
  val_step_size: CFG.walk_forward_shift
  refit_every_n_windows: 1

  context_instances:
    CTX_SHORT:
      role: "short diagnostic; intentionally local-memory"
      1d: 20
      60m: 128
      10m: 384
    CTX_MAIN:
      role: "recommended local-efficiency default"
      1d: 64
      60m: 256
      10m: 768
    CTX_LONG:
      role: "long-memory diagnostic inside local-efficiency design"
      1d: 128
      60m: 384
      10m: 1152

  optional_context_diagnostics:
    CTX_REGIME_MEMORY_DAILY*:
      1d: 250
      role: "daily regime-memory diagnostic; not local default"

  reference_context_default: CTX_MAIN

  dataset_size_checks:
    hard_min_length: context_length + 15
    useful_min_length: 2 * context_length
    median_length_target: 5 * context_length
    panel_reservoir_ratio_acceptable: 20
    panel_reservoir_ratio_strong: 50

  thresholds:
    missing_share_max:
      1d: 0.02
      60m: 0.03
      10m: 0.04
    nonzero_return_min_share:
      1d: 0.90
      60m: 0.75
      10m: 0.70
    extreme_abs_log_return_inspection_trigger:
      1d: 0.25
      60m: 0.12
      10m: 0.06

  proxies:
    use_as_targets: false
    use_as_covariates_if_part_a_selected: true
```

## 7*. Overfitting checks specific to Path B

Overfitting is not checked by one number. It is checked by a structured set of diagnostics comparing fine-tuned candidates against zero-shot, against their own validation behavior, and against stability slices.

### 7.1 Loss-vs-evaluation mismatch

Suspicious pattern:

```text
AutoGluon training/validation loss improves,
but the frozen Part A evaluation package does not improve.
```

Checks:

- record AutoGluon validation score for every candidate;
- record frozen Path A score for the same candidate;
- plot validation score vs frozen evaluation delta;
- flag candidates where validation improves but frozen evaluation gets worse.

Interpretation:

```text
If loss improves but the frozen evaluation package does not, do not call the run successful. It may still be logged as a candidate, but it should receive an overfitting/objective-mismatch flag.
```

### 7.2 Seed stability

Suspicious pattern:

```text
One seed improves, another seed is flat or negative.
```

Checks:

- run B2 for minimal LoRA;
- repeat the final candidate with at least 2–3 seeds if compute allows;
- compute mean, standard deviation, min, and max of metric deltas across seeds;
- compare candidate improvement to the B2 `LORA_NOISE_FLOOR`.

Interpretation:

```text
If the measured lift is not meaningfully larger than seed noise, mark the result inconclusive even if one run looks positive.
```

### 7.3 Fold/window stability

Suspicious pattern:

```text
Average score improves because of one or two lucky folds/windows.
```

Checks:

- save per-window and per-fold deltas;
- plot the distribution of paired fine-tuned minus zero-shot differences;
- report median delta as well as mean delta;
- check how many folds/windows are positive.

Interpretation:

```text
A broad small improvement is more trustworthy than a large average driven by a few windows.
```

### 7.4 Ticker and horizon concentration

Suspicious pattern:

```text
Only one ticker or one horizon explains nearly all lift.
```

Checks:

- compute score delta by ticker;
- compute score delta by horizon;
- compute ticker × horizon heatmap;
- report number/share of tickers with non-negative delta;
- inspect h=2, h=3, h=5 separately.

Interpretation:

```text
If the project-level lift is concentrated in one ticker/horizon cell, report it as narrow rather than general fine-tuning improvement.
```

### 7.5 Regime/time-block stability

Suspicious pattern:

```text
Fine-tuning helps in one market regime but hurts elsewhere.
```

Checks:

- reuse Part A regime/time-block slices;
- compute fine-tuned minus zero-shot delta for each block;
- check whether the final candidate collapses in any block;
- compare pre/post-2022 and recent holdout behavior if available.

Interpretation:

```text
A candidate does not need to win every regime, but severe collapse in one block should be flagged before final selection.
```

### 7.6 Calibration and magnitude stability

Suspicious pattern:

```text
Directional score improves, but quantile coverage or predicted magnitudes become unstable.
```

Checks:

- compare q10–q90 coverage between zero-shot and fine-tuned outputs;
- compare predicted absolute return magnitude distribution;
- check extreme forecast frequency;
- plot predicted magnitude vs realised magnitude if Part A already provides it.

Interpretation:

```text
Fine-tuning that wins direction but destroys calibration may still be useful for a pure directional strategy, but it must be reported as such. It should not be presented as a generally better probabilistic forecast.
```

### 7.7 Runtime-overfitting tradeoff

Suspicious pattern:

```text
A more expensive model gives tiny or unstable improvement.
```

Checks:

- compare fit time against metric delta;
- compute gain per training hour;
- compare LoRA vs full FT and manual vs HPO candidates.

Interpretation:

```text
If full FT/HPO adds little over LoRA while taking much longer, prefer LoRA or report the larger model as not worth the extra complexity.
```

### 7.8 Final overfitting label

Each candidate should receive one of:

```text
OK: no major overfitting sign
FLAGGED_OBJECTIVE_MISMATCH: validation improves but frozen evaluation does not
FLAGGED_SEED_UNSTABLE: seed variance comparable to effect
FLAGGED_CONCENTRATED: lift concentrated in one ticker/horizon/regime
FLAGGED_CALIBRATION: calibration or magnitude materially worsens
FLAGGED_RUNTIME: gain too small for runtime/complexity
INCONCLUSIVE: not enough runs/folds/seeds to decide
```

Path B should prefer a smaller, repeatable LoRA gain over a larger but unstable full fine-tuning gain.

---

## 8*. Directory layout

Recommended output structure:

```text
runs/path_b/
  config_path_b.yaml
  frozen_path_a_config.yaml
  data_schema.json
  path_b_runs.csv
  candidate_ranking.csv
  b0_autogluon_zeroshot/
    seed_main/
      predictions.parquet
      metrics.csv
      summary.json
      runtime.json
  b1_lora_min/
    seed_main/
  b2_lora_repeatability/
    seed_1/
    seed_2/
    seed_3/
  b3_lora_schedule/
    steps_100_lr_1e-5_ftbs_8/
    steps_300_lr_1e-5_ftbs_8/
    steps_1000_lr_1e-5_ftbs_8/
  b4_training_universe/
    universe_U0/
    universe_U1/
    universe_U2/
  b5_cross_learning_stability/
    cross_True_batch_32_main_stability/
    cross_True_batch_64_main_stability/
    cross_True_batch_128_main_stability/
    cross_False_batch_64_diagnostic_ablation/
  b6_full_ft/
    full_ft_reference/
  b7_hpo/
    bayes_lr_steps_12_trials/
  b8_final_holdout/
    final_refit_locked_holdout/
      predictions_zeroshot.parquet
      predictions_finetuned.parquet
      metrics.csv
      summary.json
```

Each run directory must contain:

```text
config snapshot
prediction parquet
metric output
runtime summary
model artifact path
notebook/git hash if available
```

---

## 9. Stop / continue rules

The stop rules should avoid wasting compute, but they should not make the experiment path-dependent too early. A flat result in a cheap step is not automatically a reason to stop. It is a reason to be careful before launching expensive steps.

### 9.1 Hard stop

Stop immediately only if:

```text
B0 does not reproduce Path A zero-shot closely enough
input/output schema does not match the frozen Path A evaluation code
predictions cannot be joined to realised values reliably
the run repeatedly fails technically and cannot produce comparable outputs
```

These are harness/data problems. Fine-tuning results are not interpretable until they are fixed.

### 9.2 Continue despite weak result

Continue if:

```text
the next planned run is cheap or already budgeted
the result is weak but seed/fold noise has not been estimated yet
the experiment family answers a different question, e.g. B4 dataset size or B5 cross-learning stability
runtime is acceptable for the planned scope
```

Example:

```text
If B1 is flat but cheap, still run B2 to estimate seed noise and B3 small schedule variants.
```

### 9.3 Pause before expensive runs

Pause and review before:

```text
full fine-tuning
large expanded-universe runs
HPO
many-fold repetition of a weak candidate
```

Pause condition:

```text
no candidate so far improves the frozen evaluation package
and the next step is expected to be time-demanding
```

The review should check:

- measured B1/B3 runtime;
- whether any horizon/ticker/fold shows promising signal;
- whether failure is broad or just noisy;
- whether the remaining step answers a distinct scientific question;
- whether the compute budget allows it.

### 9.4 Negative result condition

Report a negative Path B result if:

```text
B0 harness is valid
cheap and moderate candidates have been run
no candidate improves over zero-shot beyond seed/fold noise
remaining candidates are expensive and unlikely to change the conclusion
```

A negative conclusion is acceptable and should not trigger uncontrolled increases in model complexity.

### 9.5 Positive result condition

Proceed to final holdout if a candidate:

```text
improves the frozen evaluation package versus AutoGluon zero-shot
is not explained only by seed/fold noise
passes the main overfitting checks or has clearly documented caveats
has acceptable runtime
```

---

## 10. Final deliverable

Path B ends with one of three conclusions.

### Positive conclusion

```text
Fine-tuning Chronos-2 with AutoGluon improved the frozen Part A evaluation package on the locked walk-forward/holdout design. The selected configuration is <...>, and the improvement is repeatable across folds/seeds with acceptable calibration and runtime.
```

### Negative conclusion

```text
AutoGluon fine-tuning did not produce repeatable out-of-sample improvement over AutoGluon zero-shot Chronos-2 under the frozen Part A setup. The zero-shot model remains the preferred Chronos-2 configuration for this project.
```

### Inconclusive conclusion

```text
AutoGluon fine-tuning produced mixed or unstable results. Some candidates improved selected slices, but the improvement was not stable enough across seeds/folds/tickers/regimes, or the runtime cost was not justified. The result is inconclusive rather than positive.
```

A negative or inconclusive conclusion is acceptable and should not trigger uncontrolled increases in model complexity.

---
