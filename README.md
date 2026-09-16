# MOEX × Chronos-2

Testing the predictive capability of Chronos-2 on MOEX (Moscow Exchange) financial time series,
leveraging its ability to forecast multiple correlated series simultaneously.

## Structure

- **[path_a/](path_a/)** — Path A: zero-shot Chronos-2 forecasting. The primary, actively-run
  pipeline — stage-driven, config-based, walk-forward evaluated. Universal runner
  (`runner.ipynb`) sources a reusable cell library (`basic_cells.ipynb`) and reads one
  `configs/stage_X.yaml` per run.
- **[path_b/](path_b/)** — Path B: AutoGluon fine-tuning of Chronos-2 on the same MOEX panel,
  building on Path A's validated data pipeline and evaluation package. See
  [path_b/README.md](path_b/README.md) for status (daily works; intraday index alignment open).
- **[algo_data/](algo_data/)** — Data-extraction pipeline for the MOEX AlgoPack API (candles +
  order-flow/open-interest covariates + a reproducible equity-universe selector). A
  self-contained sibling project with its own docs/tests; feeds `path_a/` via the
  `load_from_algopack` adapter. See [algo_data/docs/usage.md](algo_data/docs/usage.md).
- **[docs/](docs/)** — Design decisions (`wiki.md`), master experiment plan (`exp_plan.md`),
  session snapshot (`current_state.md`), file registry (`index.md`), project brief
  (`project_brief.md`), and historical probe records (`probes/`).
- **[runs/](runs/)** — Per-stage run outputs (configs, metrics, predictions, plots). Bulk
  artifacts are gitignored; only summary-level output is committed.

## Where to start

Read [docs/current_state.md](docs/current_state.md) for the latest session snapshot, then
[docs/exp_plan.md](docs/exp_plan.md) for the master plan and stage definitions.
