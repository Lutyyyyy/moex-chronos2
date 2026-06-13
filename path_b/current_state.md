# Path B — current state

Snapshot for the next session. Path B (AutoGluon Chronos-2 fine-tuning) has been
**implemented as a self-contained module under `path_b/`** following
`path_b_implementation_prompt.md` and `B_plan_v2_cross_learning.md`. Code is written and
**verified end-to-end against a mock AutoGluon** (control flow, schema, metrics, plots, CSV).
It has **not** yet been run on a real GPU / real ISS data — that is the next step.

> NB: The implementation prompt asks to maintain `current_state.md` **at project root**.
> The user's final instruction was *"Implement within path_b folder only. Let the rest be
> unchanged."* This file therefore lives at `path_b/current_state.md`, not project root.
> (Project-root `current_state.md` is Path A's and is left untouched.)

---

## Current task
Path B implemented as a self-contained Part-A-style notebook pipeline inside `path_b/`.
Next: run `runner_B.ipynb` on a Colab GPU against a real panel (start with
`configs/path_b_60m.yaml`), confirm B0 reproduces Path A zero-shot within tolerance, then
read the comparison table.

## Layout (self-contained `path_b/`, mirrors Part A's notebook idiom)
The folder now carries **both** Part A and Part B side by side, so Path B runs without
reaching outside `path_b/`:

| File | Role |
|------|------|
| `basic_cells_A.ipynb` | Copy of Part A's `basic_cells.ipynb` (data loaders, ISS prefetch, FORTS resolver, cache, panel build). Sourced read-only via `%run`. |
| `runner_A.ipynb` | Copy of Part A's runner (reference / Path A runs). |
| `basic_cells_B.ipynb` | **Single source of truth for Path B** (notebook form, Part A idiom: title → `## 0. Imports` → `## 1..7` one code cell per section). §0 ported Path A logic (config, panels, anchors, Chronos input builder, metrics, baselines, plots); §A config helpers; §B AutoGluon data adapters; §C run-dir + append-only CSV; §D B0–B4 hyperparameter builders; §E `run_path_b_experiment` + `run_path_b`; §F comparison utils + plots. |
| `runner_B.ipynb` | Universal Path B runner (mirrors `runner_A.ipynb`): locate `path_b/` → `%run basic_cells_A.ipynb` → `%run basic_cells_B.ipynb` → load config → build panels → `run_path_b` → inspect tables/plots inline. Functions are called from globals (no `import`), exactly like Part A. |
| `configs/path_b_10m.yaml` | Path B 10m config (inherits Path A `stage_3_10m`; ctx 768 = CTX_MAIN; H=3; horizons [1,2,3]). |
| `configs/path_b_60m.yaml` | Path B 60m config (inherits Path A `stage_2_60m`; ctx 256 = CTX_MAIN; H=3; horizons [1,2,3]). |
| `current_state.md` | This file. |

`runs/path_b/...` and `scratchpads/path_b/...` are created at runtime by the runner.

> **History:** Path B was first written as `path_b_cells.py` + `runner_path_b.ipynb`. Per a
> later request it was converted to the Part A notebook idiom (`basic_cells_B.ipynb` +
> `runner_B.ipynb`); the `.py` was deleted. The notebook is the single source of truth now.
> The conversion preserved every function body byte-for-byte (split only at section banners)
> and was re-verified end-to-end (see below).

## Key decisions (deviations from the impl prompt, resolved per user constraints)
1. **Project-root `basic_cells.ipynb` is UNTOUCHED.** The prompt's step A says "extend
   basic_cells.ipynb"; the user said "path_b folder only, rest unchanged." We honor the user:
   Path A's *experiment* logic is **ported verbatim** into `basic_cells_B.ipynb` §1 (it is
   horizon-agnostic, reused as-is). Path A's *data-loading* side (ISS prefetch, FORTS resolver,
   cache loaders) is **not** re-implemented — the runner sources the Part A copy
   `path_b/basic_cells_A.ipynb` at runtime via `%run` (it needs Colab + Drive). Both `_A` and
   `_B` notebooks live in `path_b/`, so Path B is fully self-contained and the project-root
   Part A files are never modified.
