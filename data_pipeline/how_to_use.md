# How to use: ALGOPACK → Parquet pipeline

This pipeline downloads MOEX market data through **ALGOPACK** (candles plus analytical datasets) for a ticker panel set in `config.md`. It saves clean long-format **Parquet** files with **tz-aware Moscow timestamps**, ready for forecasting models such as Chronos-2.

Contents:
1. What's in the package
2. Quick start on Google Colab
3. Running locally
4. `config.md` in detail
5. Output files and columns
6. Futures: continuous series
7. Resume, refresh, runtime
8. Errors and troubleshooting
9. Tests and maintenance
10. Status: verified facts, limits, open questions

---

## 1. What's in the package

| Path | What it is |
|---|---|
| `how_to_use.md` | This instruction |
| `config.md` | **Data manifest.** The first ` ```yaml ` block is the pipeline config. |
| `notebooks/algopack_pipeline.ipynb` | **The notebook to run** (Colab or Jupyter). Self-contained: the whole pipeline plus the TLS certificate. |
| `src/algopack_pipeline.py` | The same pipeline as a Python module (source of the notebook) |
| `tools/build_notebook.py` | Regenerates the notebook from `src/` |
| `tools/probe_algopack.py` | Quick API access check (auth, datasets, freshness) |
| `certs/russian_trusted_ca.pem` | Public Russian Trusted Root/Sub CA, needed to connect to `apim.moex.com` |
| `tests/`, `pytest.ini` | Offline test suite plus a live API test |
| `docs/usage.md` | Short reference (same topics, condensed) |
| `docs/universe.md`, `docs/universe_snapshot.md` | Which tickers and datasets are available, history depth, caveats |
| `.env` | **Not included.** You create it yourself; it holds your API key. |

Requirements: Python ≥ 3.10 with `requests, pandas, pyarrow, pyyaml, certifi`. Colab has all of them preinstalled. For tests, also `pytest`.

---

## 2. Quick start on Google Colab

### Step 1: get an API key
- Subscribe to ALGOPACK at https://data.moex.com/products/algopack.
- Copy your token (API key) from https://data.moex.com/personal-account.
- The token is a long string with two dots (a JWT). **Copy it completely.** A truncated token gives `HTTP 401`.

### Step 2: prepare a Google Drive folder
Create `MyDrive/data_pipeline/` and put two files in it:

```
MyDrive/data_pipeline/
├── config.md      ← copy from the package, edit to taste (section 4)
└── .env           ← one line: ALGOPACK_API_KEY=eyJhbGciOi...   (no quotes needed)
```

Keep `.env` private: never share it and never commit it.

### Step 3: open and run the notebook
1. Open `notebooks/algopack_pipeline.ipynb` in Colab (*File → Upload notebook*, or open it from Drive/GitHub).
2. If your folder is not `MyDrive/data_pipeline/`, change `CONFIG_PATH` in **cell 0**.
3. **Runtime → Run all.** Colab asks for permission to mount Drive; allow it.

Notebook cells:

| Cell | Does |
|---|---|
| 0 | Mounts Google Drive, sets `CONFIG_PATH` |
| 1 | Imports, constants, embedded TLS certificate |
| 2 | Config parsing and validation |
| 3 | HTTP client: auth, retries, error detection, pagination |
| 4 | Download and normalize each dataset |
| 5 | Futures contract discovery and roll schedule |
| 6 | Storage, processed-file build, `run()` |
| 7 | `universe_report()` (listing snapshot) |
| 8 | **Run:** `cfg = load_config(CONFIG_PATH)`, `summary = run(cfg)` |
| 9 | Optional: universe snapshot (uncomment to use) |
| 10 | Lists result files and loads an example table |

### Step 4: watch progress
The log prints the config, the futures roll schedule, how many month chunks are planned/cached/to fetch, and progress with ETA every 30 s:

```
16:00:01 INFO futures Si: SiH0[2020-01-01..2020-03-14], SiM0[2020-03-15..2020-06-13], ...
16:00:02 INFO 3120 month chunks planned, 0 cached, 3120 to fetch
16:00:32 INFO fetched 41/3120 chunks, 250 requests, elapsed 0:00:30, eta 0:37:30
...
16:45:10 INFO done: 30 processed files under /content/drive/MyDrive/data_pipeline/data/processed
```

`summary` (the last output of cell 8) is a table with dataset, interval, group, rows, number of tickers, first and last timestamp, and file path.

### Step 5: if Colab disconnects
**Run all again.** Months already downloaded are skipped, so the run continues where it stopped (section 7).

### Step 6: load the data

```python
import pandas as pd
root = "/content/drive/MyDrive/data_pipeline/data/processed"
candles_1h = pd.read_parquet(f"{root}/candles_1h/shares.parquet")
futoi      = pd.read_parquet(f"{root}/futoi/futures.parquet")
```

---

## 3. Running locally

From the package root, with `config.md` and `.env` next to each other:

```bash
pip install requests pandas pyarrow pyyaml certifi
python -c "import sys; sys.path.insert(0, 'src'); import algopack_pipeline as ap; print(ap.run('config.md'))"
```

Or open `notebooks/algopack_pipeline.ipynb` in Jupyter from the package root. Cell 0 falls back to `config.md` in the working directory when not on Colab.

Useful calls (module or notebook):

```python
cfg = ap.load_config("config.md")       # parse + validate; raises ConfigError listing every problem
print(cfg.describe())                   # what will be downloaded
ap.run(cfg)                             # full run
ap.run(cfg, datasets=["candles"])       # only some datasets from the config
ap.run(cfg, build_only=True)            # no downloads; rebuild processed/ from cached raw chunks
ap.universe_report(cfg)                 # listing snapshot → <output_root>/universe/
```

---

## 4. `config.md` in detail

### 4.1 How the file is read
- The pipeline reads **only the first ` ```yaml ` code block**. Everything outside it is free-form notes. Don't put another yaml block above the config.
- **Relative paths resolve against the folder that contains `config.md`**. The same file works locally and on Drive.
- The config is validated before any download, and all problems are reported at once, e.g.:
  ```
  ConfigError: config.md errors:
    - candles.intervals: unknown '15m' (allowed: ['1m', '10m', '1h', '1d'])
    - tickers.futures: code must be the 2-char contract prefix (e.g. Si, BR), got 'SIX'
  ```

