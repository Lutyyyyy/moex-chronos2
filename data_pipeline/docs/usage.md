# Usage: config.md + pipeline

## 1. What you get
Long-format Parquet with **`ticker, timestamp` first**. Timestamps are **tz-aware `Europe/Moscow`**.

```
<output_root>/
  processed/                     ← results, rebuilt on every run for the current config
    candles_1m/ candles_10m/ candles_1h/ candles_1d/
      shares.parquet  indices.parquet  currency.parquet  futures.parquet
    tradestats/ orderstats/ obstats/ hi2/ alerts/   {shares,currency,futures}.parquet (by availability)
    futoi/futures.parquet
    _summary.csv                 ← rows / tickers / time range per file
    _failed.csv                  ← only if some chunks failed (re-run to retry)
  raw/<dataset>/<group>/<symbol>/[<interval>/]YYYY-MM.parquet   ← month-chunk cache (resume)
  meta/contracts/<code>_<year>.json                             ← futures contract metadata cache
  universe/                      ← optional universe_report() + rank_equity_universe() output
    equity_universe.yaml           ← selected tickers + selection metadata (ready to paste into config.md)
    equity_universe_candidates.csv ← full audit trail: every candidate + status (selected / excluded + reason)
```

Load: `pd.read_parquet(".../processed/candles_1h/shares.parquet")`

## 2. Colab
1. Create the Drive folder `MyDrive/algo_data/`. Put `config.md` (copy from repo) and `.env` in it. The `.env` has one line: `ALGOPACK_API_KEY=<token>`.
2. Open `notebooks/algopack_pipeline.ipynb` in Colab (upload it, or open from Drive/GitHub).
3. If your folder differs, change `CONFIG_PATH` in cell 0. Then **Run all**.
   - Cell 0 mounts Drive.
   - Cells 1–7 define the pipeline.
   - Cell 8 runs it.
   - Cell 9 (optional) makes a universe snapshot.
   - Cell 10 lists and loads the results.
4. **Interrupted run** (disconnect, timeout): just run again. Finished months are skipped, and the current month is always refreshed.

Local run (repo root):
```
python -c "import sys; sys.path.insert(0,'src'); import algopack_pipeline as ap; print(ap.run('config.md'))"
```

