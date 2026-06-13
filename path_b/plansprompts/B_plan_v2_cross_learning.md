# Path B — AutoGluon Chronos-2 Fine-Tuning Plan for MOEX

Companion plan to `exp_plan.md` and the Path A zero-shot pipeline.

> Test whether AutoGluon fine-tuning of Chronos-2 improves the already validated Path A setup on the same data representation, same walk-forward windows, and same frozen evaluation package.

This revision makes `cross_learning` explicit in every B1–B4 cell/run so that the main setting and the optional diagnostic setting can be toggled without changing code.

---

## 1. Fixed assumptions inherited from Part A

Before Path B starts, Part A must provide a frozen configuration:

```yaml
path_a_locked:
  interval: <60m | 10m>
  prediction_length: 3
  context_length: <selected_context>
  primary_horizons: [1, 2, 3]
  cumulative_horizons: [3]
  universe_eval: <fixed evaluation universe, e.g. core12>
  covariate_set: <selected covariate set from Part A>
  data_format: <selected canonical feature schema from Part A>
  quantile_levels: [0.1, 0.5, 0.9]
  eval_metric_autogluon: <frozen Path A / Path B fit metric>
  decision_metrics: <frozen Path A evaluation package>
  holdout_start: <locked holdout date>
  holdout_end: <locked holdout date>
```

Path B must not change these during fine-tuning experiments. If a run changes covariates, data format, horizon, interval, evaluation universe, or metric definition, it is no longer a clean fine-tuning comparison and belongs back in Part A.

For this Path B revision:

```yaml
path_b_scope:
  intervals_to_fine_tune: [10m, 60m]
  prediction_length: 3
  eval_horizons: [1, 2, 3]
  primary_horizons: [1, 2, 3]
```

---

## 2. Core principle

B0 trains/runs the AutoGluon zero-shot reference once. Each later B-run trains/runs **one fine-tuned candidate configuration**. The comparison

```text
AutoGluon Chronos-2 zero-shot
vs
AutoGluon Chronos-2 fine-tuned candidate
```

happens only in the aggregation block, after both outputs have been written in the same schema. Fine-tuned B-runs should therefore not include a zero-shot model inside the same `hyperparameters` block.

---

## 3. Cross-learning control

For this project, `cross_learning=True` is the main Chronos-2 setup, not a late optional trick. The experiment is explicitly about whether Chronos-2 can use relationships among MOEX liquid assets, so the main candidate runs should keep cross-learning enabled.

However, every B1–B4 cell must expose `cross_learning` as an explicit boolean flag. This avoids hiding it inside defaults and lets the diagnostic `cross_learning=False` arm be turned on without rewriting the experiment logic.

Recommended config-level control:

```yaml
path_b:
  cross_learning_main: true
  cross_learning_diagnostics: false
  # effective values:
  #   false -> [true]
  #   true  -> [true, false]
```

Recommended helper:

```python
def get_cross_learning_values(CFG):
    main_value = bool(CFG.path_b.get("cross_learning_main", True))
    diagnostics = bool(CFG.path_b.get("cross_learning_diagnostics", False))
    if diagnostics:
        return [main_value, not main_value]
    return [main_value]
```

Recommended Chronos-2 defaults should **not** contain `cross_learning`. The flag is inserted explicitly in B1–B4 and in B0.

```python
CHRONOS2_DEFAULTS = {
    "batch_size": 64,
}
```

Run metadata and the comparison table must store both:

```text
cross_learning
batch_size
```

---

## 4. Experiment matrix

The matrix is ordered from cheapest and least overfit-prone to most complex. Do not skip directly to full fine-tuning or HPO.

The detailed comparison logic is centralised in Sections 5 and 6. Therefore each B-step only states what changes and what output it contributes to the final comparison.

---

### B0 — AutoGluon zero-shot reproduction

Purpose: verify that AutoGluon zero-shot produces results consistent with the frozen Path A zero-shot baseline.

What changes:

```text
No fine-tuning. This is a harness check.
```

Hyperparameters:

```python
B0_CROSS_LEARNING = bool(CFG.path_b.get("cross_learning_main", True))

B0_HYPERPARAMETERS = {
    "Chronos2": {
        "fine_tune": False,
        "context_length": CFG.context_length,
        "cross_learning": B0_CROSS_LEARNING,
        **CHRONOS2_DEFAULTS,
        "ag_args": {"name_suffix": f"ZeroShot_cross{B0_CROSS_LEARNING}"},
    }
}
```

