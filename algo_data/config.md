# Pipeline config (manifest)

The pipeline reads the **first `yaml` code block** in this file. Everything else is commentary.
Full reference is in [`docs/usage.md`](docs/usage.md). Available tickers and datasets are in [`docs/universe.md`](docs/universe.md).

- Relative paths resolve against **this file's folder**. The same file works locally (repo root) and on Colab (`MyDrive/algo_data/`).
- Changing tickers, period or datasets never invalidates the cache. Raw month chunks are reused, and processed files are rebuilt for the current config.

```yaml
plan: paid                    # paid | free (free: skips tradestats/orderstats/obstats/hi2/alerts, FUTOI up to today-14d)

paths:
  env_file: .env              # file with ALGOPACK_API_KEY=...
  output_root: data           # raw/ (month chunks cache), processed/ (results), meta/, universe/

period:
  start: 2020-01-01           # YYYY-MM-DD
  end: 2024-12-31             # YYYY-MM-DD or today

datasets: [candles, tradestats, orderstats, obstats, hi2, alerts, futoi]

candles:
  intervals: [1m, 10m, 1h, 1d]   # allowed: 1m, 10m, 1h, 1d

tickers:
  shares: [SBER, GAZP, LKOH, ROSN, NVTK, GMKN, TATN, MGNT, PLZL, CHMF]   # board TQBR
  indices: [IMOEX]                                                       # board SNDX (candles only)
  currency: [CNYRUB_TOM]                                                 # board CETS
  futures:                     # continuous series by 2-char contract prefix; FUTOI uses the same code
    - {code: Si}               # USD/RUB futures; USD000UTSTOM spot has no candles from 2024-06-14 (checked to 06-20) and is thin now
    - {code: BR}               # Brent, monthly contracts
    - {code: RI}               # RTS index
    - {code: GD}               # gold
    # optional per asset: months: HMUZ (allowed contract months), roll_days: 3 (overrides the default below)

futures:
  roll_days_before_expiry: 5   # front contract switches N calendar days before its last trade date

request:
  pause_sec: 0.05              # min pause between requests
  max_retries: 5               # on network errors / HTTP 429, 5xx
  timeout_sec: 60

overwrite: false               # true = re-download every month chunk (current month is always refreshed)
```

## Panel rationale (default)
- **Shares:** 10 liquid TQBR blue chips across banks, oil & gas, metals and retail. All have complete daily history for 2020-01-03..2024-12-30, checked on 2026-09-15.
- **IMOEX, CNYRUB_TOM** as market and FX covariates. **Si / BR / RI / GD** cover USD, oil, RTS and gold. They are also the most liquid FUTOI assets.
