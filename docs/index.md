# Index

Verbose descriptions for each repo file. See the root [README.md](../README.md) for the
top-level orientation (Path A vs Path B).

---

- **[wiki.md](wiki.md)** — Design decisions and open questions for the MVP: ticker universe, history depth per interval, covariate set, log-return target definition, forecast horizons, walk-forward evaluation scheme, metrics (forecast + trading), and MOEX ISS API data source notes.
  *Update rule:* revise when an MVP-level design decision changes; otherwise stable.

- **[devdocs.md](devdocs.md)** — High-level experiment plan: deploy Chronos-2 on Colab T4, parse MOEX candles at 10m/60m/1d, build covariates, split data, fine-tune on grouped multivariate series, evaluate with sliding-window walk-forward.
  *Update rule:* stable; superseded operationally by `exp_plan.md`.

- **[current_state.md](current_state.md)** — Experiment scratchpad: file inventory, wiki decision summary, Chronos-2 key facts, known gaps, and suggested next steps.
  *Update rule:* refresh "Files in repo", "Known gaps", and "Suggested next session" at the end of every session.

- **[exp_plan.md](exp_plan.md)** — Master Path A plan. Statistical framing, universe + cache layout, Path A and Path B pipeline descriptions, stages 0–7 (config / inputs / goals / data sources / success criteria), per-stage results format.
  *Update rule:* update §3 (stage X) when a stage's config changes; update §0/§4 only on framework-level changes (metrics added, baselines changed, etc.).

- **[project_brief.md](project_brief.md)** — Project brief / architecture proposal written for a math-strong, trading/ML-new audience: why Chronos-2, the validation experiment, and a proposed LLM agent layer (risk management, trade execution) built on top once Path A validates.
  *Update rule:* revise when the target architecture or validation criteria change.

- **[probes/forts_iss_probes.md](probes/forts_iss_probes.md)** — Historical record: raw ISS API probe output that resolved the FORTS futures chain resolver's open assumptions (contract enumeration, interval availability, roll-boundary jumps, front-month selection via OI). Reference only — findings already folded into `current_state.md` and `exp_plan.md`.
  *Update rule:* frozen; do not edit, append a new probes file instead if further ISS investigation is needed.

- **[runs_empty_futures.md](runs_empty_futures.md)** — Historical record: raw log of the first bulk prefetch returning all shares/indexes empty at interval=15, the finding that led to dropping 15m in favor of 10m.
  *Update rule:* frozen historical record.

- **[../path_a/basic_cells.ipynb](../path_a/basic_cells.ipynb)** — Reusable cell library (30 cells). Sections: imports/GPU, YAML config loader, Drive mount, ISS soft prefetcher (rate-limited + retry + idempotent), **FORTS chain resolver (§4b: enumerate `{root}{letter}{year_digit}` contracts, fetch each, pick front-month per bar by volume, expose stitched close + `contract_id` for boundary-NaN downstream; FORTS served natively at 10m/60m/1d, fetched at target interval)**, cache-only loaders (**§5: `load_from_algopack` adapter — reshapes `algo_data/`'s long-format Parquet output into the same `{ticker: df}` shape the ISS cache path produces; `load_stage_inputs` branches on `cfg["data_source"] == "algopack"` vs the default ISS-cache path, both feed the same downstream code unchanged**), panel + covariate + calendar feature build (**`build_price_panel` now takes `min_ticker_coverage` (default 0.98) — drops any ticker whose raw, pre-ffill bar coverage of the union calendar is below threshold, logging what was dropped and why, plus an inner-join shrinkage diagnostic; guards against one illiquid ticker at 50-100 ticker scale silently shrinking every other ticker's usable date range; `assemble_panels` (cell 15) only passes the SURVIVING tickers (`price.columns`, post-coverage-guard) into `build_covariate_panel` — previously passed the full configured ticker list, so one dropped ticker's ragged raw volume series still collapsed the covariate panel's `dropna(how="any")` and silently produced "0 windows" with no error; caught via a real Colab Phase B run 2026-09-17, reproduced and fixed**), Chronos input builder, **walk-forward driver (calls `predict_df` with `validate_inputs=False` because the MOEX session grid is not a single regular freq — Chronos otherwise rejects every horizon crossing a day/weekend boundary; future covariates align positionally and outputs are relabelled to the real `fut_idx`; **`group_mode` (`cfg["group_mode"]`, default `"univariate"`) threads to `predict_df`'s `cross_learning` kwarg — the actual multivariate/univariate switch, verified against `chronos-forecasting`'s source; batching tickers into one `id_column`-keyed call is not by itself joint attention**)**, metrics (DA + binomial + Wilson CI + BH correction, Pearson/Spearman, amplitude, quantile coverage; plus `trend2_metrics`: 2-bar trend agreement — when predicted bar1/bar2 share a sign, how often the realised bars match, strict `both` vs cumulative `cum`), baselines (zero/last/momentum5/AR(1)), plot helpers, top-level `run_stage(cfg_path)` orchestrator (**reconciles `cfg["tickers"]` to `ret_panel.columns` right after `assemble_panels` — `min_ticker_coverage` may have dropped some, and every downstream consumer (walk-forward, baselines, metrics, plots) needs the same survivor list `ret_panel` actually has, not the originally-configured one; previously `run_walk_forward` indexed `ret_panel[tic]` for a dropped ticker and crashed with `KeyError`, caught locally 2026-09-17**).
  *Update rule:* fix bugs here, not in `runner.ipynb` — propagate from runner back to here when something hardens.