2. **Outputs/configs/scratchpads/current_state all live under `path_b/`** (prompt put some at
   project root). `path_b.output_root` defaults to `runs/path_b` (resolved relative to the project
   root the runner `chdir`s into, so artifacts still land in the project-level `runs/path_b/`,
   matching the prompt's path scheme while keeping *source* files inside `path_b/`).
3. **`model_path` pinned to `amazon/chronos-2`** (Path A's HF weights) for a clean B0↔Path A
   comparison. AutoGluon's own default is `autogluon/chronos-2` (described as the same 120M
   model, AG mirror — but **not verified byte-identical**; "mirror" may repackage config/keys).
   *Decision + fallback:* keep **Path A unchanged** on `amazon/chronos-2` (it is the canonical
   upstream release and already has real results in `runs/`), and pin **Path B to the same**
   `amazon/chronos-2`. The single source of truth that matters is "A and B share one weight repo,"
   and B0 (re-run zero-shot inside Path B) is the real comparison anchor — Path B deltas are
   measured against B0, not against Path A's `[2,3,5]` `runs/`, so B0↔Path A agreement is a
   sanity check, not load-bearing. **Fallback (use only if forced):** if AutoGluon cannot load
   the `amazon/chronos-2` repo cleanly (it sometimes expects its own repo layout) **or** the two
   repos turn out to be different checkpoints, set **both** A and B to `autogluon/chronos-2` —
   i.e. align on the AG version rather than switch only one side. Do **not** switch Path A alone
   to the AG version (that would muddy its existing runs to fix an advisory check). Confirm the
   `amazon/chronos-2` load on the first real GPU run (see TODO verify-API below).
4. **Covariate split (prompt step B "safe existing split"):** calendar features
   (`hour, dow, dom, month [, session_open]`) → **known-future** (`known_covariates_names`);
   index/futures returns + dlog-volume → **past-only** (plain columns in train data). Matches
   Path A's leakage rule.
5. **`cross_learning` is an INFERENCE knob, not a fine-tuning effect.** In AutoGluon's `Chronos2`
   it controls joint prediction across series in a batch (and makes results sensitive to
   `batch_size`); it does *not* change what LoRA learns. It is kept explicit in every B0–B4
   hyperparameters dict and in run metadata (prompt steps 5–6, B_plan_v2 §3), but read deltas
   between cross_learning arms as a batching effect, not a training effect.
6. **Horizons `[1,2,3]`, `prediction_length=3`** for all of Path B (Path A uses `[2,3,5]`/H=5).
   Every comparison is against **B0** (a re-run zero-shot at the *same* horizons), never against
   the existing Path A `runs/`. Stated in the runner + configs.

## Assumptions inherited from Path A
- Universe: core 12 (SBER, GAZP, LKOH, ROSN, NVTK, TATN, GMKN, PLZL, MAGN, NLMK, MOEX, VTBR).
- Canonical long-form input: `item_id, timestamp, target` + covariate columns.
- Walk-forward: same anchor scheme (`walk_forward_anchors`), `shift` from Path A config.
- Quantiles `[0.1, 0.5, 0.9]`.
- Metric package: Path A `per_cell_metrics` / `aggregate_metrics`, reused verbatim, evaluated
  on horizons `[1,2,3]`.

## Verified (against a mock AutoGluon + synthetic panel; no GPU)
- `basic_cells_B.ipynb` execs cell-by-cell into one namespace (simulating `%run`); 61 callable
  defs land, all key symbols present ✓. Conversion from the old `.py` preserved every function
  body byte-for-byte (split only at section banners).
- Both configs `yaml.safe_load` + `normalize_path_b_config` ✓; `get_cross_learning_values`
  returns `[True]` (diagnostics off) / `[True, False]` (on) ✓.
- B0–B4 hyperparameter builders produce the documented keys; `cross_learning` NOT in shared
  defaults; B4 deep-copies the reference (no mutation leak) ✓.
- B3 staged grid = 5 configs (step sweep + 1 LR variant + 1 ft-batch variant), not a blind
  full cross-product ✓.
- `choose_reference_candidate` selects the simplest schedule within tolerance of the best
  `delta_vs_b0` from the **written** B3 table ✓.
- **Full `run_path_b` flow, all 5 steps** (B0→B1→B2→B3→reference→B4) executed from the
  notebook-derived namespace: 13 runs written, deltas-vs-B0 computed for all 12 FT runs, B2's
  3 seeds present, immutable run dirs + append-only `path_b_runs.csv` with the canonical header,
  5 per-candidate Path A plots + 5 comparison plots rendered ✓.
- `basic_cells_B.ipynb` (18 cells) and `runner_B.ipynb` (16 cells) are valid nbformat-4 JSON;
  all code cells parse; no lingering `import path_b_cells` / `PB.` / project-root
  `basic_cells.ipynb` references in the runner ✓.

## TODO / ASK (unresolved — need a real run or a human call)
- **TODO (run):** Execute `runner_B.ipynb` on a Colab GPU with `configs/path_b_60m.yaml`.
  Confirm `from autogluon.timeseries.models.chronos.chronos2 import Chronos2Model` succeeds
  (needs autogluon.timeseries **>= 1.5.0**); if it fails, upgrade AutoGluon before anything else.
- **TODO (verify-API):** On first real run, confirm AutoGluon's forecast columns are named
  exactly `"0.1"/"0.5"/"0.9"` (the quantile-level float reprs). `_ag_forecast_to_pathA_schema`
  tolerates a missing median by falling back to a `"mean"` column, but the quantile naming should
  be eyeballed once and the fallback removed if unneeded.
- **TODO (weights / model_path):** On first real run, confirm AutoGluon loads
  `amazon/chronos-2` (the pinned `path_b.model_path`) without error. If it errors or warns about
  repo layout, apply the **fallback from decision #3**: set both Path A and Path B to
  `autogluon/chronos-2` (do not switch Path A alone). Also worth a one-time check that B0's
  zero-shot DA lands near Path A's at the same horizons — advisory, not a gate.
- **ASK (Path A prerequisite):** `B_plan_v2 §1` requires a *frozen* `path_a_locked` config
  (chosen interval/context/covariates/holdout) handed over from Path A. **Path A has only run
  daily (Stages 0–1); 60m/10m (Stages 2–3) are unrun**, so no real intraday baseline exists yet.
  The Path B configs use B_plan_v2 §6.4 default contexts (60m=256, 10m=768) as a stand-in.
  **Decide:** run Path A Stages 2–3 first to freeze the handoff, or proceed with the defaults and
  treat B0 as the self-contained anchor. (Recommendation: run Stage 2/3 first — see the project
  assessment in `~/.claude/plans/`.)
- **TODO (scratchpad):** create `scratchpads/path_b/path_b_60m_scratch_pad.md` from the Path A
  `_TEMPLATE.md` after the first real run, with actual B0–B4 numbers.

## Last completed step
Implemented + mock-verified Path B (module, runner, configs, this note).

## Next command to run
Open `path_b/runner_B.ipynb` on a Colab T4 → run §0–§3 with `configs/path_b_60m.yaml`.
