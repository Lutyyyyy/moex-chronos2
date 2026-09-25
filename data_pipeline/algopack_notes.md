# ALGOPACK — verified notes

_Pre-build check 2026-09-15. "✅ tested" = observed live from this machine; "📄 docs" = from the official OpenAPI spec / moexalgo source._

## Sources
- OpenAPI spec (most precise): https://raw.githubusercontent.com/moexalgo/moexalgo.github.io/main/static/openapi/openapi.yaml
- Docs source (the site is JS-rendered, so read the raw files): https://github.com/moexalgo/moexalgo.github.io/tree/main/docs (`description/*.md` = field lists, `method/*.md` = formulas)
- Python lib: `pip install moexalgo` (PyPI 2.4.1), auth `session.TOKEN = '<APIKEY>'`
- Token: https://data.moex.com/personal-account

## Access / auth
| Item | Value | Status |
|---|---|---|
| Auth | Header `Authorization: Bearer <APIKEY>` | 📄 docs |
| Base (with key) | `https://apim.moex.com/iss/...json` | 📄 docs, host ✅ online (401 without a valid key) |
| Base (no key) | `https://iss.moex.com/iss/...json` (15-min delayed, some fields cut) | ✅ tested |
| TLS apim | cert issuer **Russian Trusted Sub CA** (not in certifi), so a custom CA bundle is needed. Repo copy: `certs/russian_trusted_ca.pem` (Root valid to 2032-02-27, Sub to **2027-03-06**). Download source `gu-st.ru` timed out once, so use the repo copy. | ✅ tested |
| TLS iss | ZeroSSL, works with certifi | ✅ tested |
| Datashop on iss without key | `datashop/algopack/*` returns an HTML page, not data | ✅ tested |
| FUTOI on iss without key | returns data (**delayed 15 days**, per spec) | ✅ tested (348 rows Si, 2025-09-10) |

## Free-plan key: what it actually gives (✅ tested 2026-09-15, 2nd key)
| Endpoint group | Result with free key |
|---|---|
| Key accepted by gateway | ✅ yes (no 401; an invalid or missing key gets 401 JSON) |
| `datashop/algopack/*` (tradestats, orderstats, obstats, hi2, alerts), any date incl. 2020/2023/2025 | ❌ **HTTP 200 + HTML "The information is available only to subscribers"**. Not JSON, so a status-code check alone won't catch it. |
| FUTOI `analyticalproducts/futoi/...` | ✅ history from **2020-01-03** (`futoi.dates` block). ❌ **last 14 days blocked**, returned as a JSON row `ERROR_MESSAGE: "Invalid date. Free users can't receive data for the last 14 days (2026-09-01)."` Same for `latest=1`. |
| Candles (shares, index, FX, futures) via apim | ✅ work. **About 16 min delay** (15:07 MSK → last 1m candle 14:51 for SBER and SiU6). History as in `candleborders`. |
| Rate | 30 rapid sequential requests all returned 200 in 5.4 s (no throttling seen at that pace) |

Implication: on the free key only **candles + FUTOI (up to T-14d)** can be tested. Super Candles, HI2 and Alerts need the paid plan. Their code paths can be written against the OpenAPI spec but not run end-to-end.

## Paid key (✅ tested 2026-09-15, 3rd key)
- All `datashop/algopack/*` datasets return JSON. Blocks are `data`, `data.cursor` (`INDEX, TOTAL, PAGESIZE=1000`) and `data.dates`. Paging with `start` works (SBER Aug-2025: TOTAL 4785).
- Super Candles `tradetime` is the **bar end**: the first SBER bar of 2025-09-10 is `07:05`, and the first of 2020-01-06 is `10:05`. The pipeline shifts it to bar start.
- Super Candles depth: SBER has data on 2020-01-06 and none on 2019-06-03. HI2 SBER starts 2020-01-03 (11 metrics/day). Alerts (market-wide) have data on 2024-02-01.
- Field sets differ by market:
  - eq `obstats`: `spread_bbo, spread_lv10, spread_1mio, levels_b/s, vol_b/s, val_b/s, imbalance_*, vwap_*`
  - fx/fo `obstats`: `mid_price, micro_price, spread_l1..l10, vol_b_l1..l10, vwap_*`
  - fo `tradestats` adds `asset_code, im, oi_open/high/low/close`
  - fx `orderstats` has no `put_vol/put_val/...` totals
- **fo datashop needs the contract SECID:** `fo/tradestats/si` returns 0 rows, `fo/tradestats/SiU5` returns 174 rows. Expired contracts work too (SiH0 on 2020-02-10: 161 rows).
- **FUTOI ignores `start` and `limit`.** A multi-day range returns the *latest* 1000 rows (older days silently missing), so the pipeline requests **one calendar day at a time** (~350–404 rows/day, weekend sessions included).
- Market-wide FUTOI with `latest=1` lists 63 asset codes.
- Candles are real-time with the key (last 1m candle = the current minute).
- Expired futures contracts: `securities/<SECID>.json` → `description` (`ASSETCODE`, `FRSTTRADE`, `LSTTRADE`) and `boards` (RFUD). Note that ASSETCODE ≠ prefix: RI→`RTS`, GD→`GOLD`. Candles for expired contracts work, and `candleborders` covers only the contract's life.
- Contract months:
  - Si, RI, GD: quarterly H, M, U, Z (2020–2025).
  - BR: monthly; e.g. BRF4 last trade 2023-12-29.