### 4.2 Full example (the default config)

```yaml
plan: paid                    # paid | free

paths:
  env_file: .env              # file with ALGOPACK_API_KEY=...
  output_root: data           # where raw/, processed/, meta/, universe/ are written

period:
  start: 2020-01-01           # YYYY-MM-DD
  end: 2024-12-31             # YYYY-MM-DD or today

datasets: [candles, tradestats, orderstats, obstats, hi2, alerts, futoi]

candles:
  intervals: [1m, 10m, 1h, 1d]

tickers:
  shares: [SBER, GAZP, LKOH, ROSN, NVTK, GMKN, TATN, MGNT, PLZL, CHMF]
  indices: [IMOEX]
  currency: [CNYRUB_TOM]
  futures:
    - {code: Si}
    - {code: BR}
    - {code: RI}
    - {code: GD}

futures:
  roll_days_before_expiry: 5

request:
  pause_sec: 0.05
  max_retries: 5
  timeout_sec: 60

overwrite: false
```

### 4.3 Keys

| Key | Allowed values | Default | Meaning |
|---|---|---|---|
| `plan` | `paid`, `free` | `paid` | Your ALGOPACK subscription. `free` skips `tradestats, orderstats, obstats, hi2, alerts` (paid-only; you get a warning) and ends FUTOI at **today − 14 days** (free-plan embargo). Candles work on both plans. |
| `paths.env_file` | path | `.env` | File with the line `ALGOPACK_API_KEY=...`. If the file is missing, the environment variable `ALGOPACK_API_KEY` is used. |
| `paths.output_root` | path | `data` | Root folder for all outputs. Relative to `config.md`, or absolute (e.g. `/content/drive/MyDrive/other/data`). |
| `period.start` | `YYYY-MM-DD` | required | First calendar day (MSK), inclusive |
| `period.end` | `YYYY-MM-DD` or `today` | `today` | Last calendar day, inclusive. Anything after today is capped to today. |
| `datasets` | list, see 4.4 | `[candles]` | What to download. Each dataset is fetched only for groups where it exists. |
| `candles.intervals` | `1m`, `10m`, `1h`, `1d` | `[1d]` | Candle intervals as served by MOEX. **There is no 5m/15m/30m**: MOEX ISS doesn't provide them. |
| `tickers.shares` | TQBR tickers | `[]` | Shares, e.g. `SBER` |
| `tickers.indices` | SNDX tickers | `[]` | Indices, e.g. `IMOEX`, `RGBI`, `MOEXOG` (candles only) |
| `tickers.currency` | CETS tickers | `[]` | FX, e.g. `CNYRUB_TOM`, `GLDRUB_TOM` |
| `tickers.futures` | list of codes or `{code, months, roll_days}` | `[]` | Continuous futures by **2-character contract prefix** (`Si`, `BR`, `RI`, `GD`, `CR`, `MX`, …). The same code is used for FUTOI. See section 6. |
| `tickers.futures[].months` | subset of `FGHJKMNQUVXZ` | all listed | Restrict to specific contract months, e.g. `HMUZ` (quarterly) |
| `tickers.futures[].roll_days` | int | global value | Per-asset override of the roll rule |
| `futures.roll_days_before_expiry` | int | `5` | Switch to the next contract N calendar days before the current one's last trade date |
| `request.pause_sec` | float | `0.05` | Minimum pause between API requests |
| `request.max_retries` | int | `5` | Retries on network errors, HTTP 429 and 5xx (exponential backoff, max 60 s) |
| `request.timeout_sec` | float | `60` | Per-request timeout |
| `overwrite` | bool | `false` | `true` re-downloads every chunk. Normally keep `false`; the current month is refreshed anyway. |

