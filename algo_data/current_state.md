# Current state

_Last updated: 2026-09-17 (equity universe selection added; adopted by ../moex-hack Path A)._

## Done
- Access checks: auth, TLS CA, free and paid limits, endpoints, paging quirks. Details in `algopack_notes.md`.
- User decisions recorded in `needed.md` (✅ section).
- **Pipeline v1:**
  - `src/algopack_pipeline.py` is the source of truth. `notebooks/algopack_pipeline.ipynb` is generated from it by `tools/build_notebook.py`.
  - Config comes from the first yaml block of `config.md`: plan free/paid, paths, period, datasets, candle intervals 1m/10m/1h/1d, tickers by group, continuous futures roll.
  - Datasets: candles, tradestats, orderstats, obstats, hi2, alerts, futoi.
  - Output is Parquet, tz-aware MSK: `processed/<dataset>[_<interval>]/<group>.parquet`, plus a raw month-chunk cache so runs resume.
  - Futures: contract discovery (cached), expiry-based roll, `contract`/`roll` columns.
  - `universe_report()` writes a listing snapshot.
- **Equity universe selection (2026-09-17, for `../moex-hack`'s Path A pivot):**
  - `rank_equity_universe(tables, client, top_n, min_history_days, max_missing_frac)` — filters
    TQBR `shares` to real equities (`INSTRID == "EQIN"`, excludes ETFs/funds), checks each
    candidate's daily-candle history for length/missingness, ranks survivors by `VALTODAY`.
    Returns every candidate with a `status` (selected / excluded + reason) — full audit trail.
  - `save_equity_universe(ranked, out_dir, meta)` writes `equity_universe_candidates.csv` (audit
    trail) + `equity_universe.yaml` (selected tickers + selection metadata, paste-ready for
    `config.md`).
  - **Run 2026-09-17**: 506 TQBR candidates → 243 excluded (non-equity/ETF), 13 excluded
    (short history / too much missing data), 170 excluded (below top-80 cutoff by turnover),
    **80 selected**. 527 requests, ~94s. Output at `data/universe/equity_universe.yaml` (gitignored,
    under `data/`) — regenerate via the snippet in `docs/usage.md` §6 if a fresh universe is needed.
- Tests: `pytest` gives 45 offline tests passing (40 original + 5 new for `rank_equity_universe`/
  `save_equity_universe`); `pytest -m live` gives 4 live tests passing (SBER/IMOEX/CNYRUB_TOM/Si,
  2024-03-14..19, all datasets, roll check, zero-request re-run).
- Docs: `docs/usage.md` (now includes §6 equity universe selection), `docs/universe.md`, `docs/universe_snapshot.md`.
- Local env: installed `pyarrow`, `pyyaml`, `pytest`.

## Next steps
1. `config.md`'s `tickers.shares` still holds the original 10-ticker hand-picked panel — expand
   it to (a subset of) the 80-ticker `equity_universe.yaml` list before running the full
   historical pipeline for `../moex-hack`'s Path A/B/C.
2. User: copy `config.md` and `.env` to `MyDrive/algo_data/`, open the notebook in Colab, run all. Check that apim is reachable from Colab and how long the full run takes.
3. Answer the 🟡 items in `needed.md`: Super Candles resampling, futures price adjustment, merged table for moex-hack.
4. Connect the output to `../moex-hack` — see `path_a/basic_cells.ipynb`'s `load_from_algopack`
   adapter (Phase A4 of the pivot plan) for the ingestion shape it expects.