Run:

```python
result_b0 = run_path_b_experiment(
    step_id="b0_autogluon_zeroshot",
    run_id=f"seed_main_cross_{B0_CROSS_LEARNING}",
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
This run trains only one LoRA fine-tuned Chronos-2 candidate per cross_learning flag.
The zero-shot reference is not included here; it is B0.
```

Start with LoRA because it is cheaper and less overfit-prone than full fine-tuning.

Hyperparameters:

```python
def make_b1_hyperparameters(*, cross_learning: bool):
    return {
        "Chronos2": {
            "fine_tune": True,
            "fine_tune_mode": "lora",
            "fine_tune_lr": 1e-5,
            "fine_tune_steps": 300,
            "fine_tune_batch_size": 8,
            "context_length": CFG.context_length,
            "fine_tune_context_length": min(CFG.context_length, 2048),
            "cross_learning": cross_learning,
            **CHRONOS2_DEFAULTS,
            "ag_args": {"name_suffix": f"LoRA_Min_cross{cross_learning}"},
        }
    }

B1_CROSS_LEARNING_VALUES = get_cross_learning_values(CFG)
```

Run:

```python
results_b1 = []
for cross_learning in B1_CROSS_LEARNING_VALUES:
    results_b1.append(
        run_path_b_experiment(
            step_id="b1_lora_min",
            run_id=f"seed_main_cross_{cross_learning}",
            CFG=CFG,
            RUN_DIR=RUN_DIR,
            train_data=train_data,
            eval_windows=eval_windows,
            known_covariates_by_window=known_covariates_by_window,
            hyperparameters=make_b1_hyperparameters(cross_learning=cross_learning),
            random_seed=CFG.seed,
            fit_kwargs_extra=FIT_DEFAULT,
        )
    )
```

Selection role:

```text
B1 is the reference fine-tuned candidate family. It is not automatically promoted or rejected here; it is compared with all other B-runs in the final aggregation block.
```

---

### B2 — Minimal LoRA repeatability check

Purpose: estimate training variance for the cheapest fine-tuned candidate.

What changes relative to B1:

```text
No LoRA hyperparameter change. Repeat B1 with several seeds and with the explicit cross_learning flag.
```

Hyperparameters:

```python
B2_SEEDS = [1, 2, 3]
B2_CROSS_LEARNING_VALUES = get_cross_learning_values(CFG)

def make_b2_hyperparameters(*, cross_learning: bool):
    return make_b1_hyperparameters(cross_learning=cross_learning)
```

Run:

```python
results_b2 = []
for cross_learning in B2_CROSS_LEARNING_VALUES:
    for seed in B2_SEEDS:
        results_b2.append(
            run_path_b_experiment(
                step_id="b2_lora_repeatability",
                run_id=f"seed_{seed}_cross_{cross_learning}",
                CFG=CFG,
                RUN_DIR=RUN_DIR,
                train_data=train_data,
                eval_windows=eval_windows,
                known_covariates_by_window=known_covariates_by_window,
                hyperparameters=make_b2_hyperparameters(cross_learning=cross_learning),
                random_seed=seed,
                fit_kwargs_extra=FIT_DEFAULT,
            )
        )
```

Selection role:

```text
B2 estimates seed-to-seed noise. Later improvements should be interpreted relative to this noise floor, separately for cross_learning=True and any diagnostic cross_learning=False arm.
```

---

### B3 — LoRA schedule sweep

Purpose: create candidate LoRA schedules and show whether the minimal setup underfits or overfits.

What changes relative to B1/B2:

```text
Only LoRA schedule parameters change: steps, learning rate, fine-tune batch size, plus the explicit cross_learning flag.
```

Recommended staged grid:

```yaml
fine_tune_steps: [100, 300, 1000]
fine_tune_lr: [1e-5, 3e-5]
fine_tune_batch_size: [8, 16]
cross_learning: controlled by path_b.cross_learning_diagnostics
```

Do not search all combinations blindly at first. Use a staged sweep for compute control:

1. fix LR and batch size, sweep steps;
2. run LR variants around the best-looking step count;
3. run batch-size variants only if GPU memory, training instability, or runtime requires it;
4. run `cross_learning=False` only when `path_b.cross_learning_diagnostics: true`.

Hyperparameter template:

```python
def make_b3_hyperparameters(*, steps, lr, fine_tune_batch_size, cross_learning: bool):
    return {
        "Chronos2": {
            "fine_tune": True,
            "fine_tune_mode": "lora",
            "fine_tune_lr": lr,
            "fine_tune_steps": steps,
            "fine_tune_batch_size": fine_tune_batch_size,
            "context_length": CFG.context_length,
            "fine_tune_context_length": min(CFG.context_length, 2048),
            "cross_learning": cross_learning,
            **CHRONOS2_DEFAULTS,
            "ag_args": {
                "name_suffix": (
                    f"LoRA_steps{steps}_lr{lr}_ftbs{fine_tune_batch_size}"
                    f"_cross{cross_learning}"
                )
            },
        }
    }
```

Run:

```python
results_b3 = []
for params in B3_GRID_STAGED:
    for cross_learning in get_cross_learning_values(CFG):
        results_b3.append(
            run_path_b_experiment(
                step_id="b3_lora_schedule",
                run_id=(
                    f"steps_{params.steps}_lr_{params.lr}"
                    f"_ftbs_{params.fine_tune_batch_size}"
                    f"_cross_{cross_learning}"
                ),
                CFG=CFG,
                RUN_DIR=RUN_DIR,
                train_data=train_data,
                eval_windows=eval_windows,
                known_covariates_by_window=known_covariates_by_window,
                hyperparameters=make_b3_hyperparameters(
                    steps=params.steps,
                    lr=params.lr,
                    fine_tune_batch_size=params.fine_tune_batch_size,
                    cross_learning=cross_learning,
                ),
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
    runs=b3_table[b3_table["cross_learning"] == True],
    primary_key="delta_vs_b0",
    stability_keys=[
        "overfit_flag",
        "delta_h1_vs_b0",
        "delta_h2_vs_b0",
        "delta_h3_vs_b0",
        "fit_seconds",
    ],
    preference="simplest_with_good_score",
)

REFERENCE_LORA_CONFIG = load_hyperparameters(REFERENCE_LORA_RUN_ID)
REFERENCE_LORA_STEPS = REFERENCE_LORA_CONFIG["Chronos2"]["fine_tune_steps"]
REFERENCE_LORA_LR = REFERENCE_LORA_CONFIG["Chronos2"]["fine_tune_lr"]
REFERENCE_LORA_FINE_TUNE_BATCH_SIZE = REFERENCE_LORA_CONFIG["Chronos2"]["fine_tune_batch_size"]
REFERENCE_LORA_CROSS_LEARNING = REFERENCE_LORA_CONFIG["Chronos2"]["cross_learning"]
```

Selection role:

```text
B3 contributes all schedule candidates to the final comparison table. It also defines REFERENCE_LORA_CONFIG for B4. This is a local reference, not a final winner. All B3 runs remain visible in aggregate comparison.
```

---

### B4 — Cross-learning and batch-size stability

Purpose: test whether the cross-learning result is stable to batch composition and batch size.

What changes relative to the local reference LoRA configuration:

```text
Main variants keep cross_learning=True and change inference batch_size.
If diagnostics are enabled, mirror the same batch-size grid with cross_learning=False.
```

Why cross-learning is explicit here:

Fine-tuning batch size and inference batch size are separate knobs:

```text
fine_tune_batch_size = training minibatch size
batch_size           = inference/cross-learning batch size
```

Hyperparameter variants:

```python
def make_b4_hyperparameters(*, cross_learning: bool, batch_size: int):
    hp = copy.deepcopy(REFERENCE_LORA_CONFIG)

    # Reference LoRA hyperparameters should contain one fine-tuned candidate, not a zero-shot arm.
    hp["Chronos2"]["cross_learning"] = cross_learning
    hp["Chronos2"]["batch_size"] = batch_size
    hp["Chronos2"]["ag_args"] = {
        "name_suffix": f"LoRA_Ref_cross{cross_learning}_batch{batch_size}"
    }
    return hp

B4_GRID = [
    {"batch_size": 32,  "role": "main_stability"},
    {"batch_size": 64,  "role": "main_stability"},
    {"batch_size": 128, "role": "main_stability"},
]
```

Run:

```python
results_b4 = []
for cross_learning in get_cross_learning_values(CFG):
    for params in B4_GRID:
        results_b4.append(
            run_path_b_experiment(
                step_id="b4_cross_learning_stability",
                run_id=(
                    f"cross_{cross_learning}"
                    f"_batch_{params['batch_size']}"
                    f"_{params['role']}"
                ),
                CFG=CFG,
                RUN_DIR=RUN_DIR,
                train_data=train_data,
                eval_windows=eval_windows,
                known_covariates_by_window=known_covariates_by_window,
                hyperparameters=make_b4_hyperparameters(
                    cross_learning=cross_learning,
                    batch_size=params["batch_size"],
                ),
                random_seed=CFG.seed,
                fit_kwargs_extra=FIT_DEFAULT,
            )
        )
```