At least one ticker (in any group) must be configured.

### 4.4 Which dataset exists for which group

| Dataset | What it is | shares | indices | currency | futures | Granularity | History (paid, checked) |
|---|---|---|---|---|---|---|---|
| `candles` | OHLCV candles | ✓ | ✓ | ✓ | ✓ | 1m / 10m / 1h / 1d | Long; e.g. SBER 1m from 2011-12, daily from 2007 |
| `tradestats` | Super Candles: trade flow metrics | ✓ | | ✓ | ✓ | 5 min | From 2020 |
| `orderstats` | Super Candles: order flow metrics | ✓ | | ✓ | | 5 min | From 2020 |
| `obstats` | Super Candles: order book metrics | ✓ | | ✓ | ✓ | 5 min | From 2020 |
| `hi2` | Market concentration index (HHI metrics) | ✓ | | ✓ | ✓ | Daily (≈ 18:40–18:50) | From 2020-01-03 |
| `alerts` | Mega Alerts: anomaly events | ✓ | | | ✓ | Events | From 2024 |
| `futoi` | Futures open interest, individuals vs legal entities | | | | ✓ (asset) | 5-min snapshots | From 2020-01-03 |

If a dataset is listed but doesn't apply to a group (e.g. `orderstats` for futures), that combination is silently skipped.

### 4.5 Typical edits

**Small test first** (a few minutes):
```yaml
period: {start: 2024-03-11, end: 2024-03-22}
datasets: [candles, tradestats, futoi]
candles: {intervals: [1h, 1d]}
tickers:
  shares: [SBER]
  futures: [Si]
```

**Daily data only, long history:**
```yaml
period: {start: 2015-01-01, end: today}
datasets: [candles]
candles: {intervals: [1d]}
```

**Free plan:**
```yaml
plan: free
datasets: [candles, futoi]
```

**Add a ticker:** append it to its group (e.g. `shares: [..., YDEX]`). Only the new ticker is downloaded, and processed files are rebuilt for the whole panel.

**Find valid tickers:** check `docs/universe_snapshot.md`, or run `universe_report(cfg)` for a fresh list with today's turnover. Use `SECID` for shares/indices/currency and `code` for futures.

**Keep data up to date:** set `end: today` and re-run periodically. Only the current month (and anything missing) is downloaded.

---

## 5. Output files and columns

### 5.1 Folder layout