## 3. config.md reference
Only the **first ```yaml block** is read. Relative paths resolve against the folder containing `config.md`.

| Key | Values | Notes |
|---|---|---|
| `plan` | `paid` \| `free` | `free`: skips `tradestats, orderstats, obstats, hi2, alerts` with a warning and clamps FUTOI end to today−14d (free-plan embargo). |
| `paths.env_file` | path | `.env` with `ALGOPACK_API_KEY=...`. Falls back to the env variable `ALGOPACK_API_KEY`. |
| `paths.output_root` | path | Output folder, e.g. `data` (next to config.md) or an absolute Drive path. |
| `period.start` / `period.end` | `YYYY-MM-DD`, `end` may be `today` | Inclusive, by MSK calendar date. The end is capped at today. |
| `datasets` | `candles, tradestats, orderstats, obstats, hi2, alerts, futoi` | Each is fetched only for the groups where it exists (table below). |
| `candles.intervals` | `1m, 10m, 1h, 1d` | ISS native intervals. No resampling. |
| `tickers.shares` | TQBR SECIDs | e.g. `SBER` |
| `tickers.indices` | SNDX SECIDs | e.g. `IMOEX`. Candles only. |
| `tickers.currency` | CETS SECIDs | e.g. `CNYRUB_TOM` |
| `tickers.futures` | list of `{code, months?, roll_days?}` or plain codes | `code` = 2-char contract prefix (`Si`, `BR`, `RI`, `GD`…). It becomes a **continuous series** (section 5). FUTOI uses the same code. |
| `futures.roll_days_before_expiry` | int, default 5 | Global roll rule. |
| `request.pause_sec / max_retries / timeout_sec` | 0.05 / 5 / 60 | Retries cover network errors, HTTP 429 and 5xx, with exponential backoff. |
| `overwrite` | bool | `true` re-downloads all chunks. |

Dataset availability by group:

| dataset | shares | indices | currency | futures | granularity | history (paid) |
|---|---|---|---|---|---|---|
| candles | ✓ | ✓ | ✓ | ✓ | 1m/10m/1h/1d | SBER 1m from 2011; per ticker see `candleborders` |
| tradestats | ✓ | | ✓ | ✓ | 5 min | 2020 |
| orderstats | ✓ | | ✓ | | 5 min | 2020 |
| obstats | ✓ | | ✓ | ✓ | 5 min | 2020 |
| hi2 | ✓ | | ✓ | ✓ | daily (≈18:40–18:50) | 2020-01-03 |
| alerts | ✓ | | | ✓ | events | 2024 (docs) |
| futoi | | | | ✓ (asset code) | 5 min snapshots, FIZ/YUR | 2020-01-03 |

## 4. Column semantics
- **candles**: `open high low close volume value`. `timestamp` = candle **open** time. Futures candles have `value = 0` (ISS does not fill it); CNYRUB_TOM has empty `volume`/`value`.
  - `candles/shares` also gets a `close_adj` column: `close` adjusted for cash dividends (gross, backward-multiplicative — prices strictly before each **ex-date** are scaled by `1 - dividend/close_prev`, composing across multiple dividends) and known stock splits (`KNOWN_SPLITS` in `src/algopack_pipeline.py`, currently just BELU's 2024-08-22 8-for-1 — manually verified, not auto-detected). Dividend data comes from poptimizer's community-maintained dump (`https://raw.githubusercontent.com/WLM1ke/poptimizer/master/dump/dividends.json`, cached at `data/dividends.json`) plus `KNOWN_EXTRA_DIVIDENDS` (verified dividends missing from the dump: SVCB, WUSH, RUAL). The dump's `day` is the **register (record) date**, not the ex-date: `ex_date_from_record` derives the ex-date from the exchange calendar and the settlement regime (T+2 for trades up to 2023-07-28, T+1 from 2023-07-31), i.e. the first trading day whose settlement falls after the record date. Before 2026-09-24 the register date was used as the ex-date, which put every pre-2023-07-31 adjustment one trading day late (a spurious −div/+div pair around each dividend); verified fixed on 288 events (mean adjusted ex-day return ≈ +1–1.6%, the residual expected from adjusting by the gross dividend while prices drop by roughly the after-tax amount). Same-date multiple rows in the dump are real (separate declarations sharing a record date, e.g. LKOH 2022-12-21 537 + 256 RUB) or component splits summing to the official amount (ABRD, VRSB) — not duplicates. `open/high/low/close/volume/value` are left untouched (raw); only `close_adj` is adjusted. `KNOWN_UNPAID_DIVIDENDS` drops dump rows that were recommended but never paid (MGNT 560 RUB, record 2025-01-09: EGM failed for lack of quorum). Dividends whose record date is after the last trading day in the data are not applied (not ex yet). Universe tickers without any dividend record were spot-checked 2026-09-24 (FESH, SPBE, UWGN, MTLR, UGLD: no dividends 2021–2024; ENPG, VKCO, UNAC, LENT, RNFT ordinary: none found, lower-confidence).
- **tradestats / orderstats / obstats** (Super Candles):
  - `timestamp` = **bar start**. ALGOPACK's `tradetime` is the bar end and is shifted by −5 min, so it aligns with candles.
  - Field lists differ by market (e.g. `obstats` eq has `spread_bbo…`, fx/fo have `mid_price, spread_l1…`).
  - Definitions: https://github.com/moexalgo/moexalgo.github.io/blob/main/docs/description/supercandles.md
- **hi2**: pivoted wide, one column per metric (`hhi_volume, hhi_buy, …`). `timestamp` = publication time.
- **alerts**: events, several rows per timestamp allowed. Columns: `alert_type, threshold, value, reference` (JSON string).
- **futoi**: pivoted wide by client group, e.g. `pos_fiz, pos_yur, pos_long_fiz, pos_short_num_yur…` (fiz = individuals, yur = legal entities). `timestamp` = snapshot time.
- Dropped: `SYSTIME`, `secid` (replaced by `ticker`), `asset_code`. FUTOI also drops `sess_id, seqnum, systime`.