Selection role:

```text
B4 checks whether the local reference LoRA result is stable under cross-learning batch composition and inference batch size. It does not redefine horizons, covariates, data format, or evaluation package.
```

---

### One-page experiment matrix summary

| Step | Purpose | What changes | Main run object | Selection role |
|---|---|---|---|---|
| B0 | Harness check | AutoGluon zero-shot only, explicit `cross_learning` | `B0_HYPERPARAMETERS` | Must reproduce Path A before any FT result is trusted |
| B1 | Minimal fine-tune candidate | Add LoRA, 300 steps, low LR, explicit `cross_learning` | `make_b1_hyperparameters(...)` | Cheapest FT candidate family |
| B2 | Repeatability | Same config, multiple seeds, explicit `cross_learning` | `make_b2_hyperparameters(...)`, `B2_SEEDS` | Estimates seed noise floor |
| B3 | Schedule variants | Steps/LR/fine-tune batch size plus explicit `cross_learning` | `make_b3_hyperparameters(...)` | Candidate LoRA schedules + local `REFERENCE_LORA_CONFIG` |
| B4 | Cross-learning stability | `batch_size`, explicit `cross_learning=True/False` when diagnostics enabled | `make_b4_hyperparameters(...)` | Checks stability of default cross-learning |

---

## 5. Logging, timing, and result comparison

This block is independent of the tuning type. It consumes Path B outputs from B0–B4 and decides whether anything was gained.

### 5.1 Required artifacts per run

Recommendations:

- Each candidate run should have its own immutable directory.
- Do not overwrite previous runs, even if the result is worse.
- Keep raw predictions, not only metrics. Metric definitions may need to be re-run without re-fitting.
- Store enough metadata to reload the AutoGluon predictor and reproduce the run.
- Store the exact `hyperparameters` dictionary used for the run.
- Store both model predictions and the B0 predictions in the same schema.

### 5.2 Runtime measurement recommendations

Every run should record:

- `step_id`, `run_id`, seed, and training-universe ID;
- GPU name and relevant package versions;
- number of training items and rows;
- number of evaluation items and windows;
- prediction length and context length;
- fine-tuning mode, LR, steps, fine-tune batch size;
- `cross_learning` flag and inference `batch_size`;
- validation-window settings;
- fit time, prediction time, and total time.

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
score_h1
score_h1_b0
delta_h1_vs_b0
score_h2
score_h2_b0
delta_h2_vs_b0
score_h3
score_h3_b0
delta_h3_vs_b0
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

The plots should consist of plots from Part A together with comparison plots.

The comparison plots should help answer four questions:

```text
Did fine-tuning improve the frozen evaluation package?
Is the improvement broad or concentrated?
Is the improvement stable across seeds/folds?
How much runtime did the improvement cost?
```

Recommended plots for all runs:

- `delta_by_run.png`: each candidate run's score minus the B0 zero-shot reference score.
- `delta_by_horizon.png`: delta for h=1, h=2, h=3.
- `delta_by_ticker_heatmap.png`: ticker × horizon delta for selected candidate runs.
- `runtime_vs_delta.png`: fit time against metric lift.
- `coverage_candidate_vs_b0.png`: calibration comparison against the B0 zero-shot reference.
- `cross_learning_batch_stability.png`: B4 score deltas by `cross_learning` and `batch_size`.

---

## 6. Dataset sizes, candidate lengths, and transfer of choices

The guiding principle is:

```text
- Section 6 controls only context-length instances, dataset-size feasibility checks, quality thresholds, and transfer rules.
- The ticker universe is inherited from Path A. Do not tune ticker-pack size inside Path B.
- After the context probe, transfer one reference context per interval into B2–B4.
```

---

## 6.1 Context-length intervals for local inefficiencies

Path B should test a **small interval** of plausible context lengths per frequency, not a single value. The instances should be interpretable:

```text
CTX_SHORT  = intentionally short local-memory diagnostic
CTX_MAIN   = recommended default for the interval
CTX_LONG   = long-memory diagnostic inside the local-efficiency design
```

### 6.1.1 Context instances to run

