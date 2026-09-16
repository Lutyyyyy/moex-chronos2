# NEEDED: open gaps

_Updated 2026-09-15 (pipeline v1 built). Verified facts are in [`algopack_notes.md`](algopack_notes.md). Usage is in [`docs/usage.md`](docs/usage.md)._
Legend: 🟡 decision needed from user · ⚪ verify later

## ✅ Settled (2026-09-15)
- Key and plan: paid plan active, all datasets accessible (probe + `pytest -m live` pass).
- Intervals: 1m, 10m, 1h, 1d (ISS native, no resampling).
- Panel: 10 shares + IMOEX + CNYRUB_TOM + continuous Si/BR/RI/GD (see `config.md`, `docs/universe.md`).
  **Superseded 2026-09-17** for `../moex-hack`'s Path A pivot: an 80-ticker equity universe is
  now available (`data/universe/equity_universe.yaml`, via `rank_equity_universe()` — see
  `current_state.md`). `config.md`'s `tickers.shares` has not yet been updated to use it — still
  pending, listed under "Next steps" in `current_state.md`.
- Period: set in config; default 2020-01-01..2024-12-31.
- Output: Parquet, tz-aware `Europe/Moscow`.
- Futures: continuous by expiry-based roll (`roll_days_before_expiry`, default 5), with `contract` and `roll` columns, no price adjustment. FUTOI per asset.
- Drive: `MyDrive/algo_data/` holds `config.md`, `.env` and `data/`.
- Key source: `.env` next to config.md.
- Client: raw `requests`. `moexalgo`-only features are the Super Candles resampler and STOMP streaming; neither is needed now. Test suite in place.
- `plan: free|paid` switch implemented.
- TLS CA bundle: stored in `certs/` and embedded in the notebook.

## 🟡 Decisions (not blocking)
1. **Super Candles at 10m/1h/1d?** They are native 5-min only. Options: (a) keep 5-min (current), resample downstream; (b) add resampling in the pipeline. Aggregation rules differ per field (sum/last/VWAP/mean); `moexalgo.tools.resample` has reference formulas.
2. **Futures price adjustment.** It is currently none, with a `roll` flag. Add back-adjustment (ratio/difference) if `moex-hack` needs continuous price levels rather than returns.
3. **Output for `moex-hack`.** Is the per-group files layout (`processed/<dataset>[_<interval>]/<group>.parquet`) fine, or do you want one merged multivariate table per interval (candles + covariates joined on timestamp)?

## ⚪ To verify later
4. **Full 2020–2024 run time on Colab.** The docs estimate "a few hours" from local per-request timings; it has not been run end to end. Also: is `apim.moex.com` reachable from Colab's non-RU IPs? Untestable from here, so check on the first Colab run.
5. **Rate limits.** Undocumented; none hit at about 5 req/s sequential.
6. **Split adjustment of ISS candles** (GMKN 2024, VTBR 2024). Daily data shows no jumps, which suggests adjusted history. Intraday candles and Super Candles are not checked.
7. **Delisted/renamed tickers** for wider historical panels (board lists show only current listings).
8. **`certs/` Sub CA expires 2027-03-06.** Refresh it and rebuild the notebook.
