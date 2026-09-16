# FORTS ISS Probes — merged record

Historical record of the ISS API probing that resolved `_resolve_futures_chain(root, interval, date_from, date_till)`
in `path_a/basic_cells.ipynb` §4b (FORTS chain resolver). Findings are already folded into
`docs/current_state.md` session entry 11 and `docs/exp_plan.md` §5 — this file is kept only as
raw supporting evidence, not a living doc.

Originally three files: `Colab_user_tasks.md` (task spec + Task 0/1 results), `1B_res.md`
(Task 1B raw output), `345_res.md` (Tasks 3–5 raw output). Merged here verbatim, in task order.

---

## Task spec + Task 0/1 results (from `Colab_user_tasks.md`)

**Purpose.** Resolve every open ISS-side assumption blocking `_resolve_futures_chain(root, interval, date_from, date_till)` in `basic_cells.ipynb` (per `exp_plan.md` §5). All tasks below are ISS-only — no Chronos, no Drive prefetch, no edits to `basic_cells.ipynb`. Run from a Colab cell, capture raw responses, paste them under each task.

**Roots covered:** `BR` (Brent, monthly), `Si` (USD/RUB, quarterly), `GD` (Gold, quarterly).
**Date range of interest:** `2021-01-01` → `2026-04-30`.
**Intervals of interest:** `15`, `60`, `24`.

### Task 0 — Sanity / setup

`GET https://iss.moex.com/iss/index.json` — confirms base URL and reachability.

**Result:** status 200. Top-level keys `engines`, `markets` present as expected; base URL confirmed correct.

### Task 1 — Contract enumeration

**1A — Current snapshot (from `ass.json`).**
`GET https://iss.moex.com/iss/engines/futures/markets/forts/securities.json`

Findings:
- `?assetcode=...` is **silently ignored** by this endpoint — filtering must be done client-side on the `ASSETCODE` column.
- `securities.columns` = `["SECID", "BOARDID", "SHORTNAME", "SECNAME", "PREVSETTLEPRICE", "DECIMALS", "MINSTEP", "LASTTRADEDATE", "LASTDELDATE", "SECTYPE", "LATNAME", "ASSETCODE", "PREVOPENPOSITION", "LOTVOLUME", "INITIALMARGIN", "HIGHLIMIT", "LOWLIMIT", "STEPPRICE", "LASTSETTLEPRICE", "PREVPRICE", "IMTIME", "BUYSELLFEE", "SCALPERFEE", "NEGOTIATEDFEE", "EXERCISEFEE", "SETTLEPRICE_CLR"]`.
- Root identifier lives in **`ASSETCODE`**. Values: **Brent → `"BR"`**, **USD/RUB → `"Si"`**, **Gold → `"GOLD"`** (note: `"GOLD"`, not `"GD"` — `GD` is only the SECID prefix).
- BOARDID is `RFUD` for all FORTS futures.
- Currently listed contracts (2026–2027 expiries): BR: `BRM6, BRN6, BRQ6, BRU6, BRV6, BRX6, BRZ6` (monthly cadence confirmed). Si: `SiM6, SiU6, SiZ6, SiH7, SiM7, SiU7` (quarterly H/M/U/Z). GD: `GDM6, GDU6, GDZ6, GDH7` (quarterly H/M/U/Z).
- SECID convention: `{root_prefix}{month_letter}{year_digit}`, year_digit = last digit of year. For 2021–2026 digits 1–6 are unambiguous (no decade collision).

**1B — Historical enumeration** (guess-and-probe loop over `{root}{letter}{year_digit}`, verified sufficient since ISS returns per-contract historical candles by SECID directly, including expired contracts). Script and raw output below.

---

## Task 1B raw output (from `1B_res.md`)

Guess-and-probe loop result: `(secid, status, n_bars, first_begin, last_begin)` per candidate SECID, `interval=24`, `2021-01-01..2026-04-30`. 120/120 hit — confirms the enumeration approach.