- USD000UTSTOM: no daily candles 2024-06-14..20; thin trading in 2026.
- CETS marketdata: `VALTODAY` is null (use `NUMTRADES`).

## Pagination (✅ tested)
- Candles: 500 rows per page, `start=` offset.
- FUTOI: **1000 rows per page**, `start=` offset (Si for Aug-2025 had ≥ 2 full pages). Market-wide `futoi?date=` also returns 1000 per page (58 assets on the first page).
- ISS response errors come as a block with column `ERROR_MESSAGE`. Check for it.

## Endpoints (📄 OpenAPI)
Prefix `/iss/`, suffix `.json`. Market codes: `eq` = shares (TQBR), `fo` = futures (RFUD), `fx` = currency (CETS).

| Dataset | Market-wide (one date) | Per ticker (range) | Markets |
|---|---|---|---|
| tradestats (5m) | `datashop/algopack/{m}/tradestats?date=&latest=&limit≤1000` | `datashop/algopack/{m}/tradestats/{ticker}?from=&till=&latest=` | eq, fo, fx |
| orderstats (5m) | `.../{m}/orderstats` | `.../{m}/orderstats/{ticker}` | eq, fx (**no fo**) |
| obstats (5m) | `.../{m}/obstats` | `.../{m}/obstats/{ticker}` | eq, fo, fx |
| hi2 (daily) | `datashop/algopack/{m}/hi2` | `.../{m}/hi2/{ticker}?from=&till=` | eq, fo, fx |
| alerts | `datashop/algopack/{m}/alerts` | `.../{m}/alerts/{ticker}?from=&till=` | eq, fo |
| futoi (5m) | `analyticalproducts/futoi/securities?date=` | `analyticalproducts/futoi/securities/{asset}?from=&till=` (asset = `si`, `br`, `ri`…) | futures |
| candles | — | `engines/{engine}/markets/{market}/boards/{board}/securities/{SECID}/candles?from=&till=&interval=` | stock/shares/TQBR, futures/forts/RFUD, stock/index/SNDX, currency/selt/CETS |
| universe | `engines/.../boards/{board}/securities` | `.../securities/{SECID}` | same |
| calendars | `calendars/{stock,futures,currency}[/session]` | — | — |

Docs history depth: Super Candles and FUTOI and HI2 **from 2020**, Mega Alerts **from 2024**. Super Candles are published every 5 min, about 10–20 s after the interval closes.

## Key fields (📄 OpenAPI examples)
- **tradestats**: `tradedate, tradetime, secid, pr_open, pr_high, pr_low, pr_close, pr_std, vol, val, trades, pr_vwap, pr_change, trades_b, trades_s, val_b, val_s, vol_b, vol_s, disb, ...`. Full list is in `docs/description/supercandles.md`.
- **futoi**: `sess_id, seqnum, tradedate, tradetime, ticker, clgroup (FIZ/YUR), pos, pos_long, pos_short, pos_long_num, pos_short_num, systime, trade_session_date`
- **hi2**: `tradedate, tradetime, secid, metric, value, reference, SYSTIME`
- **alerts**: `tradedate, tradetime, secid, alert_type, threshold, value, reference, SYSTIME`
- **candles**: `open, close, high, low, value, volume, begin, end` (✅ tested)

## Candles (✅ tested on public ISS)
- Intervals: `1, 10, 60, 24, 7, 31, 4`. **No 5m, 15m or 30m** (they return 0 rows, verified via apim).
- Futures contracts (e.g. `SiU6`) have their own short `candleborders`: SiU6 starts 2024-09-18. A continuous series needs contract stitching.
- SBER 1m for 2012-01-10 returns data (500 rows on page 1).
- **Page size is 500 rows.** Paginate with `start=` offset.
- Time zone is **MSK, naive**. SBER 1m begins at 06:59 (morning session). Index/FX 1m/10m data starts around 09:50–09:59.
- Anonymous delay is about 14 min: at 14:34 MSK the last SBER 1m candle was 14:20.
- `candleborders` for SBER: 1m and 10m from 2011-12, 60m from 2011-11, daily from 2007-07.

## Universe (✅ public ISS, 2026-09-15)
| Board | Count | Example |
|---|---|---|
| TQBR shares | 506 | ABIO, AFLT, SBER… |
| SNDX indices | 69 | IMOEX, IMOEX2, MOEXOG… |
| CETS currency | 200 | CNYRUB_TOM, USD000UTSTOM… |
| RFUD futures | 642 contracts / 211 asset codes | Si, BR, RI, GD… |

Note: board lists include inactive/illiquid entries. A liquidity filter is still needed.

## Client library notes (moexalgo 2.4.1 source)
- With `session.TOKEN` set, base becomes `https://apim.moex.com/iss` and the Bearer header is added automatically.
- Pagination: `start` offset loop until an empty page. Per-call metric limit 10k default, 50k max.
- HTTP via `httpx`. On Colab it hits the same TLS CA issue.
