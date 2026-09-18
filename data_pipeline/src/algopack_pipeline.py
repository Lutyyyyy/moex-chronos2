# %% [markdown]
# # ALGOPACK → Parquet pipeline
# Fetches MOEX market data (candles + ALGOPACK datasets) for the panel defined in `config.md`
# and saves long-format Parquet files (`ticker, timestamp, features...`, tz-aware MSK timestamps).
#
# Cells: 1 imports & constants · 2 config · 3 HTTP client · 4 fetch & normalize · 5 futures contracts & roll ·
# 6 storage, build & run · 7 universe report.  Usage: `docs/usage.md`.

# %%
# === 1. Imports & constants ===
import calendar
import json
import logging
import os
import re
import ssl
import sys
import tempfile
import time
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import certifi
import pandas as pd
import requests
import yaml

APIM_URL = "https://apim.moex.com/iss"
TZ = "Europe/Moscow"
MSK = ZoneInfo(TZ)

# Public Russian Trusted Root + Sub CA: apim.moex.com's TLS chain, absent from certifi.
# The notebook build injects the PEM text here; as a module it is read from certs/russian_trusted_ca.pem.
RUSSIAN_TRUSTED_CA_PEM = None
CA_DOWNLOAD_URLS = ("https://gu-st.ru/content/Other/doc/russian_trusted_root_ca.cer",
                    "https://gu-st.ru/content/Other/doc/russian_trusted_sub_ca.cer")

# Ticker groups → ISS engine/market/board and ALGOPACK datashop market code.
MARKETS = {
    "shares":   {"engine": "stock",    "market": "shares", "board": "TQBR", "ds_market": "eq"},
    "indices":  {"engine": "stock",    "market": "index",  "board": "SNDX", "ds_market": None},
    "currency": {"engine": "currency", "market": "selt",   "board": "CETS", "ds_market": "fx"},
    "futures":  {"engine": "futures",  "market": "forts",  "board": "RFUD", "ds_market": "fo"},
}
INTERVALS = {"1m": 1, "10m": 10, "1h": 60, "1d": 24}  # ISS candle interval codes
# bar_minutes: dataset rows are bars whose tradetime is the bar END → timestamp is shifted to bar start.
DATASETS = {
    "candles":    {"markets": ("shares", "indices", "currency", "futures"), "paid_only": False},
    "tradestats": {"markets": ("shares", "currency", "futures"), "paid_only": True, "bar_minutes": 5},
    "orderstats": {"markets": ("shares", "currency"), "paid_only": True, "bar_minutes": 5},
    "obstats":    {"markets": ("shares", "currency", "futures"), "paid_only": True, "bar_minutes": 5},
    "hi2":        {"markets": ("shares", "currency", "futures"), "paid_only": True},
    "alerts":     {"markets": ("shares", "futures"), "paid_only": True},
    "futoi":      {"markets": ("futures",), "paid_only": False},
}
FREE_PLAN_FUTOI_EMBARGO_DAYS = 14
FUTOI_VALUES = ["pos", "pos_long", "pos_short", "pos_long_num", "pos_short_num"]
MONTH_CODES = "FGHJKMNQUVXZ"  # futures month codes Jan..Dec
STRING_COLS = {"ticker", "contract", "secid", "asset_code", "metric", "reference", "alert_type", "clgroup"}

log = logging.getLogger("algopack")
if not log.handlers:
    _h = logging.StreamHandler(sys.stdout)
    _h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%H:%M:%S"))
    log.addHandler(_h)
    log.setLevel(logging.INFO)
    log.propagate = False


class AlgopackError(RuntimeError):
    """API/transport error."""


class SubscriptionError(AlgopackError):
    """Dataset is not included in the current ALGOPACK plan."""


class ConfigError(ValueError):
    """Invalid config.md."""


def today_msk() -> date:
    return datetime.now(MSK).date()


# %%
# === 2. Config (config.md → Config) ===
@dataclass(frozen=True)
class FuturesSpec:
    code: str              # contract prefix, e.g. "Si" → SiH4, SiM4…; lower-cased it is also the FUTOI asset code
    months: str | None     # allowed contract month codes, e.g. "HMUZ"; None = every listed month
    roll_days: int         # switch to the next contract N calendar days before the last trade date


@dataclass
class Config:
    path: Path | None
    plan: str
    env_file: Path | None
    output_root: Path
    start: date
    end: date
    datasets: list
    intervals: list
    tickers: dict           # group → list[str], non-futures groups
    futures: list           # list[FuturesSpec]
    overwrite: bool = False
    pause_sec: float = 0.05
    max_retries: int = 5
    timeout_sec: float = 60.0

    def describe(self) -> str:
        fut = ", ".join(f"{f.code}({f.months or 'all'}, roll {f.roll_days}d)" for f in self.futures) or "-"
        lines = [f"plan={self.plan}  period={self.start}..{self.end}  overwrite={self.overwrite}",
                 f"output_root={self.output_root}",
                 f"datasets={self.datasets}  candle intervals={self.intervals}"]
        lines += [f"{g}: {', '.join(t)}" for g, t in self.tickers.items() if t]
        lines.append(f"futures (continuous): {fut}")
        return "\n".join(lines)


def _resolve_path(base: Path, value) -> Path | None:
    if value in (None, ""):
        return None
    p = Path(str(value)).expanduser()
    return p if p.is_absolute() else (base / p).resolve()


