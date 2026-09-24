# MOEX × Chronos-2

Does [Chronos-2](https://arxiv.org/abs/2510.15821) — a pretrained time-series foundation
model, used zero-shot — show any directional edge on MOEX (Moscow Exchange) equity returns?

**Result: no.** Across ~10 independent axes (resolution, grouping, price adjustment,
context length, sector composition, lead-lag structure), every pre-registered gate failed —
a clean, replicated null. The full methodology and results are in
**[FINDINGS.md](FINDINGS.md)**. The point of this repo isn't the null result by itself; it's
the process that produced it: pre-registered success criteria, Benjamini-Hochberg correction
on every multi-cell test, discovery/confirmation splits with verified non-overlapping dates,
and a real methodology bug (a spurious market-factor artifact) caught and fixed mid-project
before it could contaminate a result.

## Structure

- **[forecasting/](forecasting/)** — the zero-shot Chronos-2 evaluation pipeline. Config-driven,
  walk-forward evaluated: a universal runner (`run.ipynb`) sources a reusable cell library
  (`lib.ipynb`) and reads one `configs/<name>.yaml` per run. 70 configs across three
  experiment families (basket gate, lead-lag confirmation, sector baskets) — see
  [FINDINGS.md](FINDINGS.md) for what each one tests.
- **[data_pipeline/](data_pipeline/)** — the data-extraction pipeline for the MOEX AlgoPack
  API (candles, order-flow/open-interest covariates, a reproducible liquidity-ranked
  equity-universe selector, and a dividend/split price-adjustment step). A self-contained
  sibling project with its own tests (50/50 passing offline, no network needed) and docs —
  see [data_pipeline/docs/usage.md](data_pipeline/docs/usage.md). Feeds `forecasting/` via
  the `load_from_algopack` adapter.
- **[docs/transient_dependency_research.md](docs/transient_dependency_research.md)** — the
  design document for the lead-lag/dependency-detection line of work: candidate mechanisms,
  statistical safeguards, and what the completed experiments do and don't rule out.
- AutoGluon fine-tuning (not published here) — an early, partially-working attempt at
  fine-tuning Chronos-2 on the same panel. Paused deliberately rather than pushed through;
  see FINDINGS.md's "Fine-tuning" section for why.

## Where to start

Read **[FINDINGS.md](FINDINGS.md)** — it has the full methodology, every experiment
family's results table, and the limitations. `docs/transient_dependency_research.md` has the
deeper design rationale for the lead-lag work specifically.

## Reproducing a result

1. Get MOEX AlgoPack API access and run `data_pipeline/` to produce the processed Parquet
   files (see [data_pipeline/docs/usage.md](data_pipeline/docs/usage.md)).
2. In `forecasting/`, open `run.ipynb`, point `CONFIG_PATH` at any file under `configs/`,
   and run — each config is self-contained (tickers, dates, resolution, context length are
   all in the YAML).
