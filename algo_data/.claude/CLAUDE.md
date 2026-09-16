# GOAL
Build a reusable, extensible **data-extraction pipeline for MOEX market data via the ALGOPACK service**.
Output feeds the sibling project `../moex-hack` (Chronos-2 multivariate forecasting on MOEX time series).

---

# DESCRIPTION
- Pull historical market data (candles + ALGOPACK analytical datasets) for a configurable ticker universe, interval and date range.
- Save clean, consistently-formatted files ready for downstream modelling (long format: `ticker, timestamp, features...`).
- Designed to grow: new datasets / tickers / covariates are added as config + small modules, not by rewriting the pipeline.

---

# ALGOPACK CLUES
- Product page / subscription / API key: https://data.moex.com/products/algopack
- Docs, guides, examples, sources: https://moexalgo.github.io/
- API key lives in `.env` (project root) as `ALGOPACK_API_KEY`. **Never print, log or commit it.** Loaded by `load_token()` (parses `.env`, falls back to `os.environ`); on Colab `.env` sits next to `config.md` on Drive.
- Official Python client `moexalgo` exists (`pip install moexalgo`). Auth mechanism and exact API differ between versions — **check current docs before coding, do not assume**.
- Datasets to investigate (names as known from ALGOPACK docs; confirm availability, depth, and field lists): candles, `tradestats`, `orderstats`, `obstats` (Super Candles, 5-min), `hi2` (concentration), `futoi` (futures open interest), mega alerts.
- Settled: history depth, pagination, MSK time zone, stock/futures/FX/index endpoints (indices = candles only; all served by apim with the key). Still undocumented: rate limits (none hit so far).
- Verified (2026-09-15, details in `algopack_notes.md`): auth = `Authorization: Bearer <key>` against `https://apim.moex.com/iss/...json`; apim TLS cert is issued by **Russian Trusted Sub CA** → requests need certifi + Russian Trusted Root/Sub CA bundle (esp. on Colab); ISS candles have no 15m interval, 500 rows/page, MSK naive timestamps.
- **Paid key (tested 2026-09-15):** all datasets open; datashop pages 1000 rows with `data.cursor` (INDEX/TOTAL/PAGESIZE); Super Candles `tradetime` = bar END; `fo` datashop endpoints need the **contract** SECID (`SiU5`), not the asset; **FUTOI ignores `start`/`limit` and returns max 1000 latest rows → fetch per day**; expired contracts resolve via ISS `securities/<SECID>` (`LSTTRADE`, `FRSTTRADE`) and their candles/datashop still work; CETS marketdata hides `VALTODAY`.
- `moexalgo` extras not in our pipeline: `tools/resample` (Super Candles resampling), `beta/issplus` (STOMP streaming). Everything else is plain REST.
- **Free key limits (tested):** `datashop/algopack/*` (Super Candles, HI2, Alerts) → HTTP 200 + HTML "available only to subscribers" (detect by content-type, not status); FUTOI OK from 2020-01-03 but last 14 days → `ERROR_MESSAGE` row; candles OK with ~16 min delay. Always check content-type and `ERROR_MESSAGE` blocks.
- Most precise API reference = OpenAPI spec: `https://raw.githubusercontent.com/moexalgo/moexalgo.github.io/main/static/openapi/openapi.yaml` (docs site is JS-rendered; WebFetch of it returns little).
- Deliverables (built): Colab notebook generated from `src/algopack_pipeline.py`, output to Drive, config from `config.md`, docs in `docs/`. Paid key active.
- User decisions (2026-09-15): intervals 1m/10m/1h/1d (native, no 15m); Parquet, tz-aware MSK; continuous futures (expiry-based roll, no price adjustment) + FUTOI; `.env` on Drive next to config.md; raw `requests` client + test suite; `plan: free|paid` switch.
- Prefer the `context7` MCP / WebFetch on moexalgo.github.io for up-to-date API details; use the `github-code-search` / `stackoverflow-search` skills for existing implementations.
- **Equity universe selection (2026-09-17, for `../moex-hack`'s Path A pivot)**: `rank_equity_universe()` + `save_equity_universe()` added to `src/algopack_pipeline.py` (after `universe_report()`/`universe_markdown()`). Filters TQBR shares to real equities via `INSTRID == "EQIN"` (ETFs/funds carry `INSTRID == "IFTF"` — confirmed live against `securities.json`, which was not previously in the pulled column set; `INSTRID` added to `universe_report()`'s shares columns). Ranks survivors by `VALTODAY` after a daily-candle history/missingness check. Full audit trail (every candidate + status), not just survivors — see `docs/usage.md` §6. Run 2026-09-17: 506 candidates → 80 selected, output at `data/universe/equity_universe.yaml`. `config.md`'s `tickers.shares` is **not yet** updated to use this list — still the original 10-ticker panel.

---

# RULES
- Files in the INDEX below must be kept up to date. Update the relevant file (and its index entry, if its role changes) after each logical step or session.
- **Before editing or creating any file in the repo, read [`index.md`](../index.md) first.**
- update CLAUDE.md each time rules, index, clues or other key parts change. Explicitly info user about it. 
- Secrets only in `.env`; `.env` is git-ignored.
- Parameters (tickers, intervals, dates, datasets, output paths) → config files, not hard-coded.
- Raw downloads and processed outputs kept separate (`data/raw/` vs `data/processed/`), both git-ignored.
- Pipeline code lives only in `src/algopack_pipeline.py`; after any change run `python tools/build_notebook.py` and `pytest` (plus `pytest -m live` when API behaviour is touched). Never hand-edit the notebook.

---

# INDEX
Compact map. Full descriptions + update rules in [`index.md`](../index.md).

- `.env` — ALGOPACK API key (`ALGOPACK_API_KEY`); user-filled, never committed.
- `.gitignore` — Ignores `.env`, data, caches.
- `index.md` — Full file map with role + update rule for each file.
- `current_state.md` — Session scratchpad (done / open questions / next steps); refresh end of every session.
- `needed.md` — Open gaps (blockers / user decisions / verify-later); settle before building.
- `algopack_notes.md` — Verified ALGOPACK facts (auth, TLS, endpoints, fields, universe, sources).
- `certs/russian_trusted_ca.pem` — Public Russian Trusted Root/Sub CA for apim TLS (Sub CA expires 2027-03-06).
- `how_to_use.md` — Package instruction for users (setup, config.md, run, outputs, troubleshooting, status).
- `config.md` — Data manifest (first yaml block): plan, paths, period, datasets, intervals, tickers, futures roll.
- `src/algopack_pipeline.py` — Pipeline source, `# %%` cells; single source of truth.
- `notebooks/algopack_pipeline.ipynb` — Generated Colab notebook (do not hand-edit).
- `tools/build_notebook.py` — Builds the notebook from `src/` + embeds CA PEM.
- `tests/`, `pytest.ini` — Offline suite (fake ISS) + `pytest -m live`.
- `docs/usage.md`, `docs/universe.md`, `docs/universe_snapshot.md` — Usage/config reference (incl. §6 equity universe selection), accessible universe, generated listing snapshot.
- `tests/test_universe.py` — Offline tests for `rank_equity_universe()`/`save_equity_universe()`.
- `tools/probe_algopack.py` — Re-runnable live access check; never prints the key.
- `.claude/skills/` — `github-code-search`, `stackoverflow-search`; `.claude/commands/search-github.md`.