def _to_date(value, name: str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value.strip().lower() == "today":
        return today_msk()
    try:
        return date.fromisoformat(str(value).strip())
    except ValueError:
        raise ConfigError(f"{name}: expected YYYY-MM-DD or 'today', got {value!r}") from None


def parse_config(text: str, base_dir: Path, path: Path | None = None) -> Config:
    """Parse the first ```yaml block of config.md. Relative paths resolve against base_dir (config.md folder)."""
    m = re.search(r"^```ya?ml[^\n]*\n(.*?)^```", text, re.S | re.M)
    if not m:
        raise ConfigError("config.md: no ```yaml block found")
    raw = yaml.safe_load(m.group(1)) or {}
    errors = []

    plan = str(raw.get("plan", "paid")).lower()
    if plan not in ("paid", "free"):
        errors.append(f"plan: must be 'paid' or 'free', got {plan!r}")

    paths = raw.get("paths") or {}
    output_root = _resolve_path(base_dir, paths.get("output_root", "data"))
    env_file = _resolve_path(base_dir, paths.get("env_file", ".env"))

    period = raw.get("period") or {}
    start = end = None
    try:
        start = _to_date(period.get("start"), "period.start")
        end = _to_date(period.get("end", "today"), "period.end")
        if start > end:
            errors.append(f"period: start {start} is after end {end}")
    except ConfigError as e:
        errors.append(str(e))

    datasets = list(raw.get("datasets") or ["candles"])
    errors += [f"datasets: unknown {d!r} (allowed: {list(DATASETS)})" for d in datasets if d not in DATASETS]
    intervals = [str(i) for i in ((raw.get("candles") or {}).get("intervals") or ["1d"])]
    errors += [f"candles.intervals: unknown {i!r} (allowed: {list(INTERVALS)})" for i in intervals if i not in INTERVALS]

    tickers_raw = raw.get("tickers") or {}
    errors += [f"tickers: unknown group {g!r} (allowed: {list(MARKETS)})" for g in tickers_raw if g not in MARKETS]
    tickers = {g: [str(t).strip() for t in (tickers_raw.get(g) or [])] for g in MARKETS if g != "futures"}

    fut_defaults = raw.get("futures") or {}
    default_roll = int(fut_defaults.get("roll_days_before_expiry", 5))
    futures = []
    for item in tickers_raw.get("futures") or []:
        item = {"code": item} if isinstance(item, str) else dict(item)
        code = str(item.get("code", "")).strip()
        if not re.fullmatch(r"[A-Za-z0-9]{2}", code):
            errors.append(f"tickers.futures: code must be the 2-char contract prefix (e.g. Si, BR), got {code!r}")
            continue
        months = item.get("months")
        if months is not None and (not months or set(str(months)) - set(MONTH_CODES)):
            errors.append(f"tickers.futures[{code}].months: use month codes from {MONTH_CODES!r}, got {months!r}")
        futures.append(FuturesSpec(code, str(months) if months else None, int(item.get("roll_days", default_roll))))

    if not any(tickers.values()) and not futures:
        errors.append("tickers: no tickers configured")

    req = raw.get("request") or {}
    if errors:
        raise ConfigError("config.md errors:\n  - " + "\n  - ".join(errors))
    return Config(path=path, plan=plan, env_file=env_file, output_root=output_root, start=start, end=end,
                  datasets=datasets, intervals=intervals, tickers=tickers, futures=futures,
                  overwrite=bool(raw.get("overwrite", False)),
                  pause_sec=float(req.get("pause_sec", 0.05)), max_retries=int(req.get("max_retries", 5)),
                  timeout_sec=float(req.get("timeout_sec", 60)))


def load_config(path) -> Config:
    path = Path(path).expanduser().resolve()
    return parse_config(path.read_text(encoding="utf-8"), path.parent, path)


def load_token(env_file: Path | None) -> str:
    """ALGOPACK_API_KEY from env_file (KEY=VALUE lines), else from the process environment. Never logged."""
    if env_file and Path(env_file).exists():
        for line in Path(env_file).read_text(encoding="utf-8-sig").splitlines():
            m = re.match(r"\s*(?:export\s+)?ALGOPACK_API_KEY\s*=\s*(.*)$", line)
            if m and m.group(1).strip():
                return m.group(1).strip().strip('"').strip("'")
    token = os.environ.get("ALGOPACK_API_KEY", "").strip()
    if not token:
        raise ConfigError(f"ALGOPACK_API_KEY not found in {env_file} nor in the environment")
    return token


# %%
# === 3. HTTP client (auth, TLS, retries, error detection, pagination) ===
def ca_bundle_path() -> str:
    """certifi roots + Russian Trusted CA → temp PEM file usable as requests' `verify`."""
    pem = RUSSIAN_TRUSTED_CA_PEM
    if not pem:
        here = Path(globals().get("__file__", "_")).resolve().parent
        for cand in (here.parent / "certs" / "russian_trusted_ca.pem", Path.cwd() / "certs" / "russian_trusted_ca.pem"):
            if cand.exists():
                pem = cand.read_text()
                break
    if not pem:
        parts = []
        for url in CA_DOWNLOAD_URLS:
            b = requests.get(url, timeout=60).content
            parts.append(b.decode() if b.startswith(b"-----BEGIN") else ssl.DER_cert_to_PEM_cert(b))
        pem = "\n".join(parts)
    out = Path(tempfile.gettempdir()) / "algopack_ca_bundle.pem"
    with open(out, "w", newline="\n") as f:
        f.write(Path(certifi.where()).read_text() + "\n" + pem.replace("\r", ""))
    return str(out)


def _block(payload: dict, name: str) -> list[dict]:
    b = payload.get(name) or {}
    return [dict(zip(b.get("columns", []), row)) for row in b.get("data", [])]


class Client:
    RETRY_STATUS = (429, 500, 502, 503, 504)

    def __init__(self, token: str, pause_sec: float = 0.05, max_retries: int = 5, timeout_sec: float = 60,
                 session=None, backoff_sec: float = 1.0):
        self.session = session or requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {token}", "User-Agent": "moex-data-pipeline"})
        if session is None:
            self.session.verify = ca_bundle_path()
        self.pause_sec, self.max_retries, self.timeout_sec, self.backoff_sec = pause_sec, max_retries, timeout_sec, backoff_sec
        self.n_requests = 0
        self._last = 0.0

    @classmethod
    def from_config(cls, cfg: Config) -> "Client":
        return cls(load_token(cfg.env_file), cfg.pause_sec, cfg.max_retries, cfg.timeout_sec)

    def get_json(self, path: str, params: dict | None = None) -> dict:
        url = f"{APIM_URL}/{path.strip('/')}.json"
        last_err = None
        for attempt in range(self.max_retries + 1):
            if attempt:
                time.sleep(min(60.0, self.backoff_sec * 2 ** (attempt - 1)))
            wait = self.pause_sec - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            try:
                r = self.session.get(url, params=params or {}, timeout=self.timeout_sec)
            except (requests.ConnectionError, requests.Timeout) as e:
                last_err = f"{type(e).__name__}: {e}"
                continue
            finally:
                self._last = time.monotonic()
                self.n_requests += 1
            if r.status_code in self.RETRY_STATUS:
                last_err = f"HTTP {r.status_code}"
                continue
            if r.status_code in (401, 403):
                raise AlgopackError(f"HTTP {r.status_code} on {path}: API key missing, invalid or expired")
            ctype = r.headers.get("content-type", "")
            if "text/html" in ctype and b"available only to" in r.content:
                raise SubscriptionError(f"{path}: 'available only to subscribers' (dataset not in your plan)")
            if r.status_code != 200 or "json" not in ctype:
                raise AlgopackError(f"{path}: unexpected HTTP {r.status_code} {ctype}: {r.text[:200]!r}")
            return r.json()
        raise AlgopackError(f"{path}: failed after {self.max_retries} retries ({last_err})")

    def fetch_rows(self, path: str, params: dict, block: str, max_pages: int = 100_000) -> list[dict]:
        """All rows of an ISS block, paging with `start` until an empty page or the `<block>.cursor` total."""
        rows, start, prev_first = [], 0, None
        for _ in range(max_pages):
            payload = self.get_json(path, {**params, "start": start})
            b = payload.get(block) or {}
            cols, data = b.get("columns", []), b.get("data", [])
            if "ERROR_MESSAGE" in cols:
                raise AlgopackError(f"{path}: {data[0][0] if data else 'ERROR_MESSAGE'}")
            if not data:
                break
            if prev_first is not None and data[0] == prev_first:
                raise AlgopackError(f"{path}: pagination does not advance at start={start}")
            prev_first = data[0]
            rows.extend(dict(zip(cols, row)) for row in data)
            start += len(data)
            cursor = _block(payload, f"{block}.cursor")
            if cursor and cursor[0].get("INDEX", 0) + cursor[0].get("PAGESIZE", len(data)) >= cursor[0].get("TOTAL", 0):
                break
        return rows


# %%
# === 4. Fetch & normalize (raw rows → DataFrame with tz-aware `timestamp`) ===
def _numeric(df: pd.DataFrame) -> pd.DataFrame:
    for c in df.columns:
        if c not in STRING_COLS and df[c].dtype == object:
            conv = pd.to_numeric(df[c], errors="coerce")
            if conv.notna().sum() == df[c].notna().sum():
                df[c] = conv
    return df


def _msk(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series).dt.tz_localize(TZ)


def candles_path(group: str, secid: str) -> str:
    s = MARKETS[group]
    return f"engines/{s['engine']}/markets/{s['market']}/boards/{s['board']}/securities/{secid}/candles"


def normalize_candles(rows: list[dict]) -> pd.DataFrame:
    """timestamp = candle open time (ISS `begin`, MSK)."""
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df.insert(0, "timestamp", _msk(df["begin"]))
    return _numeric(df[["timestamp", "open", "high", "low", "close", "volume", "value"]].copy())


def normalize_datashop(rows: list[dict], dataset: str) -> pd.DataFrame:
    """Bar datasets: timestamp = bar start (tradetime - 5 min). hi2/alerts: timestamp = tradedate+tradetime as published."""
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df.columns = [c.lower() for c in df.columns]
    ts = _msk(df["tradedate"].astype(str) + " " + df["tradetime"].astype(str))
    bar = DATASETS[dataset].get("bar_minutes")
    df.insert(0, "timestamp", ts - pd.Timedelta(minutes=bar) if bar else ts)
    return _numeric(df.drop(columns=[c for c in ("tradedate", "tradetime", "systime") if c in df.columns]))


def normalize_futoi(rows: list[dict]) -> pd.DataFrame:
    """Long by client group (FIZ/YUR); timestamp = snapshot time."""
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df.columns = [c.lower() for c in df.columns]
    df.insert(0, "timestamp", _msk(df["tradedate"].astype(str) + " " + df["tradetime"].astype(str)))
    return _numeric(df[["timestamp", "clgroup", *FUTOI_VALUES]].copy())


def fetch_candles(client: Client, group: str, secid: str, interval: str, d_from: date, d_till: date) -> pd.DataFrame:
    params = {"from": d_from.isoformat(), "till": d_till.isoformat(), "interval": INTERVALS[interval]}
    return normalize_candles(client.fetch_rows(candles_path(group, secid), params, "candles"))


def fetch_datashop(client: Client, dataset: str, group: str, secid: str, d_from: date, d_till: date) -> pd.DataFrame:
    path = f"datashop/algopack/{MARKETS[group]['ds_market']}/{dataset}/{secid}"
    rows = client.fetch_rows(path, {"from": d_from.isoformat(), "till": d_till.isoformat()}, "data")
    return normalize_datashop(rows, dataset)


FUTOI_PAGE_CAP = 1000


def fetch_futoi(client: Client, code: str, d_from: date, d_till: date) -> pd.DataFrame:
    """FUTOI ignores `start`/`limit` and returns at most 1000 (latest) rows per request → one request per day (~400 rows)."""
    path = f"analyticalproducts/futoi/securities/{code.lower()}"
    rows, day = [], d_from
    while day <= min(d_till, today_msk()):
        b = client.get_json(path, {"from": day.isoformat(), "till": day.isoformat()}).get("futoi") or {}
        cols, data = b.get("columns", []), b.get("data", [])
        if "ERROR_MESSAGE" in cols:
            raise AlgopackError(f"{path} {day}: {data[0][0] if data else 'ERROR_MESSAGE'}")
        if len(data) >= FUTOI_PAGE_CAP:
            raise AlgopackError(f"{path} {day}: {len(data)} rows = response cap, data may be truncated")
        rows.extend(dict(zip(cols, row)) for row in data)
        day += timedelta(days=1)
    return normalize_futoi(rows)


# %%
# === 5. Futures: contract discovery + roll schedule (continuous series) ===
@dataclass(frozen=True)
class Contract:
    secid: str
    code: str
    first_trade: date
    last_trade: date


def resolve_contract(client: Client, secid: str, year: int, month: int) -> Contract | None:
    """Contract metadata via ISS securities/{secid}; None if not a FORTS contract expiring near year/month."""
    payload = client.get_json(f"securities/{secid}", {"iss.meta": "off", "iss.only": "description,boards"})
    desc = {r.get("name"): r.get("value") for r in _block(payload, "description")}
    boards = {r.get("boardid") for r in _block(payload, "boards")}
    last = desc.get("LSTTRADE") or desc.get("LSTDELDATE")
    if "RFUD" not in boards or not last:
        return None
    last_d = date.fromisoformat(str(last)[:10])
    if abs((last_d.year * 12 + last_d.month) - (year * 12 + month)) > 2:  # single year digit → other decade
        return None
    first = desc.get("FRSTTRADE")
    first_d = date.fromisoformat(str(first)[:10]) if first else last_d - timedelta(days=730)
    return Contract(secid, secid[:2], first_d, last_d)


def discover_contracts(client: Client, spec: FuturesSpec, start: date, end: date, root: Path) -> list[Contract]:
    """Contracts with prefix spec.code expiring in [start.year, end.year+1]. Past years cached under meta/contracts/."""
    found = []
    for year in range(start.year, end.year + 2):
        cache = root / "meta" / "contracts" / f"{spec.code}_{year}.json"
        if cache.exists() and year < today_msk().year:
            items = [Contract(c["secid"], c["code"], date.fromisoformat(c["first_trade"]), date.fromisoformat(c["last_trade"]))
                     for c in json.loads(cache.read_text())]
        else:
            items = []
            for i, m in enumerate(MONTH_CODES):
                c = resolve_contract(client, f"{spec.code}{m}{year % 10}", year, i + 1)
                if c:
                    items.append(c)
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps([{"secid": c.secid, "code": c.code, "first_trade": c.first_trade.isoformat(),
                                          "last_trade": c.last_trade.isoformat()} for c in items], indent=1))
        found += [c for c in items if spec.months is None or c.secid[2] in spec.months]
    return sorted(found, key=lambda c: c.last_trade)