## 5. Futures: continuous series
- Contracts `<code><month><year digit>` (e.g. `SiH4`) are discovered through ISS `securities/<SECID>`, which gives the last trade date. Results are cached in `meta/contracts/`.
- The front contract stays active until `last_trade − roll_days` (inclusive). The next contract takes over from the following day.
- Output columns `contract` (SECID used for the row) and `roll` (True on the first row after a switch).
- **Prices are not back-adjusted.** When computing returns, drop or mask rows where `roll` is True.
- Si, RI and GD list quarterly contracts (H, M, U, Z). BR lists monthly ones. Restrict with `months: HMUZ` if needed.

## 6. Equity universe selection

`rank_equity_universe(tables, client, top_n=80, min_history_days=240, max_missing_frac=0.05)`
builds a reproducible ~N-ticker equity universe on top of `universe_report()`'s `shares`
table, for downstream studies that need more than a hand-picked list:

1. **Non-equity filter**: excludes rows where `INSTRID != "EQIN"` (ETFs/funds — e.g. `AKMM`,
   `LQDT`, `SBMM` carry `INSTRID="IFTF"`) without any further request.
2. **History-quality filter**: for each remaining candidate, fetches daily candles over a
   trailing window (default ≈ `min_history_days * 1.6` calendar days) and excludes tickers
   with fewer than `min_history_days` bars, or with a missing-bar fraction (vs. expected
   business days in the window) above `max_missing_frac`.
3. **Ranking**: survivors are ranked by today's `VALTODAY` (RUB turnover) and the top `top_n`
   are marked `selected`; the rest get `excluded: below top_n cutoff`.

Returns **every** candidate (not just the selected ones) with a `status` column stating why
it was excluded, so the selection is auditable rather than opaque. `save_equity_universe(ranked, out_dir, meta)`
writes the full table to `equity_universe_candidates.csv` and the selected tickers (plus
selection metadata) to `equity_universe.yaml`, ready to paste into `config.md`'s
`tickers.shares:` block.

```python
tables = universe_report(cfg, client)
ranked = rank_equity_universe(tables, client, top_n=80)
save_equity_universe(ranked, cfg.output_root / "universe", meta={"generated": today_msk().isoformat()})
```

Cost: one candles request per equity candidate (paginated at 500 rows/page for longer
windows) — on the full TQBR board (~460 real equities after the ETF filter) this is on the
order of 500 requests, ~1.5 minutes at the default `pause_sec`.

## 7. Runtime & resume
- Each (dataset, symbol, interval, month) is one raw chunk. Past months are fetched once, and a re-run skips them.
- Pagination: candles have 500 rows/page, datashop 1000 rows/page. FUTOI takes one request per calendar day because the API ignores paging and caps at 1000 rows.
- Measured locally: one month of 1m candles for one share ≈ 40–50 requests. Requests run sequentially at ≈0.15–0.3 s each.
- **My estimate, not measured end-to-end:** the default config for 2020–2024 is on the order of **40–50k requests, a few hours**. 1m candles dominate; everything else is minutes. Colab sessions can drop, and re-running resumes.
- No throttling was observed (30 rapid requests, all 200). Rate limits aren't documented.

## 8. Errors you may see
| Message | Meaning / action |
|---|---|
| `HTTP 401 ... API key missing, invalid or expired` | Fix `.env`. The token is a JWT from https://data.moex.com/personal-account |
| `'available only to subscribers'` | Dataset not in the plan. It is skipped. Set `plan: free` to avoid requests. |
| `Free users can't receive data for the last 14 days` | Free plan FUTOI embargo. `plan: free` clamps it automatically. |
| `failed after N retries` | Network/5xx problem. The chunk goes to `_failed.csv`; re-run. |
| `CERTIFICATE_VERIFY_FAILED` | The Russian Trusted CA is missing. The notebook embeds it; as a module it's read from `certs/`. |

## 9. Tests & maintenance
- `pytest`: offline suite with a fake ISS (config, client, transforms, futures roll, end-to-end run and resume, notebook build).
- `pytest -m live`: real API with the key from `.env`. Covers SBER, IMOEX, CNYRUB_TOM and Si over 2024-03-14..19, all datasets. Takes about 40 s.
- After editing `src/algopack_pipeline.py`, run `python tools/build_notebook.py`. A test fails if the notebook is stale.
- **The Russian Trusted Sub CA in `certs/` expires 2027-03-06.** Refresh it from `https://gu-st.ru/content/Other/doc/` and rebuild the notebook.
