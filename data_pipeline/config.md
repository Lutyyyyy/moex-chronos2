# Pipeline config (manifest)

The pipeline reads the **first `yaml` code block** in this file. Everything else is commentary.
Full reference is in [`docs/usage.md`](docs/usage.md). Available tickers and datasets are in [`docs/universe.md`](docs/universe.md).

- Relative paths resolve against **this file's folder**. The same file works locally (repo root) and on Colab (`MyDrive/data_pipeline/`).
- Changing tickers, period or datasets never invalidates the cache. Raw month chunks are reused, and processed files are rebuilt for the current config.

```yaml
plan: paid                    # paid | free (free: skips tradestats/orderstats/obstats/hi2/alerts, FUTOI up to today-14d)

paths:
  env_file: .env              # file with ALGOPACK_API_KEY=...
  output_root: data           # raw/ (month chunks cache), processed/ (results), meta/, universe/

period:
  start: 2020-01-01           # YYYY-MM-DD
  end: today                  # YYYY-MM-DD or today -- widened 2026-09-18 from 2024-12-31 to
                               # fetch a fresh 2025+ holdout window for the UNAC ctx=100
                               # lead-lag anomaly (see FINDINGS.md, lead-lag confirmation).
                               # Additive only -- widening period never invalidates or
                               # truncates the already-cached/cited 2020-2024 data (only new
                               # month chunks past 2024-12 get fetched).

datasets: [candles]           # scoped to Phase B gate's needs (daily candles only); widen when a later phase needs more

candles:
  # Added 1h 2026-09-17 for a post-daily-screen 1h-frequency follow-on (user's original
  # intent, sized as affordable after the daily screen concluded). period below stays
  # at the full 2020-2024 range rather than
  # narrowing to the ~24mo window the 1h analysis actually needs: period is applied
  # globally across every interval (not per-interval), so narrowing it would silently
  # truncate the already-processed, already-cited 2020-2024 candles_1d/shares.parquet
  # that Phase B/C's results are built on. The notebook-side date_from/date_till configs
  # restrict Chronos to the shorter 1h analysis window instead.
  #
  # Added 10m 2026-09-17: five independent negative results at daily/1h resolution
  # plus a per-window clustering check on the multivariate basket-gate arm (p=0.22, no
  # hidden localized structure) closed off both "aggregate skill" and "hidden
  # non-pairwise structure" readings at those two resolutions. User's explicit next
  # step: push to 10-minute bars. Real added cost flagged before pulling: 10m needs
  # ~3 ISS pages/month per ticker (vs 1h's ~1), so this interval alone costs roughly 3x
  # the 1h pull's request volume (~2.5hr/~29k requests estimated). Same 80-ticker
  # universe and full 2020-2024 period as 1h (not narrowed) -- keeps this pull reusable
  # for a later Phase C/E-style screen at 10m without a second pull, and avoids the
  # `period`-truncation risk documented above.
  intervals: [1d, 1h, 10m]     # allowed: 1m, 10m, 1h, 1d

tickers:
  # Full 80-ticker equity_universe.yaml list (see data/universe/), expanded 2026-09-17 for
  # Phase C's lead-lag cross-correlation screen after Phase B's
  # 22-ticker multivariate-vs-univariate gate concluded with a clean negative result — Phase C
  # asks a different question (does ANY pair among many tickers show lead-lag structure) that
  # needs the widest reasonable universe, not the sector-stratified subsample Phase B used.
  # X5 and RAGR are known (from the Phase B pull) to have zero 2020-2024 candle history —
  # both recent MOEX redomiciliations; left in rather than pre-trimmed, same as before, so the
  # pipeline's own missing-ticker reporting is the audit trail, not a hand-maintained exclusion
  # list. Other tickers in this 80 may turn out to have similarly short history; check the pull
  # output before trusting the final ticker count.
  shares: [GAZP, SMLT, SBER, ROSN, MTSS, LKOH, T, OZON, NVTK, PLZL, VTBR, YDEX, VKCO, GMKN, MAGN, TATN, ALRS, X5, NLMK, AFKS, SNGS, CHMF, POSI, MGNT, SNGSP, TRNFP, PHOR, SIBN, AFLT, RUAL, SBERP, SVCB, SPBE, SGZH, MTLR, SELG, MOEX, UGLD, FLOT, HEAD, IRAO, TATNP, DOMRF, RNFT, RTKM, FEES, BSPB, MDMG, ASTR, SFIN, UPRO, CNRU, RAGR, HYDR, BANEP, ENPG, MTLRP, CBOM, WUSH, LENT, MSNG, PRMD, MRKC, FESH, EUTR, RASP, NMTP, MVID, IRKT, BELU, OZPH, RENI, UNAC, MSRS, PIKK, UWGN, VSMO, RTKMP, DELI, TORS]   # board TQBR
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

**2026-09-17 (current): post-Phase-C 1h follow-on, same 80 tickers, candles/1d + 1h.** Phase C
(daily lead-lag screen) concluded with a clean negative result — 20 discovery-shortlisted
pairs, 0/20 replicated out-of-sample.
User's original intent was 1h resolution from the start; sized as affordable (~similar
request count to the daily pull, since AlgoPack's cost is driven by month-chunks not bar
count) and added as a genuinely different follow-on test, not a Phase C retry. Same 80-ticker
universe and full 2020-2024 `period` (kept unchanged rather than narrowed, to avoid silently
truncating the already-processed daily parquet Phase B/C's results are built on — the
notebook-side configs restrict the 1h analysis to a shorter ~24-month window instead).

**Superseded (2026-09-17): Phase C lead-lag screen, full 80 tickers, candles/1d only.** All of
`equity_universe.yaml`'s ranked list — Phase C's discovery step needs the widest reasonable
universe to screen for pairwise lead-lag structure (up to 80×79/2 = 3160 pairs), unlike
Phase B's gate which deliberately used a smaller stratified sample. `datasets`/
`candles.intervals` unchanged (`[candles]`/`[1d]`) — daily closes are all the correlation
screen needs. X5 and RAGR are known to have zero 2020-2024 history from the Phase B pull;
other tickers in the 80 may also turn out short — check the pull's ticker count before
trusting it (same pattern as before, no pre-trimming).

**Superseded (2026-09-17): Phase B gate, 22 tickers.** Stratified sample across 11 sectors
(oil_gas, metals, financials, tech, telecom, retail, transport, utilities, chemicals,
healthcare, realestate — holding/agriculture dropped) drawn from `equity_universe.yaml`'s
80-ticker ranked list — top-liquidity pick(s) per sector rather than a flat top-N by
turnover, so the multivariate-vs-univariate gate wasn't tested only on the most
liquidity-correlated cluster. Originally 24 tickers; **X5 and RAGR dropped** after the
actual pull confirmed zero 2020-2024 candle history (recent MOEX redomiciliations). Result:
gate FAILED — this panel is no longer active
but kept as a documented step in the project's history.

**Superseded (2026-09-15): original 10-ticker default.** SBER, GAZP, LKOH, ROSN, NVTK, GMKN,
TATN, MGNT, PLZL, CHMF — liquid TQBR blue chips across banks, oil & gas, metals and retail,
full multi-dataset/multi-interval scope. All had complete daily history for
2020-01-03..2024-12-30, checked on 2026-09-15. Predates the Phase B gate's need for a larger,
sector-diverse universe.

**IMOEX, CNYRUB_TOM** as market and FX covariates. **Si / BR / RI / GD** cover USD, oil, RTS and gold. They are also the most liquid FUTOI assets.