def roll_schedule(contracts: list[Contract], roll_days: int, start: date, end: date) -> list[tuple]:
    """[(contract, active_from, active_till)] within [start, end]: each contract is front until
    last_trade - roll_days (inclusive); the next one takes over the following day."""
    out, prev_roll = [], None
    for c in sorted(contracts, key=lambda c: c.last_trade):
        roll = c.last_trade - timedelta(days=roll_days)
        lo = max(c.first_trade, prev_roll + timedelta(days=1) if prev_roll else c.first_trade, start)
        hi = min(roll, end)
        prev_roll = roll
        if lo <= hi:
            out.append((c, lo, hi))
    return out


# %%
# === 6. Storage, build & run ===
@dataclass(frozen=True)
class Task:
    dataset: str
    group: str
    symbol: str            # what is requested: secid, contract secid, or futoi code
    ticker: str            # value of `ticker` in outputs (futures → contract prefix)
    interval: str | None
    month: date            # first day of the month chunk
    contract: str | None = None

    @property
    def month_end(self) -> date:
        return self.month.replace(day=calendar.monthrange(self.month.year, self.month.month)[1])


def month_starts(lo: date, hi: date) -> list[date]:
    out, cur = [], lo.replace(day=1)
    while cur <= hi:
        out.append(cur)
        cur = (cur.replace(day=28) + timedelta(days=4)).replace(day=1)
    return out


