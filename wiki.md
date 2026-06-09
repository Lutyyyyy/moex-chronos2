# Wiki — Open Questions

Working notes for design decisions. MVP-oriented: enough to test Chronos-2 multiseries with covariates, not yet a full trading system.

## 1. Ticker universe
Which group of MOEX tickers should we use?
- Size of the group (e.g., 10 / 30 / 100)?
- Sector mix (single sector vs. diversified)?
- Liquidity threshold (min ADV, min price)?

**Answer:** Start with **10–15 highly liquid blue chips** on the main board (TQBR), grouped by economic linkage so cross-series structure is meaningful for multivariate forecasting.

First universe:
- Oil / gas / exporters: `SBER` (financial proxy), `GAZP`, `LKOH`, `ROSN`, `NVTK`, `TATN`
- Metals / miners: `GMKN`, `PLZL`, `MAGN`, `NLMK`
- Market / index proxy: `MOEX`, `VTBR`

Liquidity filter: stable candles on 15m/60m, low missingness, meaningful volume. Avoid illiquid tickers at MVP stage. Scale to 30/100 only after the pipeline is validated.

---

## 2. History window
- How far back should the parser pull data?
- Hard cutoff date for train / eval / test split, or rolling / walk-forward scheme?

**Answer:** Pull as much as ISS provides reliably; experiment on recent rolling windows.

Suggested depth per interval:
- **15m:** 6–12 months
- **60m:** 1–2 years
- **1d:** 3–5 years (use rolling recent context — older regimes add noise)

Evaluation scheme: **walk-forward**, not a single hard split.
```
context window → forecast horizon → shift forward → repeat
```
Reserve a hard final test set only after the workflow stabilizes.

---

## 3. Covariates
Candidate covariates to consider:
- Volume, open interest
- FX rates (USD/RUB, EUR/RUB, CNY/RUB)
- Commodities (Brent, gold)
- Index returns (IMOEX, RTSI, sector indices)
- Calendar features (hour-of-day, day-of-week, month, holiday flags)
- Sector aggregates
- News / macro indicators

**Answer:** Start with a small, clean covariate set. MVP set:

1. Own volume / volume change
2. IMOEX returns
3. Sector index returns
4. USD/RUB returns
5. Brent returns (oil/exporter group)
6. Gold returns (`PLZL`)
7. Hour-of-day
8. Day-of-week

Optional later: open interest, RTSI, CNY/RUB, EUR/RUB, realized volatility, sector aggregates, dividend flags. News/macro indicators excluded from MVP — add as a separate layer.

**Leakage rule:** future-known covariates may include calendar features only. All market-derived covariates are past-known only.

**Open extension (deferred to Stage 5e):** evaluate adding **price-level** covariates for USD/RUB and Brent (and possibly Gold) alongside their returns. Rationale: Russian exporter margins are roughly linear in Brent *level*, and USD/RUB *level* is a regime proxy (sanctions / capital-flow); neither is recoverable from short-context returns alone. Encoding: `log(price)` and/or rolling-z over a long lookback (e.g. 252 bars) — **not** raw price (Chronos-2's per-series scaling centres-out raw level and mutes the signal). Past-known only.

---

## 4. Returns definition
Form of the target variable.

**Answer:** Log-returns, interval-based — `r_n = ln(P_n / P_{n-1})` computed on each interval's OHLC (15m / 60m / 1d). Use **close-to-close** returns first.

Later extensions:
- Relative return: `r_ticker − r_index_or_sector`
- Horizon return: sum of next H log-returns

---

## 5. Forecast horizon
How many steps ahead per interval?

**Answer:** Use small horizon grids per interval.

| Interval | Horizons (bars) | Equivalent |
|----------|-----------------|------------|
| 15m      | 1 / 2 / 4       | 15 / 30 / 60 min |
| 60m      | 1 / 2 / 4       | 1 / 2 / 4 hours |
| 1d       | 3 / 5 / 10      | 3 days / 1 week / 2 weeks |

**First priority:** 60m h=4, 15m h=4, 1d h=5. Avoid very long intraday horizons (e.g., 24×60m) at MVP.

---

## 6. Sliding-window evaluation
- Shift size between consecutive windows?
- Total number of evaluation windows?

**Answer:** Walk-forward windows.

Shift size:
- **15m:** shift by 4 bars
- **60m:** shift by 1–4 bars
- **1d:** shift by 1 day

Minimum useful evaluation size:
- **15m:** 200+ forecast windows
- **60m:** 150+ forecast windows
- **1d:** 50+ forecast windows

Context length:
- **15m:** 500–1500 bars
- **60m:** 300–1000 bars
- **1d:** 200–500 bars

Keep context recent to reduce regime noise.

---

## 7. Metrics
What to optimize / report?

**Answer:** Report both forecast metrics and trading-signal metrics.

**Forecast metrics:**
- MAE
- RMSE
- WQL / quantile loss
- Quantile coverage
- Correlation between predicted and actual returns

**Trading metrics:**
- Directional accuracy
- LONG / SHORT / HOLD count
- Average PnL per trade
- Total PnL
- Sharpe
- Max drawdown
- Winrate

**Baselines to compare against:**
- Zero-return forecast
- Last-return momentum
- Simple moving-average / momentum rule
- CatBoost baseline

**Primary success criterion:** Chronos-2 multivariate + covariates beats univariate Chronos-2 and naive baselines in walk-forward tests.

---

## 8. MOEX data source
- ISS API directly, or an intermediary (Finam, broker API, third-party)?
- Auth required?
- Rate limits / historical depth available?

**Answer:** Start with the **MOEX ISS API** directly. ISS exposes historical market and candlestick data; delayed public data is available without a real-time subscription and without auth.

Candles endpoint:
```
/iss/engines/stock/markets/shares/securities/{SECID}/candles.json
```
Intervals used: `15`, `60`, `24` (15m, 60m, 1d).

Why ISS first:
- No broker dependency
- No auth for delayed/historical public data
- Reproducible
- Sufficient for MVP

Consider broker / paid feeds later only if ISS depth, speed, or reliability becomes limiting.
