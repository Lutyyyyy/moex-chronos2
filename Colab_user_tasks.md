# Colab User Tasks — FORTS ISS Probe

**Purpose.** Resolve every open ISS-side assumption blocking `_resolve_futures_chain(root, interval, date_from, date_till)` in `basic_cells.ipynb` (per `exp_plan.md` §5). All tasks below are ISS-only — no Chronos, no Drive prefetch, no edits to `basic_cells.ipynb`. Run from a Colab cell, capture raw responses, paste them under each task in the **Results** subsection.

**Roots covered:** `BR` (Brent, monthly), `Si` (USD/RUB, quarterly), `GD` (Gold, quarterly).
**Date range of interest:** `2021-01-01` → `2026-04-30`.
**Intervals of interest:** `15`, `60`, `24`.

---

## Task 0 — Sanity / setup

Confirm ISS is reachable from Colab anonymously.

```
GET https://iss.moex.com/iss/index.json
```

**Report back:**
- HTTP status.
- Top-level keys (especially `engines`, `markets`).
- Confirms base URL `https://iss.moex.com/iss/` is correct.

### Results
Url correct, status 200

{ "engines": { "metadata": { "id": {"type": "int32"}, "name": {"type": "string", "bytes": 45, "max_size": 0}, "title": {"type": "string", "bytes": 765, "max_size": 0} }, "columns": ["id", "name", "title"], "data": [ [1, "stock", "Фондовый рынок и рынок депозитов"], [2, "state", "Рынок ГЦБ (размещение)"], [3, "currency", "Валютный рынок"], [4, "futures", "Срочный рынок"], [5, "commodity", "Товарный рынок"], [6, "interventions", "Товарные интервенции"], [7, "offboard", "ОТС-система"], [9, "agro", "Агро"], [1012, "otc", "ОТС с ЦК"], [1282, "quotes", "Квоты"], [1326, "money", "Денежный рынок"] ] }, "markets": { "metadata": { "id": {"type": "int32"}, "trade_engine_id": {"type": "int32"}, "trade_engine_name": {"type": "string", "bytes": 45, "max_size": 0}, "trade_engine_title": {"type": "string", "bytes": 765, "max_size": 0}, "market_name": {"type": "string", "bytes": 45, "max_size": 0}, "market_title": {"type": "string", "bytes": 765, "max_size": 0}, "market_id": {"type": "int32"}, "marketplace": {"type": "string", "bytes": 48, "max_size": 0}, "is_otc": {"type": "int32"}, "has_history_files": {"type": "int32"}, "has_history_trades_files": {"type": "int32"}, "has_trades": {"type": "int32"}, "has_history": {"type": "int32"}, "has_candles": {"type": "int32"}, "has_orderbook": {"type": "int32"}, "has_tradingsession": {"type": "int32"}, "has_extra_yields": {"type": "int32"}, "has_delay": {"type": "int32"} },


---

## Task 1 — Contract enumeration

### 1A — Current snapshot (DONE — answered by `ass.json`)

`GET https://iss.moex.com/iss/engines/futures/markets/forts/securities.json` (saved as `ass.json`).

**Findings:**
- `?assetcode=...` is **silently ignored** by this endpoint — response contains AI92, AFRICA, AED, ALIBABA, …, far beyond any single root. Filtering must be done client-side on the `ASSETCODE` column.
- `securities.columns` = `["SECID", "BOARDID", "SHORTNAME", "SECNAME", "PREVSETTLEPRICE", "DECIMALS", "MINSTEP", "LASTTRADEDATE", "LASTDELDATE", "SECTYPE", "LATNAME", "ASSETCODE", "PREVOPENPOSITION", "LOTVOLUME", "INITIALMARGIN", "HIGHLIMIT", "LOWLIMIT", "STEPPRICE", "LASTSETTLEPRICE", "PREVPRICE", "IMTIME", "BUYSELLFEE", "SCALPERFEE", "NEGOTIATEDFEE", "EXERCISEFEE", "SETTLEPRICE_CLR"]`.
- Root identifier lives in **`ASSETCODE`**. Values for our roots: **Brent → `"BR"`**, **USD/RUB → `"Si"`**, **Gold → `"GOLD"`** (note: `"GOLD"`, not `"GD"` — `GD` is only the SECID prefix).
- BOARDID is `RFUD` for all FORTS futures.
- Currently listed contracts per root (all 2026–2027 expiries):
  - BR: `BRM6, BRN6, BRQ6, BRU6, BRV6, BRX6, BRZ6` — monthly cadence confirmed.
  - Si: `SiM6, SiU6, SiZ6, SiH7, SiM7, SiU7` — quarterly H/M/U/Z confirmed.
  - GD: `GDM6, GDU6, GDZ6, GDH7` — quarterly H/M/U/Z confirmed.
- SECID convention: `{root_prefix}{month_letter}{year_digit}`, year_digit = last digit of year. For 2021–2026 the digits 1–6 are unambiguous (no decade collision).
- No cursor block needed on this endpoint at current size (response is ~240 KB, comes whole). If you want to be safe, paginate with `start=0,1000,…` and check `securities.cursor`.

→ **No action needed for 1A.** Schema and current-snapshot enumeration are settled.

### 1B — Historical enumeration (THIS IS THE OPEN QUESTION)

The current snapshot doesn't include expired contracts. We need to enumerate every BR/Si/GD contract that traded in `2021-01-01 → 2026-04-30`.

**Confirmed (from the `fetch_future_SiH6_24_*.parquet` file): ISS returns per-contract historical candles by SECID directly**, including for contracts not in the current snapshot. So a guess-and-probe loop is sufficient — no need for the history endpoint.

Run this from a Colab cell:

```python
# Should take ~1 min total (rate-limit ≥0.25 s/req, ~144 requests).
import requests, time

roots = {
    "BR": "FGHJKMNQUVXZ",  # Brent: monthly, all 12 letters
    "Si": "HMUZ",           # USD/RUB: quarterly H/M/U/Z
    "GD": "HMUZ",           # Gold:    quarterly H/M/U/Z
}

hits = []
t0 = time.time()
for prefix, letters in roots.items():
    for year_digit in "123456":   # 2021..2026
        for L in letters:
            secid = f"{prefix}{L}{year_digit}"
            url = (f"https://iss.moex.com/iss/engines/futures/markets/forts/"
                   f"securities/{secid}/candles.json"
                   f"?from=2021-01-01&till=2026-04-30&interval=24")
            r = requests.get(url, timeout=15)
            try:
                data = r.json().get("candles", {}).get("data", [])
                n = len(data)
                first = data[0][-2] if n else None   # begin of first bar
                last  = data[-1][-2] if n else None  # begin of last bar
            except Exception as e:
                n, first, last = -1, None, str(e)
            hits.append((secid, r.status_code, n, first, last))
            time.sleep(0.3)
elapsed = time.time() - t0

print(f"elapsed: {elapsed:.1f}s, total: {len(hits)}")
for row in hits:
    print(row)
```

**Report back:**
- Total elapsed time.
- The full `hits` list — one row per SECID with `(secid, status, n_bars, first_begin, last_begin)`.
- Any 404s or 0-row returns (helps me see whether ISS uses a different letter convention historically, e.g. if BR was quarterly in 2021).

### Results
_(fill in 1B here — 1A is already settled)_

---

## Task 2 — Per-contract metadata

Pick **3 expired contracts** and **1 active contract** per root from Task 1B's list (e.g. for BR something like `BRF4, BRM4, BRZ4` + current front month `BRM6`).

For each chosen `SECID`:

```
GET https://iss.moex.com/iss/securities/{SECID}.json
GET https://iss.moex.com/iss/engines/futures/markets/forts/securities/{SECID}.json
```

**Field-name note (from `ass.json`):** ISS uses **`LASTTRADEDATE`** (last trade) and **`LASTDELDATE`** (delivery/expiry) on FORTS — not `MATDATE` / `LSTTRADE`. For some contracts they differ by 1 day (e.g. AFLT-6.26: LASTTRADEDATE=2026-06-18, LASTDELDATE=2026-06-19); for BR they're equal (BR-6.26: both 2026-06-01). The `description` block on `/iss/securities/{SECID}.json` may also expose `MATDATE` separately — that's what we want to confirm.

**Report back per contract:**
- Field names available in the `description` / `securities` / `marketdata` blocks.
- Values of: `LASTTRADEDATE`, `LASTDELDATE`, `MATDATE` (if in `description`), `PREVDATE`, `ASSETCODE`, `SHORTNAME`, `IMTIME`, `SETTLEDATE` (whichever exist; flag the ones that are null).
- Whether `LASTTRADEDATE == LASTDELDATE` for BR/Si/GD specifically (this decides whether my active-window rule uses one or the other).
- **Whether the endpoints still return data for expired contracts** — i.e. can I retrieve `BRM4` metadata in 2026? If 404, I need to rely purely on candle responses for boundary detection.

### Results
_(fill in)_

---

## Task 3 — Candle availability across the date range

For each root, pick **the front-month contract you found above** (just one per root, e.g. `BRZ4` for Brent) and pull candles at all three intervals:

```
GET https://iss.moex.com/iss/engines/futures/markets/forts/securities/{SECID}/candles.json
    ?from=2021-01-01&till=2026-04-30&interval={15|60|24}
```

**Report back per (root, interval):**
- Number of rows returned.
- First and last `begin` timestamp.
- 5-row head + 5-row tail.
- The `candles.cursor` block — `TOTAL`, `PAGESIZE`, `INDEX`. I need to know if ISS silently caps the response.

If pagination is required (likely on 15m): confirm the `start=` cursor by pulling page 2 and report row counts. Example:

```
GET …/candles.json?from=…&till=…&interval=15&start=500
```

### Results
_(fill in)_

---

## Task 4 — Roll-boundary spot check (validation gate)

Decides whether the "stitch returns, NaN at roll" rule is correct.

Take **one root** (Brent `BR` is easiest — monthly rolls give many boundaries). Pull **3 consecutive contracts** roughly spanning 3 months in 2024 (e.g. `BRJ4, BRK4, BRM4`) at daily interval:

```
GET https://iss.moex.com/iss/engines/futures/markets/forts/securities/{SECID}/candles.json
    ?from=2024-01-01&till=2024-08-31&interval=24
```

**Report back:**
- For each contract: first and last bar with non-zero volume.
- The overlap window between consecutive contracts (days both contracts traded).
- The close price of the *expiring* contract on its last day vs the close of the *next* contract on the same day → **size of the level jump I'll be NaN-ing in the return series.** Need at least one concrete number to know if jumps are typically 1–3% (fine) or 10%+ (would trigger the `|r| > 0.20` validation rule and indicate a stitch error).

### Results
_(fill in)_

---

## Task 5 — Front-month selection field

**Pre-evidence from `ass.json` (current snapshot, 2026-05-16):** Brent BR `PREVOPENPOSITION` by contract: BRM6 = **595,104**, BRN6 = 57,446, BRQ6 = 9,622, BRU6 = 4,542, BRV6 = 4,348 — ~10× drop per step out. OI clearly identifies the front contract. Si shows the same pattern (SiM6 = 10,114,852 vs SiU6 = 2,057,852 vs SiZ6 = 62,934). GD same (GDM6 = 438,678 vs GDU6 = 23,430).

So OI > volume as front-month signal is essentially confirmed for the live snapshot. The remaining question: **does the same hold on historical dates** (i.e. can I rely on `OPENPOSITION` from historical candles to pick the front contract on any past date)?

For Task 4's three contracts, on a date when all three were tradable simultaneously (e.g. `2024-04-15` if in range):

- From the candles response: `VOLUME` and `OPENPOSITION` (open interest) of each contract on that date.

**Report back:**
- The three pairs of (VOLUME, OPENPOSITION) on that date.
- Confirm OI shows the same ~10× front-vs-next ratio historically. If it doesn't (e.g. flat across contracts), I'll fall back to expiry-based windows.

### Results
_(fill in)_

---

## Combined batch — Tasks 3 + 4 + 5 (one Colab cell)

Single script that handles all three. ~20 requests, ~10 s total. Paste into a fresh Colab cell, run, save the entire `stdout` into `345_res.md`.

```python
import requests, time, json

ISS = "https://iss.moex.com/iss"
PAUSE = 0.3

def get_json(url, params=None):
    r = requests.get(url, params=params, timeout=30)
    time.sleep(PAUSE)
    try:
        return r.status_code, r.json()
    except Exception as e:
        return r.status_code, {"_error": str(e), "_text": r.text[:500]}

# Pick one moderately-aged contract per root for interval availability checks.
# Using 2024 vintage so we exercise the full intraday window without hitting
# the unknown 15m depth limit too hard.
probes_t3 = [
    ("BR", "BRM4"),   # Brent monthly, expired 2024-06
    ("Si", "SiM4"),   # Si quarterly, expired 2024-06
    ("GD", "GDM4"),   # Gold quarterly, expired 2024-06
]

# ============================================================
# TASK 3 — interval availability (15m / 60m / 1d) + pagination
# ============================================================
print("=" * 70)
print("TASK 3 — interval availability")
print("=" * 70)

for root, secid in probes_t3:
    for interval in (15, 60, 24):
        url = f"{ISS}/engines/futures/markets/forts/securities/{secid}/candles.json"
        params = {"from": "2021-01-01", "till": "2026-04-30", "interval": interval}
        status, j = get_json(url, params)
        block = j.get("candles", {})
        cols = block.get("columns", [])
        data = block.get("data", [])
        cursor = j.get("candles.cursor", {}).get("data", [])
        begin_i = cols.index("begin") if "begin" in cols else -1
        first = data[0][begin_i] if data and begin_i >= 0 else None
        last  = data[-1][begin_i] if data and begin_i >= 0 else None
        print(f"{secid:6s} interval={interval:>2} | status={status} | "
              f"rows={len(data):>5} | first={first} | last={last} | "
              f"cursor={cursor}")
    # Pagination probe on 15m specifically (cursor cap usually ~500)
    url = f"{ISS}/engines/futures/markets/forts/securities/{secid}/candles.json"
    params = {"from": "2021-01-01", "till": "2026-04-30",
              "interval": 15, "start": 500}
    status, j = get_json(url, params)
    block = j.get("candles", {})
    data = block.get("data", [])
    cursor = j.get("candles.cursor", {}).get("data", [])
    print(f"   {secid} interval=15 page2 (start=500) | rows={len(data)} | "
          f"cursor={cursor}")
    print()

# ============================================================
# TASK 4 — roll-boundary spot check on 3 consecutive BR contracts
# ============================================================
print("=" * 70)
print("TASK 4 — roll-boundary check, BRJ4 -> BRK4 -> BRM4 (daily)")
print("=" * 70)

contracts_t4 = ["BRJ4", "BRK4", "BRM4"]
candles = {}
cols_global = None

for secid in contracts_t4:
    url = f"{ISS}/engines/futures/markets/forts/securities/{secid}/candles.json"
    params = {"from": "2024-01-01", "till": "2024-08-31", "interval": 24}
    status, j = get_json(url, params)
    block = j.get("candles", {})
    cols = block.get("columns", [])
    rows = block.get("data", [])
    candles[secid] = {"cols": cols, "rows": rows}
    cols_global = cols
    print(f"{secid}: status={status} cols={cols} rows={len(rows)}")

ci = {c: i for i, c in enumerate(cols_global)}
print(f"\ncolumn index map: {ci}")
vol_i, close_i, begin_i = ci["volume"], ci["close"], ci["begin"]

def first_last_active(rows):
    active = [r for r in rows if (r[vol_i] or 0) > 0]
    return (active[0], active[-1]) if active else (None, None)

def close_on(secid, date_str):
    for r in candles[secid]["rows"]:
        if r[begin_i].startswith(date_str):
            return r[close_i]
    return None

def last_active_day(secid):
    rows = candles[secid]["rows"]
    active = [r for r in rows if (r[vol_i] or 0) > 0]
    return active[-1][begin_i][:10] if active else None

print("\nfirst & last active (volume>0) bars per contract:")
for secid in contracts_t4:
    fa, la = first_last_active(candles[secid]["rows"])
    if fa:
        print(f"  {secid}: first_active={fa[begin_i]} (close={fa[close_i]}, "
              f"vol={fa[vol_i]})  last_active={la[begin_i]} "
              f"(close={la[close_i]}, vol={la[vol_i]})")
    else:
        print(f"  {secid}: no active bars in window")

print("\nroll-boundary close jumps (old vs new on old's last active day):")
for old, new in [("BRJ4", "BRK4"), ("BRK4", "BRM4")]:
    boundary = last_active_day(old)
    if boundary is None:
        print(f"  {old}->{new}: no boundary found"); continue
    oc = close_on(old, boundary)
    nc = close_on(new, boundary)
    if oc and nc:
        jump = (nc - oc) / oc * 100
        print(f"  {old}->{new} on {boundary}: close({old})={oc}  "
              f"close({new})={nc}  jump={jump:+.2f}%")
    else:
        print(f"  {old}->{new} on {boundary}: old_close={oc} new_close={nc}")

# ============================================================
# TASK 5 — front-month signal (volume + history-endpoint OI)
# ============================================================
print("=" * 70)
print("TASK 5 — front-month signal on 2024-04-15")
print("=" * 70)

probe_date = "2024-04-15"

print("from candles endpoint (no OPENPOSITION in this schema):")
for secid in contracts_t4:
    hit = [r for r in candles[secid]["rows"]
           if r[begin_i].startswith(probe_date)]
    if hit:
        r = hit[0]
        print(f"  {secid}: volume={r[vol_i]}  close={r[close_i]}  "
              f"begin={r[begin_i]}")
    else:
        print(f"  {secid}: no bar on {probe_date}")

print("\nfrom /iss/history/.../securities/{SECID}.json (does it expose OI?):")
for secid in contracts_t4:
    url = f"{ISS}/history/engines/futures/markets/forts/securities/{secid}.json"
    params = {"from": probe_date, "till": probe_date}
    status, j = get_json(url, params)
    block = j.get("history", {})
    cols = block.get("columns", [])
    rows = block.get("data", [])
    print(f"  {secid}: status={status} rows={len(rows)} cols={cols}")
    if rows:
        rec = dict(zip(cols, rows[0]))
        keys = ["TRADEDATE", "CLOSE", "VOLUME", "OPENPOSITION",
                "OPENPOSITIONVALUE", "NUMTRADES"]
        snippet = {k: rec.get(k) for k in keys if k in rec}
        print(f"     -> {snippet}")

print("\nDONE")
```

### Results
_(paste full stdout here, or save as `345_res.md` and reference)_

---

## What NOT to do in this session
- No Chronos calls.
- No Drive prefetch — these probes are tiny.
- No edits to `basic_cells.ipynb`. That lands after this report.