| Interval | Plausible local context interval | `CTX_SHORT` | `CTX_MAIN` recommended | `CTX_LONG` | Argumentation |
|---|---:|---:|---:|---:|---|
| `60m` | `64–512` | `128` | `256` | `384` | This is the clean several-hours regime. `128` keeps memory strongly recent, `256` gives enough repeated intraday patterns, and `384` tests broader intraday state. |
| `10m` | `256–1152` | `384` | `768` | `1152` | This is the main local/microstructure regime. `384` is a short local diagnostic, `768` is the recommended balance, and `1152` tests whether a few extra weeks of intraday behavior help. Very long contexts can add stale microstructure noise. |

### 6.1.4 Recommended default

Use `CTX_MAIN` unless the context probe shows a clear reason to use `CTX_SHORT` or `CTX_LONG`.

```yaml
CTX_MAIN:
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
H = prediction_length = 3
V = num_val_windows = 3
```

### 6.2.1 Hard and useful length ratios

Mechanical feasibility:

```text
min_length_hard = C + H * V = C + 9
```

This only prevents obvious technical failure. It does not mean the item is useful for fine-tuning.

Useful ratio checks:

| Ratio | Formula | Interpretation | Recommended band |
|---|---|---|---|
| Hard item ratio | `min(L_i) / C` | Does every fixed target item have enough history for the chosen context? | Must be `> 1`; practically `>= 1 + 9/C` |
| Useful item ratio | `min(L_i) / C` | Is the weakest item still useful, not only technically valid? | Prefer `>= 2` |
| Median item ratio | `median(L_i) / C` | Does a typical item provide several different contexts? | Prefer `>= 5` |
| Panel reservoir ratio | `sum_i max(0, L_i - C - H + 1) / (N * C)` | How many possible training windows exist relative to context width? | `20–50` acceptable, `>50` strong, `<20` risky |

The panel reservoir ratio is a planning heuristic, not a statistical guarantee. It detects when the context is so long that the fixed dataset produces too few distinct training contexts.

### 6.2.2 Plausible ratio implications under local contexts

Exact ratios must be computed after cache inspection. Before that, the expected qualitative picture is:

| Interval | Context instance | Ratio expectation | Practical implication |
|---|---|---|
| `60m` | `128 / 256 / 384` | Usually strong | Best representation of several-hour inefficiencies. |
| `10m` | `384 / 768 / 1152` | Usually strong because intraday data has many bars | Best representation of micro/local inefficiencies; long context must still pass overfitting checks. |

### 6.2.3 Dataset-size status table

| Field | Value / source | Purpose |
|---|---|---|
| Target universe | inherited from Part A | No ticker-pack choice in Section 6. |
| `N` target items | measured from Part A locked universe | Used in panel reservoir ratio. |
| Intervals | `60m`, `10m` | Only these intervals are fine-tuned in Path B. |
| Context instances | `CTX_SHORT`, `CTX_MAIN`, `CTX_LONG` | Small context probe. |
| `L_min`, `L_median` per interval | measured after cache build | Used for hard/useful/median ratios. |
| Panel reservoir ratio per context | computed after cache build | Decides whether a context is feasible or risky. |
| Final `REFERENCE_CONTEXT_BY_INTERVAL` | selected after the context probe | Passed to B2–B4. |

---

## 6.3 Validation settings

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

---

## 6.4 Final recommended defaults

If Part A does not force a different choice, start Path B with:

```yaml
path_b_section_6_defaults:
  intervals_to_test: [60m, 10m]
  target_universe: inherited_from_path_a
  choose_new_tickers_in_path_b: false

  prediction_length: 3
  eval_horizons: [1, 2, 3]
  primary_horizons: [1, 2, 3]
  num_val_windows: 3
  val_step_size: CFG.walk_forward_shift
  refit_every_n_windows: 1

  cross_learning_main: true
  cross_learning_diagnostics: false

  context_instances:
    CTX_SHORT:
      60m: 128
      10m: 384
    CTX_MAIN:
      60m: 256
      10m: 768
    CTX_LONG:
      60m: 384
      10m: 1152

  reference_context_default: CTX_MAIN

  dataset_size_checks:
    hard_min_length: context_length + 9
    useful_min_length: 2 * context_length
    median_length_target: 5 * context_length
    panel_reservoir_ratio_acceptable: 20
    panel_reservoir_ratio_strong: 50

  proxies:
    use_as_targets: false
    use_as_covariates_if_part_a_selected: true
```