```
<output_root>/
├── processed/                                ← USE THESE (rebuilt from raw on every run)
│   ├── candles_1m/   shares.parquet  indices.parquet  currency.parquet  futures.parquet
│   ├── candles_10m/  …
│   ├── candles_1h/   …
│   ├── candles_1d/   …
│   ├── tradestats/   shares.parquet  currency.parquet  futures.parquet
│   ├── orderstats/   shares.parquet  currency.parquet
│   ├── obstats/      shares.parquet  currency.parquet  futures.parquet
│   ├── hi2/          shares.parquet  currency.parquet  futures.parquet
│   ├── alerts/       shares.parquet  futures.parquet
│   ├── futoi/        futures.parquet
│   ├── _summary.csv                          ← rows / tickers / time range per file
│   └── _failed.csv                           ← only if some chunks failed
├── raw/<dataset>/<group>/<symbol>/[<interval>/]YYYY-MM.parquet   ← download cache, one file per month
├── meta/contracts/<code>_<year>.json                             ← futures contract metadata cache
└── universe/                                                     ← only after universe_report()
```

Processed files contain **exactly the current config's tickers and period**. Raw chunks are never deleted, so changing the config is cheap.

### 5.2 Common format
- **Long format:** one row per `ticker` × `timestamp` (alerts can have several rows per timestamp).
- First columns are always `ticker, timestamp`. Futures files add `contract, roll`.
- `timestamp` is `datetime64[ns, Europe/Moscow]` (tz-aware, UTC+3, no DST).
- For futures, `ticker` is the config code (`Si`), so futures candles, Super Candles and FUTOI join on `ticker, timestamp`.
- Rows are sorted by `ticker, timestamp` and de-duplicated.

### 5.3 Columns per dataset

