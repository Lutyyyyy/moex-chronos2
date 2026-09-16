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

datasets: [candles]           # scoped to Phase B gate's needs (daily candles only); widen when a later phase needs more

candles:
  intervals: [1d]              # allowed: 1m, 10m, 1h, 1d — 1d only for the first pivot-phase pull

tickers:
  # 22-ticker stratified subsample of equity_universe.yaml (80 tickers, see data/universe/),
  # picked 2026-09-17 for the Phase B multivariate-vs-univariate gate: top-liquidity ticker(s)
  # per sector across sectors, not just top-N by turnover (avoids biasing the gate toward a
  # liquidity-correlated cluster). Sector map + rationale: docs/usage.md §6.
  # X5 and RAGR (retail, agriculture) were in the original 24-ticker pick but dropped after the
  # 2026-09-17 pull confirmed zero candle history anywhere in 2020-2024 — both are recent MOEX
  # redomiciliations (foreign listing -> MOEX) with real current liquidity but no history over
  # this backtest period. equity_universe.yaml's ranker only checks recent history (240+ days),
  # so it selected them without catching this. No replacement picked; retail/agriculture have
  # thinner representation as a result (retail: MGNT, LENT still present).
  shares: [GAZP, SMLT, SBER, ROSN, MTSS, LKOH, T, OZON, PLZL, VTBR, YDEX, VKCO, GMKN, MAGN, AFKS, MGNT, PHOR, AFLT, IRAO, FEES, MDMG, LENT]   # board TQBR
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

## Panel rationale

**2026-09-17 (current): Phase B gate, 22 tickers, candles/1d only.** Stratified sample across
11 sectors (oil_gas, metals, financials, tech, telecom, retail, transport, utilities,
chemicals, healthcare, realestate — holding/agriculture dropped, see below) drawn from
`equity_universe.yaml`'s 80-ticker ranked list — top-liquidity pick(s) per sector rather than
a flat top-N by turnover, so the multivariate-vs-univariate gate isn't tested only on the most
liquidity-correlated cluster. `datasets`/`candles.intervals` scoped to the cheapest slice
that Phase B/C need (daily candles only) — widen once a phase actually needs
tradestats/obstats/futoi or finer intervals. Originally 24 tickers; **X5 and RAGR dropped**
after the actual pull confirmed zero 2020-2024 candle history (recent MOEX redomiciliations —
see `tickers.shares` comment above and `current_state.md` session log for detail).

**Superseded (2026-09-15): original 10-ticker default.** SBER, GAZP, LKOH, ROSN, NVTK, GMKN,
TATN, MGNT, PLZL, CHMF — liquid TQBR blue chips across banks, oil & gas, metals and retail,
full multi-dataset/multi-interval scope. All had complete daily history for
2020-01-03..2024-12-30, checked on 2026-09-15. Predates the Phase B gate's need for a larger,
sector-diverse universe.

**IMOEX, CNYRUB_TOM** as market and FX covariates. **Si / BR / RI / GD** cover USD, oil, RTS and gold. They are also the most liquid FUTOI assets.
