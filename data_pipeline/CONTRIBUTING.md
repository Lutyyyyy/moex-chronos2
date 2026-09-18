# Contributing / project rules

## Goal

A reusable, extensible data-extraction pipeline for MOEX market data via the ALGOPACK
service. Output feeds the sibling project `../forecasting/` (Chronos-2 zero-shot forecasting
on MOEX time series).

## What it does

- Pulls historical market data (candles + ALGOPACK analytical datasets) for a configurable
  ticker universe, interval, and date range.
- Saves clean, consistently-formatted files ready for downstream modelling (long format:
  `ticker, timestamp, features...`).
- Designed to grow: new datasets/tickers/covariates are added as config + small modules, not
  by rewriting the pipeline.

## Rules

- Secrets only in `.env`; `.env` is git-ignored. Never print, log, or commit the API key.
- Parameters (tickers, intervals, dates, datasets, output paths) go in config files
  (`config.md`), not hard-coded.
- Raw downloads and processed outputs are kept separate (`data/raw/` vs `data/processed/`),
  both git-ignored.
- Pipeline code lives only in `src/algopack_pipeline.py`. After any change, run
  `python tools/build_notebook.py` and `pytest` (plus `pytest -m live` when API behavior is
  touched). **Never hand-edit `notebooks/algopack_pipeline.ipynb`** — it's generated.
- Before editing or creating any file, check [`index.md`](index.md) for the current file map.

## ALGOPACK API notes

Facts about the ALGOPACK service worth knowing before touching the client code:

- Product page / API key: https://data.moex.com/products/algopack. Docs:
  https://moexalgo.github.io/ (JS-rendered — fetch the
  [OpenAPI spec](https://raw.githubusercontent.com/moexalgo/moexalgo.github.io/main/static/openapi/openapi.yaml)
  directly for the most precise reference).
- Auth: `Authorization: Bearer <key>` against `https://apim.moex.com/iss/...json`. The apim
  TLS cert is issued by Russian Trusted Sub CA — requests need certifi plus the bundled
  Russian Trusted Root/Sub CA (`certs/russian_trusted_ca.pem`, expires 2027-03-06).
- ISS candles: no 15-minute interval exists on any market; 500 rows/page; MSK naive
  timestamps.
- Datashop endpoints (Super Candles, HI2, Alerts, FUTOI) page 1000 rows via `data.cursor`.
  `fo` datashop endpoints need the contract SECID (e.g. `SiU5`), not the asset. FUTOI ignores
  `start`/`limit` and returns only the latest 1000 rows — fetch per day if you need history.
- Free-tier key: `datashop/algopack/*` returns HTTP 200 with an HTML "subscribers only" body
  (detect by content-type, not status code) rather than an error status.
- The official `moexalgo` Python client exists but its auth/API details drift between
  versions — verify against current docs rather than assuming.

## File map

Full per-file descriptions and update rules are in [`index.md`](index.md). Compact version:

| File | Role |
|---|---|
| `.env` | ALGOPACK API key; user-filled, never committed |
| `index.md` | Full file map with role + update rule for each file |
| `algopack_notes.md` | Verified ALGOPACK facts (auth, TLS, endpoints, fields, universe, sources) |
| `certs/russian_trusted_ca.pem` | Russian Trusted Root/Sub CA for apim TLS |
| `how_to_use.md` | Setup, config.md reference, running the pipeline, troubleshooting |
| `config.md` | Data manifest: plan, paths, period, datasets, intervals, tickers, futures roll |
| `src/algopack_pipeline.py` | Pipeline source, single source of truth |
| `notebooks/algopack_pipeline.ipynb` | Generated Colab notebook — do not hand-edit |
| `tools/build_notebook.py` | Builds the notebook from `src/` |
| `tests/`, `pytest.ini` | Offline suite (fake ISS) + `pytest -m live` |
| `docs/usage.md`, `docs/universe.md`, `docs/universe_snapshot.md` | Usage/config reference, accessible universe, generated listing snapshot |
