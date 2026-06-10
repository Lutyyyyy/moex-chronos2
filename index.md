# Index

Verbose descriptions for each repo file. The compact one-liner + update rule lives in `.claude/CLAUDE.md`; this file holds the longer context for when deeper detail is needed.

---

- **[wiki.md](wiki.md)** — Design decisions and open questions for the MVP: ticker universe, history depth per interval, covariate set, log-return target definition, forecast horizons, walk-forward evaluation scheme, metrics (forecast + trading), and MOEX ISS API data source notes.
  *Update rule:* revise when an MVP-level design decision changes; otherwise stable.

- **[devdocs.md](devdocs.md)** — High-level experiment plan: deploy Chronos-2 on Colab T4, parse MOEX candles at 10m/60m/1d, build covariates, split data, fine-tune on grouped multivariate series, evaluate with sliding-window walk-forward.
  *Update rule:* stable; superseded operationally by `exp_plan.md`.

- **[current_state.md](current_state.md)** — Experiment scratchpad: file inventory, wiki decision summary, Chronos-2 key facts, known gaps, and suggested next steps.
  *Update rule:* refresh "Files in repo", "Known gaps", and "Suggested next session" at the end of every session.

- **[exp_plan.md](exp_plan.md)** — Master Path A plan. Statistical framing, universe + cache layout, Path A and Path B pipeline descriptions, stages 0–7 (config / inputs / goals / data sources / success criteria), per-stage results format.
  *Update rule:* update §3 (stage X) when a stage's config changes; update §0/§4 only on framework-level changes (metrics added, baselines changed, etc.).

- **[basic_cells.ipynb](basic_cells.ipynb)** — Reusable cell library. Sections: imports/GPU, YAML config loader, Drive mount, ISS soft prefetcher (rate-limited + retry + idempotent), **FORTS chain resolver (§4b: enumerate `{root}{letter}{year_digit}` contracts, fetch each, pick front-month per bar by volume, expose stitched close + `contract_id` for boundary-NaN downstream; FORTS served natively at 10m/60m/1d, fetched at target interval)**, cache-only loaders, panel + covariate + calendar feature build, Chronos input builder, walk-forward driver, metrics (DA + binomial + Wilson CI + BH correction, Pearson/Spearman, amplitude, quantile coverage), baselines (zero/last/momentum5/AR(1)), plot helpers, top-level `run_stage(cfg_path)` orchestrator.
  *Update rule:* fix bugs here, not in `runner.ipynb` — propagate from runner back to here when something hardens.

- **[runner.ipynb](runner.ipynb)** — Universal stage runner. Mounts Drive, sources `basic_cells.ipynb`, reads one `configs/stage_X.yaml`, runs `run_stage(...)`, displays outputs inline.
  *Update rule:* edit only the `CONFIG_PATH` cell to switch stages; structural changes go in `basic_cells.ipynb`.

- **[configs/](configs/)** — Per-stage YAML config files (extension `.yaml`). One file per stage / sub-variant of Path A: `stage_0_smoke.yaml`, `stage_1_daily.yaml`, `stage_2_60m.yaml`, `stage_3_10m.yaml`, `stage_4_sector.yaml`, `stage_5_covariates.yaml`, `stage_6_stability.yaml`, `stage_7_holdout.yaml`.
  *Update rule:* duplicate + edit the relevant file when running a sub-variant (different `context_len`, sector, date window) and bump `stage_id` so outputs do not overwrite each other.

- **[scratchpads/](scratchpads/)** — Per-stage running notes. `_TEMPLATE.md` is the canonical template; `stage_X_scratch_pad.md` is one per stage.
  *Update rule:* fill before/during/after every stage run — config deviations, run log, top-line numbers, plot checks, observations, next-step decision.

- **[moex_chronos2_pipeline.ipynb](moex_chronos2_pipeline.ipynb)** — Original prototype notebook. Useful as reference / Path B fine-tune skeleton.
  *Update rule:* legacy — fold any still-relevant bits into `basic_cells.ipynb`; do not develop new logic here.