- **[../algo_data/](../algo_data/)** — Data-extraction pipeline (MOEX AlgoPack API), a colleague-built sibling project with its own `.claude/CLAUDE.md`/`index.md`/tests. Produces long-format Parquet (`ticker, timestamp, ...`) that `path_a/basic_cells.ipynb`'s `load_from_algopack` adapter ingests. Includes `rank_equity_universe()`/`save_equity_universe()` — a reproducible, audited equity universe selector (TQBR board → filter ETFs/short-history tickers → rank by turnover → top-N), output at `algo_data/data/universe/equity_universe.yaml`. See `algo_data/docs/usage.md` for full usage; `algo_data/current_state.md` for status.
  *Update rule:* maintained per `algo_data/.claude/CLAUDE.md`'s own rules (edit `algo_data/src/algopack_pipeline.py`, rebuild notebook, run tests); this repo's docs only need a one-line pointer, not a duplicate description.

- **[../path_a/runner.ipynb](../path_a/runner.ipynb)** — Universal stage runner. Mounts Drive, sources `basic_cells.ipynb`, reads one `configs/stage_X.yaml`, runs `run_stage(...)`, displays outputs inline.
  *Update rule:* edit only the `CONFIG_PATH` cell to switch stages; structural changes go in `basic_cells.ipynb`.

- **[../path_a/configs/](../path_a/configs/)** — `phase_b_multivariate.yaml` / `phase_b_univariate.yaml` (written 2026-09-17, not yet run) — identical except `group_mode`; `data_source: algopack` pointing at the real AlgoPack pull (22 tickers configured, ~16 survive the coverage guard). The project pivoted 2026-09-17 from a linear numbered-stage sequence to gated phases (A: universe/data via `algo_data`, B: multivariate-vs-univariate gate, C: lead-lag screening, D: stretch backtest — see `exp_plan.md`). All `stage_0`–`stage_7` configs are archived at `../path_a/archive/concluded_stages/`.
  *Update rule:* new configs use `phase_<letter>_<name>.yaml` naming, bump `stage_id` per run so outputs do not overwrite each other. When a phase's run concludes with a written-up result, move its config + scratchpad to `archive/concluded_stages/` (the `runs/<stage_id>/` output stays live).

- **[../path_a/scratchpads/](../path_a/scratchpads/)** — `_TEMPLATE.md` (canonical template for future phase scratchpads) and `phase_b_scratch_pad.md` (combined paired-arm scratchpad for the Phase B gate — both configs' run logs, top-line numbers, and the McNemar test result/gate decision in one file, since the gate needs both arms read together, not the per-stage template). `stage_1_scratch_pad.md` archived alongside its config — see `../path_a/archive/README.md`.
  *Update rule:* fill before/during/after every run — config deviations, run log, top-line numbers, plot checks, observations, next-step decision.

- **[../path_a/archive/](../path_a/archive/)** — Concluded/superseded material, not read by any active code or config: `legacy_notebooks/` (`moex_chronos2_pipeline.ipynb`, `Chronos2_Roma.ipynb` — original prototypes), `concluded_stages/` (all `stage_0`–`stage_7` configs + scratchpads — results stay live at `runs/`). See `archive/README.md` for the full rationale per item, including which stages concluded normally vs. were superseded wholesale by the pivot.
  *Update rule:* add to it (never delete outright) when a run concludes or a notebook is fully superseded; update `archive/README.md`'s entry list alongside.

- **[../path_b/](../path_b/)** — Path B (AutoGluon Chronos-2 fine-tuning). Self-contained; see [path_b/README.md](../path_b/README.md) and [path_b/current_state.md](../path_b/current_state.md) for its own file map and status.