| Dataset | `timestamp` means | Columns |
|---|---|---|
| candles | Candle **open** time | `open, high, low, close, volume, value` |
| tradestats | **Bar start** (5-min bar; ALGOPACK's `tradetime` = bar end, shifted by −5 min) | `pr_open, pr_high, pr_low, pr_close, pr_std, vol, val, trades, pr_vwap, pr_change, trades_b, trades_s, val_b, val_s, vol_b, vol_s, disb, pr_vwap_b, pr_vwap_s, sec_pr_*`. Futures add `im, oi_open, oi_high, oi_low, oi_close`. |
| orderstats | Bar start | `put_orders_b/s, put_val_b/s, put_vol_b/s, put_vwap_b/s, cancel_*` (+ `put_vol, put_val, put_orders, cancel_vol…` for shares) |
| obstats | Bar start | Shares: `spread_bbo, spread_lv10, spread_1mio, levels_b/s, vol_b/s, val_b/s, imbalance_vol_bbo, imbalance_val_bbo, imbalance_vol, imbalance_val, vwap_b/s, vwap_b/s_1mio`. Currency/futures: `mid_price, micro_price, spread_l1..l10, levels_b/s, vol_b_l1..l10, vol_s_l1..l20, vwap_b/s_l3..l10` |
| hi2 | Publication time (daily) | One column per metric: `hhi_volume, hhi_buy, hhi_sell, hhi_agressive, hhi_agressive_buy, hhi_agressive_sell, hhi_passive, hhi_passive_buy, hhi_passive_sell, hhi_netflow_buy, hhi_netflow_sell` |
| alerts | Event time | `alert_type, threshold, value, reference` (JSON string with context) |
| futoi | Snapshot time (5 min) | `pos_fiz, pos_yur, pos_long_fiz, pos_long_yur, pos_short_fiz, pos_short_yur, pos_long_num_fiz, pos_long_num_yur, pos_short_num_fiz, pos_short_num_yur` (fiz = individuals, yur = legal entities; `*_num` = number of holders) |

Field definitions and formulas (official): https://github.com/moexalgo/moexalgo.github.io/tree/main/docs/description and `…/docs/method`.

Known data details:
- Futures candles have `value = 0`; MOEX doesn't fill it. Use `volume`.
- `CNYRUB_TOM` candles have empty `volume`/`value`.
- Session hours changed over the years (morning, evening and weekend sessions), so the number of bars per day varies.
- MOEX shares didn't trade from 2022-02-28 to 2022-03-23, so that period is a gap.

---

## 6. Futures: continuous series

Futures contracts expire, so each `tickers.futures` code is stitched into one continuous series:

1. **Discovery.** Candidate SECIDs `<code><month><year digit>` (e.g. `SiH4` = Si March 2024) are looked up in MOEX ISS. This gives each contract's first and last trade dates. Results are cached in `meta/contracts/` (past years are never re-queried).
2. **Roll rule.** A contract is "front" until `last_trade_date − roll_days` (inclusive), and the next contract takes over the following day. Example with `roll_days: 5`: SiH4 (last trade 2024-03-21) is used through 2024-03-16, and SiM4 from 2024-03-17.
3. **Stitching.** Every futures dataset (candles, tradestats, obstats, hi2, alerts) takes each contract's rows only inside its window.
4. **Columns.** `contract` holds the SECID used for that row. `roll` is `True` on the first row after a contract switch.

⚠️ **Prices are not back-adjusted.** At a roll the price jumps by the calendar spread between contracts. When computing returns, **drop or mask rows where `roll == True`**:

```python
df = pd.read_parquet(".../candles_1h/futures.parquet")
df["ret"] = np.log(df["close"]).groupby(df["ticker"]).diff()
df.loc[df["roll"], "ret"] = np.nan
```

- Contract months (checked): Si, RI and GD list quarterly contracts (H, M, U, Z). BR lists monthly ones.
- FUTOI is per underlying asset, so it needs no stitching.

---

## 7. Resume, refresh, runtime

- **Unit of work:** one raw chunk per (dataset, ticker/contract, interval, month).
- **Skip rule:** a chunk whose file exists **and** whose month has fully ended is skipped. The **current month is always re-downloaded**, and `overwrite: true` re-downloads everything.
- **Interrupted?** Re-run. An interruption during a write never leaves a corrupt chunk: files are written to `.tmp` and then renamed.
- **Failed chunks** (network errors after retries) are logged, listed in `processed/_failed.csv`, and retried on the next run. The rest of the run continues.
- **Request volume:** candles return 500 rows per request and Super Candles 1000. FUTOI takes one request per calendar day (the API caps responses at 1000 rows and ignores paging).
- **Runtime:**
  - Measured: one month of 1m candles for one share ≈ 40–50 requests. Sequential requests take ≈ 0.15–0.3 s each.
  - Estimated, not measured end to end: the default config for 2020–2024 is on the order of 40–50k requests, **a few hours**. 1m candles dominate; every other dataset takes minutes.
  - If you don't need 1m, drop it for a much faster run.
- **Rate limits:** not documented by MOEX. None were hit in testing (sequential ~5 req/s).

---

## 8. Errors and troubleshooting

| Symptom / message | Cause | Fix |
|---|---|---|
| `ConfigError: config.md errors: ...` | Invalid config | Fix the listed keys (section 4.3) |
| `ConfigError: ALGOPACK_API_KEY not found` | `.env` missing or wrong path | Check `paths.env_file` and the file content `ALGOPACK_API_KEY=...` |
| `HTTP 401 ... API key missing, invalid or expired` | Truncated, wrong or expired token | Copy the token again from the personal account |
| `'available only to subscribers' ... skipping this dataset` | Dataset not in your plan | Upgrade the plan, or set `plan: free` to avoid these requests |
| `Free users can't receive data for the last 14 days` | Free-plan FUTOI embargo | Set `plan: free` (clamps automatically) |
| `failed after N retries (HTTP 5xx / Timeout)` | Network or MOEX server problem | Re-run later. Chunks are listed in `_failed.csv`. |
| `CERTIFICATE_VERIFY_FAILED` | Russian Trusted CA not available | The notebook embeds it. For the module, keep `certs/russian_trusted_ca.pem` in the package. |
| Connection timeouts to `apim.moex.com` on Colab | Possibly blocked from non-Russian IPs (**not verified**) | Test with a tiny config first. Run locally if it's blocked. |
| Empty processed file / missing group | No data for those tickers or that period (e.g. before 2020 for Super Candles) | Check `_summary.csv` and dataset history (4.4) |
| `pagination does not advance` / `response cap` | The API changed its paging behaviour | Report it. The pipeline refuses to store possibly incomplete data. |

Raw API check (prints no secrets): `python tools/probe_algopack.py`

---

## 9. Tests and maintenance

```bash
pip install pytest
pytest              # 40 offline tests with a fake MOEX API (config, client, transforms, futures roll, end-to-end run + resume, notebook build)
pytest -m live      # 4 live tests, real API, key from .env: SBER/IMOEX/CNYRUB_TOM/Si, 2024-03-14..19, all datasets (~40 s)
```

Rules for changing the code:
1. Edit only `src/algopack_pipeline.py`.
2. Run `python tools/build_notebook.py` to regenerate `notebooks/algopack_pipeline.ipynb`. A test fails if the notebook is stale.
3. Run `pytest`, and also `pytest -m live` if API behaviour is touched.

Calendar reminder: **the Russian Trusted Sub CA in `certs/` expires 2027-03-06.** Download a fresh copy from `https://gu-st.ru/content/Other/doc/` (`russian_trusted_root_ca.cer`, `russian_trusted_sub_ca.cer`), save both as PEM in `certs/russian_trusted_ca.pem`, and rebuild the notebook.

---

## 10. Status: verified facts, limits, open questions

_As of 2026-09-15, paid ALGOPACK key._

### 10.1 Verified live
- **Access:** auth is the `Authorization: Bearer <token>` header against `https://apim.moex.com/iss/...json`. All datasets are open on the paid plan.
- **TLS:** `apim.moex.com` uses a certificate from the Russian Trusted CA, which isn't in Python's default bundle. The pipeline adds it.
- **API quirks handled by the pipeline:**
  - **FUTOI ignores paging.** A multi-day request silently returns only the latest 1000 rows, so it's fetched one day at a time.
  - **Futures Super Candles/HI2/Alerts need the contract code** (`SiU5`), not the asset (`si` returns nothing).
  - **Super Candles' `tradetime` is the end of the 5-min bar.** It's shifted to the bar start to align with candles.
  - **Dataset not in plan:** HTTP 200 with an HTML page ("available only to subscribers") instead of an error status. It's detected by content.
  - **Free-plan FUTOI embargo:** comes back as an `ERROR_MESSAGE` row. It's detected.
- **Free plan (tested earlier):** candles (~16 min delay), FUTOI up to today − 14 days. Super Candles, HI2 and Alerts are closed.
- **Default panel checks:** all 10 shares have full daily data for 2020–2024. USD/RUB spot (`USD000UTSTOM`) has no candles from 2024-06-14 (checked to 06-20), so `Si` futures are the USD proxy.
- **Test results:** 40 offline tests and 4 live tests pass. The live test confirms every dataset, schema and time zone, the Si roll on 2024-03-18, and a re-run with zero requests.

### 10.2 Decisions taken
- Intervals 1m/10m/1h/1d, native (no resampling). Super Candles stay 5-min.
- Parquet, tz-aware Moscow time, long format.
- Continuous futures by expiry-based roll, with `contract`/`roll` columns and no price adjustment. FUTOI per asset.
- `.env` on Drive next to `config.md`.
- Plain `requests` client instead of the `moexalgo` library. Its only extras are a Super Candles resampler and live streaming, neither needed now.
- `plan: free|paid` switch.

### 10.3 Not verified yet
- **Colab access:** whether `apim.moex.com` is reachable from Google Colab (non-Russian IPs). Start with the small test config (4.5).
- **Full-run time:** the real duration of the full 2020–2024 run (estimate: a few hours).
- **Split adjustment:** GMKN and VTBR show no split jumps in daily candles, which suggests adjusted history. Intraday candles and Super Candles are unchecked.
- **Rate limits:** not documented; none hit so far.
- **Delisted/renamed tickers:** the universe listing shows only current securities (e.g. `YNDX` → `YDEX`, whose data starts 2024-07-24).

### 10.4 Open questions (not blocking)
1. Resample Super Candles to 10m/1h/1d inside the pipeline, or downstream?
2. Back-adjust futures prices at rolls, or is the `roll` flag enough for return-based models?
3. Keep one file per group, or also produce one merged multivariate table per interval for modelling?