```
elapsed: 95.8s, total: 120
('BRF1', 200, 1, '2021-01-04 00:00:00', '2021-01-04 00:00:00')
('BRG1', 200, 20, '2021-01-04 00:00:00', '2021-02-01 00:00:00')
('BRH1', 200, 40, '2021-01-04 00:00:00', '2021-03-01 00:00:00')
('BRJ1', 200, 62, '2021-01-04 00:00:00', '2021-04-01 00:00:00')
('BRK1', 200, 84, '2021-01-04 00:00:00', '2021-05-04 00:00:00')
('BRM1', 200, 103, '2021-01-04 00:00:00', '2021-05-31 00:00:00')
('BRN1', 200, 124, '2021-01-04 00:00:00', '2021-07-01 00:00:00')
('BRQ1', 200, 139, '2021-01-04 00:00:00', '2021-08-02 00:00:00')
('BRU1', 200, 167, '2021-01-04 00:00:00', '2021-09-01 00:00:00')
('BRV1', 200, 185, '2021-01-04 00:00:00', '2021-10-01 00:00:00')
('BRX1', 200, 201, '2021-01-05 00:00:00', '2021-11-01 00:00:00')
('BRZ1', 200, 233, '2021-01-04 00:00:00', '2021-12-01 00:00:00')
('BRF2', 200, 236, '2021-01-04 00:00:00', '2022-01-03 00:00:00')
('BRG2', 200, 231, '2021-01-27 00:00:00', '2022-02-01 00:00:00')
('BRH2', 200, 248, '2021-02-22 00:00:00', '2022-02-28 00:00:00')
('BRJ2', 200, 231, '2021-03-26 00:00:00', '2022-04-01 00:00:00')
('BRK2', 200, 236, '2021-04-28 00:00:00', '2022-05-04 00:00:00')
('BRM2', 200, 248, '2021-05-27 00:00:00', '2022-06-01 00:00:00')
('BRN2', 200, 251, '2021-06-25 00:00:00', '2022-07-01 00:00:00')
('BRQ2', 200, 241, '2021-07-28 00:00:00', '2022-08-01 00:00:00')
('BRU2', 200, 247, '2021-09-01 00:00:00', '2022-09-01 00:00:00')
('BRV2', 200, 241, '2021-09-27 00:00:00', '2022-10-03 00:00:00')
('BRX2', 200, 245, '2021-10-27 00:00:00', '2022-11-01 00:00:00')
('BRZ2', 200, 255, '2021-11-26 00:00:00', '2022-12-01 00:00:00')
('BRF3', 200, 215, '2022-01-05 00:00:00', '2022-12-30 00:00:00')
('BRG3', 200, 214, '2022-01-26 00:00:00', '2023-02-01 00:00:00')
('BRH3', 200, 197, '2022-03-10 00:00:00', '2023-03-01 00:00:00')
('BRJ3', 200, 169, '2022-05-19 00:00:00', '2023-04-03 00:00:00')
('BRK3', 200, 203, '2022-04-27 00:00:00', '2023-05-02 00:00:00')
('BRM3', 200, 202, '2022-05-26 00:00:00', '2023-06-01 00:00:00')
('BRN3', 200, 227, '2022-06-29 00:00:00', '2023-07-03 00:00:00')
('BRQ3', 200, 205, '2022-07-26 00:00:00', '2023-08-01 00:00:00')
('BRU3', 200, 217, '2022-08-31 00:00:00', '2023-09-01 00:00:00')
('BRV3', 200, 192, '2022-10-03 00:00:00', '2023-10-02 00:00:00')
('BRX3', 200, 221, '2022-10-26 00:00:00', '2023-11-01 00:00:00')
('BRZ3', 200, 245, '2022-11-25 00:00:00', '2023-12-01 00:00:00')
('BRF4', 200, 234, '2022-12-30 00:00:00', '2023-12-29 00:00:00')
('BRG4', 200, 219, '2023-01-26 00:00:00', '2024-02-01 00:00:00')
('BRH4', 200, 232, '2023-03-01 00:00:00', '2024-03-01 00:00:00')
('BRJ4', 200, 218, '2023-04-03 00:00:00', '2024-04-01 00:00:00')
('BRK4', 200, 221, '2023-04-28 00:00:00', '2024-05-02 00:00:00')
('BRM4', 200, 242, '2023-05-30 00:00:00', '2024-06-03 00:00:00')
('BRN4', 200, 229, '2023-06-29 00:00:00', '2024-07-01 00:00:00')
('BRQ4', 200, 203, '2023-07-31 00:00:00', '2024-08-01 00:00:00')
('BRU4', 200, 230, '2023-09-06 00:00:00', '2024-09-02 00:00:00')
('BRV4', 200, 234, '2023-10-03 00:00:00', '2024-10-01 00:00:00')
('BRX4', 200, 233, '2023-11-01 00:00:00', '2024-11-01 00:00:00')
('BRZ4', 200, 222, '2023-12-06 00:00:00', '2024-12-02 00:00:00')
('BRF5', 200, 205, '2023-12-28 00:00:00', '2025-01-03 00:00:00')
('BRG5', 200, 214, '2024-01-31 00:00:00', '2025-02-03 00:00:00')
('BRH5', 200, 197, '2024-03-01 00:00:00', '2025-03-03 00:00:00')
('BRJ5', 200, 204, '2024-03-28 00:00:00', '2025-04-01 00:00:00')
('BRK5', 200, 201, '2024-05-02 00:00:00', '2025-05-02 00:00:00')
('BRM5', 200, 228, '2024-06-03 00:00:00', '2025-06-02 00:00:00')
('BRN5', 200, 222, '2024-06-28 00:00:00', '2025-07-01 00:00:00')
('BRQ5', 200, 215, '2024-08-01 00:00:00', '2025-08-01 00:00:00')
('BRU5', 200, 235, '2024-09-02 00:00:00', '2025-09-01 00:00:00')
('BRV5', 200, 238, '2024-10-02 00:00:00', '2025-10-01 00:00:00')
('BRX5', 200, 226, '2024-11-01 00:00:00', '2025-11-03 00:00:00')
('BRZ5', 200, 236, '2024-11-29 00:00:00', '2025-12-01 00:00:00')
('BRF6', 200, 236, '2025-01-03 00:00:00', '2026-01-05 00:00:00')
('BRG6', 200, 226, '2025-02-05 00:00:00', '2026-02-02 00:00:00')
('BRH6', 200, 237, '2025-02-25 00:00:00', '2026-03-02 00:00:00')
('BRJ6', 200, 241, '2025-03-26 00:00:00', '2026-04-01 00:00:00')
('BRK6', 200, 150, '2025-09-25 00:00:00', '2026-04-30 00:00:00')
('BRM6', 200, 123, '2025-10-30 00:00:00', '2026-04-30 00:00:00')
('BRN6', 200, 109, '2025-11-24 00:00:00', '2026-04-30 00:00:00')
('BRQ6', 200, 86, '2025-12-24 00:00:00', '2026-04-30 00:00:00')
('BRU6', 200, 67, '2026-01-27 00:00:00', '2026-04-30 00:00:00')
('BRV6', 200, 49, '2026-02-20 00:00:00', '2026-04-30 00:00:00')
('BRX6', 200, 28, '2026-03-24 00:00:00', '2026-04-30 00:00:00')
('BRZ6', 200, 5, '2026-04-24 00:00:00', '2026-04-30 00:00:00')
('SiH1', 200, 52, '2021-01-04 00:00:00', '2021-03-18 00:00:00')
('SiM1', 200, 116, '2021-01-04 00:00:00', '2021-06-17 00:00:00')
('SiU1', 200, 181, '2021-01-04 00:00:00', '2021-09-16 00:00:00')
('SiZ1', 200, 245, '2021-01-04 00:00:00', '2021-12-16 00:00:00')
('SiH2', 200, 306, '2021-01-04 00:00:00', '2022-03-17 00:00:00')
('SiM2', 200, 345, '2021-01-04 00:00:00', '2022-06-16 00:00:00')
('SiU2', 200, 406, '2021-01-04 00:00:00', '2022-09-15 00:00:00')
('SiZ2', 200, 486, '2021-01-04 00:00:00', '2022-12-15 00:00:00')
('SiH3', 200, 432, '2021-03-17 00:00:00', '2023-03-16 00:00:00')
('SiM3', 200, 457, '2021-06-14 00:00:00', '2023-06-15 00:00:00')
('SiU3', 200, 496, '2021-09-13 00:00:00', '2023-09-21 00:00:00')
('SiZ3', 200, 500, '2021-12-13 00:00:00', '2023-12-05 00:00:00')
('SiH4', 200, 447, '2022-05-18 00:00:00', '2024-03-21 00:00:00')
('SiM4', 200, 492, '2022-06-16 00:00:00', '2024-06-20 00:00:00')
('SiU4', 200, 490, '2022-09-13 00:00:00', '2024-09-19 00:00:00')
('SiZ4', 200, 487, '2022-12-19 00:00:00', '2024-12-19 00:00:00')
('SiH5', 200, 477, '2023-03-16 00:00:00', '2025-03-20 00:00:00')
('SiM5', 200, 476, '2023-06-21 00:00:00', '2025-06-19 00:00:00')
('SiU5', 200, 495, '2023-09-21 00:00:00', '2025-09-18 00:00:00')
('SiZ5', 200, 450, '2024-01-03 00:00:00', '2025-12-18 00:00:00')
('SiH6', 200, 440, '2024-03-15 00:00:00', '2026-03-19 00:00:00')
('SiM6', 200, 418, '2024-06-25 00:00:00', '2026-04-30 00:00:00')
('SiU6', 200, 380, '2024-09-18 00:00:00', '2026-04-30 00:00:00')
('SiZ6', 200, 322, '2024-12-17 00:00:00', '2026-04-30 00:00:00')
('GDH1', 200, 52, '2021-01-04 00:00:00', '2021-03-18 00:00:00')
('GDM1', 200, 116, '2021-01-04 00:00:00', '2021-06-17 00:00:00')
('GDU1', 200, 181, '2021-01-04 00:00:00', '2021-09-16 00:00:00')
('GDZ1', 200, 245, '2021-01-04 00:00:00', '2021-12-16 00:00:00')
('GDH2', 200, 252, '2021-03-09 00:00:00', '2022-03-17 00:00:00')
('GDM2', 200, 251, '2021-06-08 00:00:00', '2022-06-16 00:00:00')
('GDU2', 200, 244, '2021-09-09 00:00:00', '2022-09-16 00:00:00')
('GDZ2', 200, 256, '2021-12-03 00:00:00', '2022-12-16 00:00:00')
('GDH3', 200, 223, '2022-04-27 00:00:00', '2023-03-17 00:00:00')
('GDM3', 200, 255, '2022-06-09 00:00:00', '2023-06-16 00:00:00')
('GDU3', 200, 262, '2022-09-08 00:00:00', '2023-09-22 00:00:00')
('GDZ3', 200, 265, '2022-12-07 00:00:00', '2023-12-22 00:00:00')
('GDH4', 200, 267, '2023-03-02 00:00:00', '2024-03-22 00:00:00')
('GDM4', 200, 263, '2023-06-01 00:00:00', '2024-06-21 00:00:00')
('GDU4', 200, 256, '2023-09-21 00:00:00', '2024-09-20 00:00:00')
('GDZ4', 200, 263, '2023-12-11 00:00:00', '2024-12-20 00:00:00')
('GDH5', 200, 265, '2024-03-11 00:00:00', '2025-03-21 00:00:00')
('GDM5', 200, 259, '2024-06-17 00:00:00', '2025-06-20 00:00:00')
('GDU5', 200, 260, '2024-09-17 00:00:00', '2025-09-19 00:00:00')
('GDZ5', 200, 258, '2024-12-18 00:00:00', '2025-12-19 00:00:00')
('GDH6', 200, 261, '2025-03-11 00:00:00', '2026-03-20 00:00:00')
('GDM6', 200, 171, '2025-08-28 00:00:00', '2026-04-30 00:00:00')
('GDU6', 200, 158, '2025-09-16 00:00:00', '2026-04-30 00:00:00')
('GDZ6', 200, 94, '2025-12-15 00:00:00', '2026-04-30 00:00:00')
```