def raw_path(root: Path, t: Task) -> Path:
    parts = [root, "raw", t.dataset, t.group, t.symbol] + ([t.interval] if t.interval else [])
    return Path(*map(str, parts)) / f"{t.month:%Y-%m}.parquet"


def processed_path(root: Path, dataset: str, interval: str | None, group: str) -> Path:
    return root / "processed" / (f"{dataset}_{interval}" if interval else dataset) / f"{group}.parquet"


def write_parquet(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    df.to_parquet(tmp, index=False)
    os.replace(tmp, path)


def effective_end(cfg: Config, dataset: str) -> date:
    end = min(cfg.end, today_msk())
    if dataset == "futoi" and cfg.plan == "free":
        end = min(end, today_msk() - timedelta(days=FREE_PLAN_FUTOI_EMBARGO_DAYS))
    return end


def plan_tasks(cfg: Config, windows: dict) -> list[Task]:
    tasks = []
    for ds in cfg.datasets:
        spec = DATASETS[ds]
        if spec["paid_only"] and cfg.plan == "free":
            log.warning(f"{ds}: skipped (plan: free; dataset needs a paid ALGOPACK subscription)")
            continue
        end = effective_end(cfg, ds)
        if cfg.start > end:
            continue
        intervals = cfg.intervals if ds == "candles" else [None]
        for group in spec["markets"]:
            for iv in intervals:
                if group != "futures":
                    for secid in cfg.tickers.get(group, []):
                        tasks += [Task(ds, group, secid, secid, iv, m) for m in month_starts(cfg.start, end)]
                elif ds == "futoi":
                    for f in cfg.futures:
                        tasks += [Task(ds, group, f.code, f.code, iv, m) for m in month_starts(cfg.start, end)]
                else:
                    for f in cfg.futures:
                        for c, lo, hi in windows.get(f.code, []):
                            tasks += [Task(ds, group, c.secid, f.code, iv, m, c.secid)
                                      for m in month_starts(lo, min(hi, end))]
    return tasks


def needs_fetch(cfg: Config, t: Task) -> bool:
    path = raw_path(cfg.output_root, t)
    return cfg.overwrite or not path.exists() or t.month_end >= today_msk()  # current month is always refreshed


def fetch_task(client: Client, t: Task) -> pd.DataFrame:
    if t.dataset == "candles":
        return fetch_candles(client, t.group, t.symbol, t.interval, t.month, t.month_end)
    if t.dataset == "futoi":
        return fetch_futoi(client, t.symbol, t.month, t.month_end)
    return fetch_datashop(client, t.dataset, t.group, t.symbol, t.month, t.month_end)


DIVIDENDS_URL = "https://raw.githubusercontent.com/WLM1ke/poptimizer/master/dump/dividends.json"

# Manually verified stock splits (not present in the poptimizer dividend dump, which covers
# cash dividends only). Add entries here as new splits are found; see docs/usage.md for the
# isolated-large-move detection method used to find candidates.
# ratio: 1 pre-split share -> `ratio` post-split shares. BELU: confirmed 8-for-1; date corrected
# 2026-09-17 to 2024-08-22 after a real-data spot-check found the previously recorded
# 2024-05-24 date has no price discontinuity at all (BELU trades smoothly 5848->5627 that
# week) -- the actual ~6.55x drop (4680 -> 714) is on 2024-08-22.
KNOWN_SPLITS = {
    "BELU": [{"date": date(2024, 8, 22), "ratio": 8.0}],
}


def fetch_dividends(cfg: Config, fetcher=None) -> pd.DataFrame:
    """Download (or load cached) per-ticker dividend history from poptimizer's community dump.
    Returns columns: ticker, ex_date, dividend. Cached under <output_root>/dividends.json.
    `fetcher(url) -> bytes` defaults to a plain `requests.get`; tests inject a fake to stay offline."""
    cache = cfg.output_root / "dividends.json"
    if not cache.exists():
        log.info(f"fetching dividend dump from {DIVIDENDS_URL}")
        fetcher = fetcher or (lambda url: requests.get(url, timeout=60).content)
        content = fetcher(DIVIDENDS_URL)
        cache.parent.mkdir(parents=True, exist_ok=True)
        tmp = cache.with_suffix(".tmp")
        tmp.write_bytes(content)
        os.replace(tmp, cache)
    raw = json.loads(cache.read_text())
    rows = [{"ticker": rec["uid"], "ex_date": pd.to_datetime(d["day"]).date(), "dividend": float(d["dividend"])}
            for rec in raw for d in rec["df"]]
    return pd.DataFrame(rows, columns=["ticker", "ex_date", "dividend"])


def compute_close_adj(close: pd.Series, timestamp: pd.Series, ticker: str, dividends: pd.DataFrame) -> pd.Series:
    """Backward-multiplicative adjusted close for one ticker's daily-sorted candle rows.
    For each dividend, prices strictly before the ex-date are scaled by (1 - div/close_prev),
    where close_prev is the last close on or before the trading day preceding ex_date. Splits
    from KNOWN_SPLITS are applied the same way with factor 1/ratio. Adjustments compose
    (oldest dividend/split applied last) so multiple corporate actions stack correctly."""
    close = close.astype(float)
    dates = timestamp.dt.date if hasattr(timestamp, "dt") else pd.Series([t.date() for t in timestamp], index=close.index)
    adj = pd.Series(1.0, index=close.index)

    events = []  # (ex_date, factor)
    for _, row in dividends[dividends["ticker"] == ticker].iterrows():
        prior = dates < row["ex_date"]
        if not prior.any():
            continue
        close_prev = close[prior].iloc[-1]
        if close_prev <= 0:
            continue
        factor = 1.0 - row["dividend"] / close_prev
        if factor <= 0:
            continue  # implausible (dividend >= price); skip rather than corrupt history
        events.append((row["ex_date"], factor))
    for split in KNOWN_SPLITS.get(ticker, []):
        events.append((split["date"], 1.0 / split["ratio"]))

    for ex_date, factor in events:
        adj[dates < ex_date] *= factor
    return close * adj


def finalize(df: pd.DataFrame, dataset: str, cfg: Config, windows: dict, group: str | None = None,
             dividends: pd.DataFrame | None = None) -> pd.DataFrame:
    """Raw chunks (already tagged with ticker/contract) → filtered, de-duplicated, pivoted, sorted table."""
    df = df.drop(columns=[c for c in ("secid", "asset_code") if c in df.columns])
    d = df["timestamp"].dt.date
    keep = (d >= cfg.start) & (d <= effective_end(cfg, dataset))
    if "contract" in df.columns:  # keep each contract only inside its roll window
        win = {c.secid: (lo, hi) for code_windows in windows.values() for c, lo, hi in code_windows}
        lo = df["contract"].map(lambda s: win.get(s, (date.max, date.min))[0])
        hi = df["contract"].map(lambda s: win.get(s, (date.max, date.min))[1])
        keep &= (d >= lo) & (d <= hi)
    df = df[keep].copy()
    keys =["ticker", "timestamp"] + (["contract"] if "contract" in df.columns else [])

    if dataset == "futoi":
        df = df.pivot_table(index=keys, columns="clgroup", values=FUTOI_VALUES, aggfunc="last")
        df.columns = [f"{v}_{g.lower()}" for v, g in df.columns]
        df = df.reset_index()
    elif dataset == "hi2":
        df = df.pivot_table(index=keys, columns="metric", values="value", aggfunc="last")
        df.columns.name = None
        df = df.reset_index()
    elif dataset != "alerts":  # alerts are events: several rows per timestamp are legitimate
        df = df.drop_duplicates(subset=keys, keep="last")

    df = df.sort_values(["ticker", "timestamp"]).reset_index(drop=True)
    if "contract" in df.columns:
        prev = df.groupby("ticker")["contract"].shift()
        df.insert(3, "roll", prev.notna() & (prev != df["contract"]))
        df = df[["ticker", "timestamp", "contract", "roll"] + [c for c in df.columns if c not in keys + ["roll"]]]
    else:
        df = df[["ticker", "timestamp"] + [c for c in df.columns if c not in keys]]
    df = _numeric(df.copy())

    if dataset == "candles" and group == "shares" and "close" in df.columns and dividends is not None:
        parts = [compute_close_adj(g["close"], g["timestamp"], t, dividends)
                 for t, g in df.groupby("ticker", sort=False)]
        df["close_adj"] = pd.concat(parts).sort_index() if parts else pd.Series(dtype=float)

    return df


def build_processed(cfg: Config, tasks: list[Task], windows: dict, dividends_fetcher=None) -> pd.DataFrame:
    groups: dict = {}
    for t in tasks:
        groups.setdefault((t.dataset, t.interval, t.group), []).append(t)
    dividends = (fetch_dividends(cfg, dividends_fetcher)
                 if ("candles", "shares") in {(ds, g) for ds, _, g in groups} else None)
    summary = []
    for (ds, iv, group), ts in groups.items():
        frames = []
        for t in ts:
            p = raw_path(cfg.output_root, t)
            if p.exists():
                part = pd.read_parquet(p)
                if not part.empty:
                    part.insert(0, "ticker", t.ticker)
                    if t.contract:
                        part.insert(1, "contract", t.contract)
                    frames.append(part)
        out = processed_path(cfg.output_root, ds, iv, group)
        if not frames:
            continue
        df = finalize(pd.concat(frames, ignore_index=True), ds, cfg, windows, group=group, dividends=dividends)
        write_parquet(df, out)
        summary.append({"dataset": ds, "interval": iv, "group": group, "rows": len(df),
                        "tickers": df["ticker"].nunique(), "ts_min": df["timestamp"].min(),
                        "ts_max": df["timestamp"].max(), "file": str(out)})
    result = pd.DataFrame(summary)
    if not result.empty:
        result.to_csv(cfg.output_root / "processed" / "_summary.csv", index=False)
    return result


def run(config, client: Client | None = None, datasets: list | None = None, build_only: bool = False,
        dividends_fetcher=None) -> pd.DataFrame:
    """Fetch missing/stale raw month chunks, then rebuild processed Parquet for the configured panel.
    Safe to re-run: completed months are skipped, so an interrupted run resumes where it stopped."""
    cfg = config if isinstance(config, Config) else load_config(config)
    if datasets:
        cfg = replace(cfg, datasets=[d for d in cfg.datasets if d in datasets])
    if client is None:
        client = Client.from_config(cfg)  # build_only still resolves futures contracts (cached for past years)
    log.info("config:\n" + cfg.describe())

    windows = {}
    if cfg.futures and any(d != "futoi" and "futures" in DATASETS[d]["markets"] for d in cfg.datasets):
        for f in cfg.futures:
            contracts = discover_contracts(client, f, cfg.start, cfg.end, cfg.output_root)
            windows[f.code] = roll_schedule(contracts, f.roll_days, cfg.start, cfg.end)
            log.info(f"futures {f.code}: " + ", ".join(f"{c.secid}[{lo}..{hi}]" for c, lo, hi in windows[f.code]))

    tasks = plan_tasks(cfg, windows)
    todo = [] if build_only else [t for t in tasks if needs_fetch(cfg, t)]
    log.info(f"{len(tasks)} month chunks planned, {len(tasks) - len(todo)} cached, {len(todo)} to fetch")

    failed, blocked = [], set()
    t0 = last_report = time.monotonic()
    for i, t in enumerate(todo, 1):
        if t.dataset in blocked:
            continue
        try:
            write_parquet(fetch_task(client, t), raw_path(cfg.output_root, t))
        except SubscriptionError as e:
            blocked.add(t.dataset)
            log.warning(f"{t.dataset}: {e}; skipping this dataset")
        except AlgopackError as e:
            failed.append({"dataset": t.dataset, "symbol": t.symbol, "interval": t.interval, "month": t.month, "error": str(e)})
            log.error(f"{t.dataset} {t.symbol} {t.interval or ''} {t.month:%Y-%m}: {e}")
        now = time.monotonic()
        if now - last_report > 30 or i == len(todo):
            eta = (now - t0) / i * (len(todo) - i)
            log.info(f"fetched {i}/{len(todo)} chunks, {client.n_requests} requests, "
                     f"elapsed {timedelta(seconds=int(now - t0))}, eta {timedelta(seconds=int(eta))}")
            last_report = now

    summary = build_processed(cfg, tasks, windows, dividends_fetcher=dividends_fetcher)
    if failed:
        path = cfg.output_root / "processed" / "_failed.csv"
        path.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(failed).to_csv(path, index=False)
        log.warning(f"{len(failed)} chunks failed → {path} (re-run to retry)")
    log.info(f"done: {len(summary)} processed files under {cfg.output_root / 'processed'}")
    return summary


# %%
# === 7. Universe report (what is available right now) ===
FUTURES_SECID_RE = re.compile(r"^([A-Za-z0-9]{2})[FGHJKMNQUVXZ]\d$")


def universe_report(config, client: Client | None = None, top_n: int = 30) -> dict:
    """Current board listings + today's turnover per group, futures assets by contract prefix, and FUTOI assets.
    Writes <output_root>/universe/*.parquet and universe.md; returns the DataFrames."""
    cfg = config if isinstance(config, Config) else load_config(config)
    client = client or Client.from_config(cfg)
    out_dir = cfg.output_root / "universe"
    out_dir.mkdir(parents=True, exist_ok=True)
    tables = {}
    for group, s in MARKETS.items():
        payload = client.get_json(f"engines/{s['engine']}/markets/{s['market']}/boards/{s['board']}/securities", {"iss.meta": "off"})
        sec, md = pd.DataFrame(_block(payload, "securities")), pd.DataFrame(_block(payload, "marketdata"))
        sec = sec[[c for c in ("SECID", "SHORTNAME", "SECNAME", "ISIN", "LOTSIZE", "LISTLEVEL", "ASSETCODE", "LASTTRADEDATE", "INSTRID") if c in sec]]
        md_cols = [c for c in ("SECID", "LAST", "VALTODAY", "VOLTODAY", "NUMTRADES") if c in md]
        df = sec.merge(md[md_cols], on="SECID", how="left") if len(md_cols) > 1 else sec
        df["datasets"] = ", ".join(d for d, spec in DATASETS.items() if group in spec["markets"])
        if group == "indices":  # SNDX "turnover" is dominated by repo indices → list alphabetically
            df = df.sort_values("SECID")
        else:  # CETS hides VALTODAY (null) → rank by NUMTRADES there
            key = "VALTODAY" if "VALTODAY" in df and df["VALTODAY"].notna().any() else "NUMTRADES"
            df = df.sort_values(key, ascending=False) if key in df else df
        tables[group] = df

    fut = tables["futures"].copy()
    fut["code"] = fut["SECID"].str.extract(FUTURES_SECID_RE, expand=False)
    fut = fut.dropna(subset=["code"]).sort_values("LASTTRADEDATE")
    tables["futures_assets"] = (fut.groupby("code")
                                .agg(asset=("ASSETCODE", "first"), contracts=("SECID", "count"), front=("SECID", "first"),
                                     front_last_trade=("LASTTRADEDATE", "first"), value_today=("VALTODAY", "sum"))
                                .reset_index().sort_values("value_today", ascending=False))

    futoi_assets = []
    for back in range(0, 8):
        day = today_msk() - timedelta(days=back)
        payload = client.get_json("analyticalproducts/futoi/securities", {"date": day.isoformat(), "latest": 1})
        futoi_assets = sorted({r.get("ticker") for r in _block(payload, "futoi") if r.get("ticker")})
        if futoi_assets:
            break
    tables["futoi_assets"] = pd.DataFrame({"code": futoi_assets})

    for name, df in tables.items():
        write_parquet(df, out_dir / f"{name}.parquet")
    (out_dir / "universe.md").write_text(universe_markdown(tables, top_n), encoding="utf-8")
    log.info(f"universe report → {out_dir}")
    return tables


def universe_markdown(tables: dict, top_n: int = 30) -> str:
    def md_table(df: pd.DataFrame) -> str:
        df = df.fillna("")
        rows = ["| " + " | ".join(map(str, df.columns)) + " |", "|" + "---|" * len(df.columns)]
        rows += ["| " + " | ".join(str(v) for v in r) + " |" for r in df.itertuples(index=False)]
        return "\n".join(rows)

    lines = [f"# MOEX universe snapshot ({datetime.now(MSK):%Y-%m-%d %H:%M} MSK)", "",
             "Generated by `universe_report()`. `VALTODAY` (RUB turnover) and `NUMTRADES` cover the current/last session only; "
             "currency is ranked by `NUMTRADES` (ISS does not publish `VALTODAY` for CETS), indices are listed alphabetically.", "",
             "| Group | Board | Securities | ALGOPACK datasets |", "|---|---|---|---|"]
    for g, s in MARKETS.items():
        lines.append(f"| {g} | {s['board']} | {len(tables[g])} | {', '.join(d for d, sp in DATASETS.items() if g in sp['markets'])} |")
    lines += ["", f"FUTOI assets ({len(tables['futoi_assets'])}): " + ", ".join(tables["futoi_assets"]["code"]), ""]
    for g in ("shares", "currency"):
        cols = [c for c in ("SECID", "SHORTNAME", "LISTLEVEL", "VALTODAY", "NUMTRADES") if c in tables[g]]
        lines += [f"## {g}: top {top_n} by activity", "", md_table(tables[g][cols].head(top_n)), ""]
    cols = [c for c in ("SECID", "SHORTNAME", "SECNAME") if c in tables["indices"]]
    lines += [f"## indices: all {len(tables['indices'])} (candles only)", "", md_table(tables["indices"][cols]), ""]
    lines += [f"## futures: top {top_n} contract prefixes by turnover (use `code` in config)", "",
              md_table(tables["futures_assets"].head(top_n)), ""]
    return "\n".join(lines)


def rank_equity_universe(tables: dict, client: Client, top_n: int = 80, min_history_days: int = 240,
                          max_missing_frac: float = 0.05, history_start: date | None = None,
                          history_end: date | None = None) -> pd.DataFrame:
    """Reproducible equity universe selection on top of `universe_report()`'s `shares` table.

    Filters non-equity instruments (ETFs/funds have INSTRID != 'EQIN'), then checks each
    remaining candidate's daily-candle history over [history_start, history_end] (default:
    the trailing `min_history_days` calendar days) for length and missingness, and ranks the
    survivors by today's turnover (VALTODAY). Returns **every** candidate with a `status`
    column ('selected' | excluded reason) and, for selected rows, a `rank` — this is the audit
    trail, not just the top_n survivors, so exclusions are traceable rather than silent.
    Writes nothing; caller decides what to persist (see `save_equity_universe`).
    """
    shares = tables["shares"].copy()
    history_end = history_end or today_msk()
    history_start = history_start or (history_end - timedelta(days=int(min_history_days * 1.6)))

    rows = []
    non_equity = shares[shares.get("INSTRID", pd.Series(dtype=str)) != "EQIN"] if "INSTRID" in shares else shares.iloc[0:0]
    for _, r in non_equity.iterrows():
        rows.append({"SECID": r["SECID"], "SHORTNAME": r.get("SHORTNAME"), "VALTODAY": r.get("VALTODAY"),
                      "status": f"excluded: non-equity (INSTRID={r.get('INSTRID')!r})", "history_days": None, "missing_frac": None})

    candidates = shares[shares.get("INSTRID") == "EQIN"] if "INSTRID" in shares else shares
    expected_bdays = max(len(pd.bdate_range(history_start, history_end)), 1)
    for _, r in candidates.iterrows():
        secid = r["SECID"]
        try:
            raw = client.fetch_rows(candles_path("shares", secid),
                                     {"from": history_start.isoformat(), "till": history_end.isoformat(), "interval": INTERVALS["1d"]},
                                     "candles")
            df = normalize_candles(raw)
        except AlgopackError as e:
            rows.append({"SECID": secid, "SHORTNAME": r.get("SHORTNAME"), "VALTODAY": r.get("VALTODAY"),
                         "status": f"excluded: fetch error ({e})", "history_days": None, "missing_frac": None})
            continue
        n_days = len(df)
        missing_frac = max(0.0, 1 - n_days / expected_bdays)
        if n_days < min_history_days:
            status = f"excluded: history_days={n_days} < min_history_days={min_history_days}"
        elif missing_frac > max_missing_frac:
            status = f"excluded: missing_frac={missing_frac:.3f} > max_missing_frac={max_missing_frac}"
        else:
            status = "selected"
        rows.append({"SECID": secid, "SHORTNAME": r.get("SHORTNAME"), "VALTODAY": r.get("VALTODAY"),
                     "status": status, "history_days": n_days, "missing_frac": round(missing_frac, 4)})

    out = pd.DataFrame(rows)
    out["rank"] = pd.NA
    sel = out["status"] == "selected"
    ranked = out[sel].sort_values("VALTODAY", ascending=False).head(top_n)
    out.loc[ranked.index, "rank"] = range(1, len(ranked) + 1)
    out.loc[sel & ~out.index.isin(ranked.index), "status"] = "excluded: below top_n cutoff"
    return out.sort_values(["rank", "VALTODAY"], ascending=[True, False], na_position="last").reset_index(drop=True)


def save_equity_universe(ranked: pd.DataFrame, out_dir: Path, meta: dict) -> Path:
    """Writes the audit trail (all candidates) to CSV and the selected tickers to a YAML block
    ready to paste into config.md's `tickers.shares:`. Returns the YAML file's path."""
    out_dir.mkdir(parents=True, exist_ok=True)
    ranked.to_csv(out_dir / "equity_universe_candidates.csv", index=False)
    selected = ranked[ranked["status"] == "selected"].sort_values("rank")["SECID"].tolist()
    yaml_path = out_dir / "equity_universe.yaml"
    payload = {**meta, "n_selected": len(selected), "tickers": selected}
    yaml_path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8")
    log.info(f"equity universe: {len(selected)} selected of {len(ranked)} candidates → {out_dir}")
    return yaml_path
