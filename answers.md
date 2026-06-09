

## 1. Ticker universe
Which group of MOEX tickers should we use?
- Size of the group (e.g., 10 / 30 / 100)?
- Sector mix (single sector vs. diversified)?
- Liquidity threshold (min ADV, min price)?

**Answer:** _TBD_

---

## 2. History window
- How far back should the parser pull data?
- Hard cutoff date for train / eval / test split, or rolling / walk-forward scheme?

**Answer:** _TBD_

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

**Answer:** _TBD_

---

## 4. Returns definition
Form of the target variable.

**Answer:** Log-returns, interval-based — r_n = ln(P_n / P_{n-1}) computed on each interval's OHLC (15m / 60m / 1d).

---

## 5. Forecast horizon
How many steps ahead per interval?
- 15-min: e.g., next 4 / 8 / 16 steps?
- 60-min: e.g., next 24 steps (1 day)?
- Daily: e.g., next 5 / 10 / 20 steps?

**Answer:** _TBD_

---

## 6. Sliding-window evaluation
- Shift size between consecutive windows?
- Total number of evaluation windows?

**Answer:** _TBD_

---

## 7. Metrics
What to optimize / report?
- MASE
- WQL / quantile loss
- Directional accuracy
- Sharpe / PnL of a toy strategy on top of forecasts

**Answer:** _TBD_

---

## 8. MOEX data source
- ISS API directly, or an intermediary (Finam, broker API, third-party)?
- Auth required?
- Rate limits / historical depth available?

**Answer:** _TBD_

I’ll fill this as practical wiki-ready decisions, keeping them MVP-oriented: enough to test Chronos-2 multiseries, not yet a full trading system.

Thought for 6s
Below is a concise wiki-ready version.

Wiki — Open Questions
1. Ticker universe
Answer: Start with 10–15 highly liquid tickers, not 30/100 yet.

Recommended first universe:

SBER, GAZP, LKOH, ROSN, NVTK,
TATN, GMKN, PLZL, MAGN, NLMK,
MOEX, VTBR
Use mostly blue chips, grouped by economic linkage:

oil/gas/exporters;

banks/financials;

metals/miners;

market/index proxy.

Avoid illiquid tickers at MVP stage. Liquidity filter: stable candles on 15m/60m, low missingness, meaningful volume. Prefer main board TQBR.

2. History window
Answer: Pull as much as ISS provides reliably, but start experiments with recent rolling windows.

Suggested:

15m: 6–12 months
60m: 1–2 years
1d: 3–5 years if available, but use rolling recent context
Evaluation should be walk-forward, not one hard split.

Example:

context window → forecast horizon → shift forward → repeat
Use hard final test only after workflow stabilizes.

3. Covariates
Answer: Start with a small, clean covariate set.

MVP covariates:

1. own volume / volume change
2. IMOEX returns
3. sector index returns
4. USD/RUB returns
5. Brent returns for oil/exporter group
6. gold returns for PLZL
7. hour-of-day
8. day-of-week
Optional later:

open interest, RTSI, CNY/RUB, EUR/RUB, volatility, sector aggregates, dividend flags
Exclude news/macro indicators for now. Add later as a separate layer.

Important: avoid leakage. Future-known covariates may include calendar features only; market covariates are past-known only.

4. Returns definition
Answer: Keep as stated.

Log-returns, interval-based:
r_n = ln(P_n / P_{n-1})
Use close-to-close returns first.

Later extensions:

relative return = ticker_return - index_or_sector_return
horizon return = sum of next H log-returns
5. Forecast horizon
Answer: Use small horizon grids per interval.

15m: 1 / 2 / 4 bars
     = 15 / 30 / 60 minutes

60m: 1 / 2 / 4 bars
     = 1 / 2 / 4 hours

1d: 3 / 5 / 10 bars
    = 3 days / 1 week / 2 weeks
First priority:

60m horizon 4
15m horizon 4
1d horizon 5
Do not start with very long intraday horizons like 24×60m.

6. Sliding-window evaluation
Answer: Use walk-forward windows.

Suggested shift:

15m: shift by 4 bars
60m: shift by 1–4 bars
1d: shift by 1 day
Minimum useful evaluation size:

15m: 200+ forecast windows
60m: 150+ forecast windows
1d: 50+ forecast windows
Context length:

15m: 500–1500 bars
60m: 300–1000 bars
1d: 200–500 bars
Keep context recent to reduce regime noise.

7. Metrics
Answer: Report both forecast metrics and trading-signal metrics.

Forecast metrics:

MAE
RMSE
WQL / quantile loss
quantile coverage
correlation between predicted and actual returns
Trading metrics:

directional accuracy
LONG/SHORT/HOLD count
average PnL per trade
total PnL
Sharpe
max drawdown
winrate
Always compare against baselines:

zero-return forecast
last-return momentum
simple moving-average/momentum rule
CatBoost baseline
Primary success criterion:

Chronos-2 multivariate + covariates beats univariate Chronos-2 and naive baselines in walk-forward tests.
8. MOEX data source
Answer: Start with MOEX ISS API directly.

MOEX ISS provides web API access to historical market data and candlestick chart data; delayed public data is available without real-time subscription. 

Use candles endpoint conceptually like:

/iss/engines/stock/markets/shares/securities/{SECID}/candles.json
with intervals such as:

15, 60, 24
Use direct ISS first because:

no broker dependency;

no auth for delayed/historical public data;

reproducible;

enough for MVP.

Later, consider broker/paid feeds only if ISS depth, speed, or reliability becomes limiting.