---

## Tasks 3–5 raw output (from `345_res.md`)

Combined batch probe: Task 3 (interval availability + pagination), Task 4 (roll-boundary spot check), Task 5 (front-month signal via volume/OI). This is what settled: ISS has **no 15-minute candle** for FORTS (led to the intraday stage moving 10m instead of 15m — see `docs/current_state.md` entry 12), roll-boundary jumps are small (≤5%, no stitch-error trigger), and open interest (`OPENPOSITION` from the history endpoint) confirms front-month selection historically (~10× drop per step out).

```
======================================================================
TASK 3 — interval availability
======================================================================
BRM4   interval=15 | status=200 | rows=    0 | first=None | last=None | cursor=[]
BRM4   interval=60 | status=200 | rows=  500 | first=2023-05-30 16:00:00 | last=2024-01-04 18:00:00 | cursor=[]
BRM4   interval=24 | status=200 | rows=  242 | first=2023-05-30 00:00:00 | last=2024-06-03 00:00:00 | cursor=[]
   BRM4 interval=15 page2 (start=500) | rows=0 | cursor=[]

SiM4   interval=15 | status=200 | rows=    0 | first=None | last=None | cursor=[]
SiM4   interval=60 | status=200 | rows=  500 | first=2022-06-16 18:00:00 | last=2022-12-28 11:00:00 | cursor=[]
SiM4   interval=24 | status=200 | rows=  492 | first=2022-06-16 00:00:00 | last=2024-06-20 00:00:00 | cursor=[]
   SiM4 interval=15 page2 (start=500) | rows=0 | cursor=[]

GDM4   interval=15 | status=200 | rows=    0 | first=None | last=None | cursor=[]
GDM4   interval=60 | status=200 | rows=  500 | first=2023-06-01 14:00:00 | last=2023-10-23 09:00:00 | cursor=[]
GDM4   interval=24 | status=200 | rows=  263 | first=2023-06-01 00:00:00 | last=2024-06-21 00:00:00 | cursor=[]
   GDM4 interval=15 page2 (start=500) | rows=0 | cursor=[]

======================================================================
TASK 4 — roll-boundary check, BRJ4 -> BRK4 -> BRM4 (daily)
======================================================================
BRJ4: status=200 cols=['open', 'close', 'high', 'low', 'value', 'volume', 'begin', 'end'] rows=62
BRK4: status=200 cols=['open', 'close', 'high', 'low', 'value', 'volume', 'begin', 'end'] rows=85
BRM4: status=200 cols=['open', 'close', 'high', 'low', 'value', 'volume', 'begin', 'end'] rows=106

column index map: {'open': 0, 'close': 1, 'high': 2, 'low': 3, 'value': 4, 'volume': 5, 'begin': 6, 'end': 7}

first & last active (volume>0) bars per contract:
  BRJ4: first_active=2024-01-03 00:00:00 (close=80.44, vol=358)  last_active=2024-04-01 00:00:00 (close=87.42, vol=31427)
  BRK4: first_active=2024-01-03 00:00:00 (close=81.6, vol=150)  last_active=2024-05-02 00:00:00 (close=87.89, vol=58390)
  BRM4: first_active=2024-01-03 00:00:00 (close=82.19, vol=36)  last_active=2024-06-03 00:00:00 (close=81.59, vol=64980)

roll-boundary close jumps (old vs new on old's last active day):
  BRJ4->BRK4 on 2024-04-01: close(BRJ4)=87.42  close(BRK4)=87.95  jump=+0.61%
  BRK4->BRM4 on 2024-05-02: close(BRK4)=87.89  close(BRM4)=83.66  jump=-4.81%
======================================================================
TASK 5 — front-month signal on 2024-04-15
======================================================================
from candles endpoint (no OPENPOSITION in this schema):
  BRJ4: no bar on 2024-04-15
  BRK4: volume=292469  close=89.64  begin=2024-04-15 00:00:00
  BRM4: volume=37332  close=89.19  begin=2024-04-15 00:00:00

from /iss/history/.../securities/{SECID}.json (does it expose OI?):
  BRJ4: status=200 rows=0 cols=['BOARDID', 'TRADEDATE', 'SECID', 'OPEN', 'LOW', 'HIGH', 'CLOSE', 'OPENPOSITIONVALUE', 'VALUE', 'VOLUME', 'OPENPOSITION', 'SETTLEPRICE', 'SWAPRATE', 'WAPRICE', 'CHANGE', 'QTY', 'NUMTRADES', 'SHORTNAME', 'ASSETCODE']
  BRK4: status=200 rows=1 cols=['BOARDID', 'TRADEDATE', 'SECID', 'OPEN', 'LOW', 'HIGH', 'CLOSE', 'OPENPOSITIONVALUE', 'VALUE', 'VOLUME', 'OPENPOSITION', 'SETTLEPRICE', 'SWAPRATE', 'WAPRICE', 'CHANGE', 'QTY', 'NUMTRADES', 'SHORTNAME', 'ASSETCODE']
     -> {'TRADEDATE': '2024-04-15', 'CLOSE': 89.64, 'VOLUME': 292469, 'OPENPOSITION': 246712, 'OPENPOSITIONVALUE': 20734199509.44, 'NUMTRADES': 75158}
  BRM4: status=200 rows=1 cols=['BOARDID', 'TRADEDATE', 'SECID', 'OPEN', 'LOW', 'HIGH', 'CLOSE', 'OPENPOSITIONVALUE', 'VALUE', 'VOLUME', 'OPENPOSITION', 'SETTLEPRICE', 'SWAPRATE', 'WAPRICE', 'CHANGE', 'QTY', 'NUMTRADES', 'SHORTNAME', 'ASSETCODE']
     -> {'TRADEDATE': '2024-04-15', 'CLOSE': 89.19, 'VOLUME': 37332, 'OPENPOSITION': 51092, 'OPENPOSITIONVALUE': 4272326834.84, 'NUMTRADES': 16670}

DONE
```
