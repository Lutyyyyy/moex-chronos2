# Ticker universe: what is accessible

A live snapshot of the current listings can be generated with `universe_report(cfg)`, cell 9 of the notebook.

## Groups (paid ALGOPACK key, verified 2026-09-15)
| Config group | ISS board | Listed now | Datasets | Ticker to put in config |
|---|---|---|---|---|
| `shares` | TQBR | 506 | candles, tradestats, orderstats, obstats, hi2, alerts | SECID, e.g. `SBER` |
| `indices` | SNDX | 69 | candles | SECID, e.g. `IMOEX`, `MOEXOG`, `RGBI` |
| `currency` | CETS | 200 | candles, tradestats, orderstats, obstats, hi2 | SECID, e.g. `CNYRUB_TOM`, `GLDRUB_TOM` |
| `futures` | RFUD | 642 contracts / 180 prefixes | candles, tradestats, obstats, hi2, alerts (per contract, stitched); futoi (per asset) | 2-char prefix, e.g. `Si`, `BR`, `RI`, `GD`, `CR`, `MX` |

FUTOI covers 63 asset codes, listed in the snapshot (e.g. `Si, BR, RI, GD, CR, MX, Eu, NG, SV`…). Many single-stock futures are not included.

## History depth (checked)
- **Candles:** SBER 1m from 2011-12, daily from 2007. 1m data for IMOEX and CNYRUB_TOM exists on 2020-01-06. Futures contracts only cover their own life (about 1–2 years each); continuous stitching covers the full period.
- **Super Candles** (tradestats/orderstats/obstats): SBER has data on 2020-01-06 and none on 2019-06-03. The docs say "from 2020".
- **FUTOI:** `futoi.dates` reports 2020-01-03 → today.
- **Alerts:** data on 2024-02-01. The docs say "from 2024".
- **HI2:** SBER from 2020-01-03, 11 metrics per day (checked).

## Default panel (config.md) and why
| Group | Tickers | Reason |
|---|---|---|
| shares | SBER, GAZP, LKOH, ROSN, NVTK, GMKN, TATN, MGNT, PLZL, CHMF | Liquid blue chips across sectors. Full daily coverage for 2020-01-03..2024-12-30 (1249 days, GMKN 1245). No split-sized daily jumps: the max daily move is the real 2022-02-24 crash. |
| indices | IMOEX | Market factor |
| currency | CNYRUB_TOM | Most active FX pair now |
| futures | Si, BR, RI, GD | USD/RUB, Brent, RTS, gold. Top turnover prefixes and FUTOI assets. |

## Caveats
- **Board lists show only currently listed securities.** Delisted or renamed tickers don't appear (e.g. `YNDX` → `YDEX`: YDEX daily data starts 2024-07-24).
- **Trading halts:** MOEX shares didn't trade from 2022-02-28 to 2022-03-23, so expect a gap. Morning, evening and weekend sessions changed over the years, so the number of 1m bars per day varies.
- **Splits / adjustments:** GMKN (2024 split) and VTBR (2024 consolidation) show no split-sized jumps in ISS daily candles. That suggests adjusted history, but I haven't checked it against a source that states it. Intraday candles and Super Candles are unchecked.
- **USD000UTSTOM:** no candles from 2024-06-14 (checked to 06-20). It trades thinly now. Use `Si` futures for USD.
- CETS doesn't publish `VALTODAY`, so the snapshot ranks currency by `NUMTRADES`.
