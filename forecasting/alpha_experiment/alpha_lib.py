"""alpha_lib — Chronos-2 quantile forecasts -> alpha signals -> portfolios -> backtest -> statistics.

Pure pandas/numpy (+ scipy / statsmodels / arch). The Chronos pipeline is *injected* into
`generate_forecasts`, so everything here is testable without the model (see tests/).

Conventions used throughout (read these before changing anything):
  * Every wide DataFrame is indexed by trading DATE (tz-naive, normalized) x ticker.
  * `ret` = daily log return on the MAIN-SESSION close (last 10m bar starting <=18:50 MSK),
    dividend/split adjusted (close_adj). The 1d candle close is the *evening-session* last print
    and is deliberately never used (see README "Data").
  * A signal indexed at date d uses information up to and including the main close of d.
  * Forecast anchor d = last context day. Forecast step h refers to trading day d+h.
  * exec_lag L: a book decided at close d is traded at the main close of d+L and earns returns
    from d+L+1 on. The matching forecast/forward-return steps are h = L+1 .. L+5.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Callable, Iterable, Sequence

import numpy as np
import pandas as pd
from scipy import stats as sstats

NATIVE_QUANTILES: list[float] = [0.01, 0.05] + [round(0.1 + 0.05 * i, 2) for i in range(17)] + [0.95, 0.99]
HOLDOUT_START = pd.Timestamp("2025-01-01")
MAIN_FIRST_START = "09:50"   # opening auction bar
MAIN_LAST_START = "18:50"    # closing auction lives in the 18:40 bar; 18:50 bar exists on a few 2025 days
TRADING_DAYS = 252


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Data: main-session daily panel, calendar, realized variance
# ═══════════════════════════════════════════════════════════════════════════════

def load_long(path, tickers=None, columns=None, end=None) -> pd.DataFrame:
    """Read a data_pipeline long parquet; returns tz-naive MSK `timestamp`. `end` (inclusive date)
    is applied at read time so data after it never enters memory (holdout lock)."""
    filters = [("ticker", "in", list(tickers))] if tickers is not None else None
    df = pd.read_parquet(path, columns=columns, filters=filters)
    ts = df["timestamp"]
    if isinstance(ts.dtype, pd.DatetimeTZDtype):
        df["timestamp"] = ts.dt.tz_convert("Europe/Moscow").dt.tz_localize(None)
    if end is not None:
        df = df[df["timestamp"] < pd.Timestamp(end) + pd.Timedelta(days=1)]
    return df.reset_index(drop=True)


def main_session_bars(bars: pd.DataFrame) -> pd.DataFrame:
    """Keep only main-session bars (start in [09:50, 18:50]); adds `date`."""
    hm = bars["timestamp"].dt.strftime("%H:%M")
    out = bars[(hm >= MAIN_FIRST_START) & (hm <= MAIN_LAST_START)].copy()
    out["date"] = out["timestamp"].dt.normalize()
    return out


def trading_calendar(index_bars: pd.DataFrame, min_bars: int = 20) -> pd.DatetimeIndex:
    """Trading days = days on which the index (IMOEX 10m) printed at least `min_bars` main-session
    bars. Keeps the 2022-03-24..30 shortened sessions (~23 bars) and official working Saturdays
    (2021-02-20, 2024-04-27/11-02/12-28), which IMOEX computes; excludes holidays, the Feb-Mar
    2022 closure and the 2025+ weekend sessions (IMOEX is not computed on those)."""
    b = main_session_bars(index_bars)
    n = b.groupby("date").size()
    return pd.DatetimeIndex(sorted(n.index[(n >= min_bars).to_numpy()]))


def main_session_close(bars: pd.DataFrame, col: str = "close_adj") -> pd.DataFrame:
    """Wide date x ticker: `col` of the last main-session bar of each day."""
    b = main_session_bars(bars).sort_values("timestamp")
    last = b.groupby(["date", "ticker"])[col].last()
    return last.unstack("ticker").sort_index()


def main_session_value(bars: pd.DataFrame) -> pd.DataFrame:
    """Wide date x ticker: RUB traded value summed over the main session."""
    b = main_session_bars(bars)
    return b.groupby(["date", "ticker"])["value"].sum().unstack("ticker").sort_index()


def build_daily_panel(share_bars: pd.DataFrame, index_bars: pd.DataFrame, ffill_limit: int = 5) -> dict:
    """Returns dict(calendar, close, stale, ret, R, value, mkt_close, mkt_ret).
    Prices are reindexed onto the trading calendar; a missing print is forward-filled for at most
    `ffill_limit` days and flagged `stale` (a stale name is never eligible, but a held position
    correctly earns 0 then the catch-up return)."""
    cal = trading_calendar(index_bars)
    close_raw = main_session_close(share_bars).reindex(cal)
    # drop index-only days (2022-01-07: IMOEX printed, zero shares traded). Threshold 20% of the
    # usual print count keeps the 2022-03-24/25 partial reopening (~49% of names traded).
    n_print = close_raw.notna().sum(axis=1)
    usual = n_print.rolling(21, min_periods=1, center=True).median()
    cal = cal[(n_print >= 0.2 * usual).to_numpy()]
    close_raw = close_raw.reindex(cal)
    close = close_raw.ffill(limit=ffill_limit)
    stale = close_raw.isna() & close.notna()
    ret = np.log(close).diff()
    value = main_session_value(share_bars).reindex(cal)
    mkt = main_session_close(index_bars, col="close").reindex(cal).iloc[:, 0].rename("IMOEX")
    return dict(calendar=cal, close=close, stale=stale, ret=ret, R=np.expm1(ret), value=value,
                mkt_close=mkt, mkt_ret=np.log(mkt).diff())


def realized_variance(share_bars: pd.DataFrame, calendar: pd.DatetimeIndex, col: str = "close_adj") -> pd.DataFrame:
    """Daily realized variance of the main-session-close-to-main-session-close return:
    sum of squared 10m log returns over the main session, where the first bar of day d is
    differenced against the last main bar of the previous *calendar* trading day (so the
    overnight gap + evening session are one squared term). Adjusted prices -> no ex-div jumps."""
    b = main_session_bars(share_bars)
    b = b[b["date"].isin(calendar)].sort_values(["ticker", "timestamp"])
    r = np.log(b[col]).groupby(b["ticker"]).diff()
    rv = (r ** 2).groupby([b["date"], b["ticker"]]).sum(min_count=1)
    return rv.unstack("ticker").reindex(calendar)


def fetch_key_rate(cache_path, date_from="01.01.2020", date_to=None, refresh=False) -> pd.Series:
    """CBR key rate (percent p.a.), daily, from cbr.ru/hd_base/KeyRate (HTML table). Cached CSV."""
    cache_path = Path(cache_path)
    if cache_path.exists() and not refresh:
        s = pd.read_csv(cache_path, parse_dates=["date"]).set_index("date")["key_rate"]
        return s.sort_index()
    import re
    import requests
    date_to = date_to or pd.Timestamp.today().strftime("%d.%m.%Y")
    url = ("https://www.cbr.ru/hd_base/KeyRate/?UniDbQuery.Posted=True"
           f"&UniDbQuery.From={date_from}&UniDbQuery.To={date_to}")
    html = requests.get(url, timeout=30).text
    rows = re.findall(r"<td>(\d{2}\.\d{2}\.\d{4})</td>\s*<td>([\d,]+)</td>", html)
    if not rows:
        raise RuntimeError("CBR key-rate table not found (page layout changed?)")
    s = pd.Series({pd.to_datetime(d, format="%d.%m.%Y"): float(v.replace(",", ".")) for d, v in rows},
                  name="key_rate").sort_index()
    s.index.name = "date"
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    s.to_csv(cache_path)
    return s


def fetch_iss_index_daily(secid: str, date_from: str, date_till: str, cache_path, refresh=False) -> pd.Series:
    """Daily index close from MOEX ISS candles (same endpoint as lib.ipynb `_iss_candles`), cached CSV.
    Used for MCFTR (total-return benchmark)."""
    cache_path = Path(cache_path)
    if cache_path.exists() and not refresh:
        return pd.read_csv(cache_path, parse_dates=["date"]).set_index("date")[secid]
    import requests
    import time
    url = f"https://iss.moex.com/iss/engines/stock/markets/index/securities/{secid}/candles.json"
    rows, start = [], 0
    while True:
        r = requests.get(url, params={"from": date_from, "till": date_till, "interval": 24, "start": start}, timeout=30)
        r.raise_for_status()
        data = r.json()["candles"]
        if not data["data"]:
            break
        rows += data["data"]; start += len(data["data"])
        if len(data["data"]) < 500:
            break
        time.sleep(0.25)
    df = pd.DataFrame(rows, columns=data["columns"])
    s = pd.Series(df["close"].to_numpy(), index=pd.to_datetime(df["begin"]).dt.normalize(), name=secid)
    s.index.name = "date"
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    s.to_csv(cache_path)
    return s


def rf_daily(key_rate: pd.Series, calendar: pd.DatetimeIndex) -> pd.Series:
    """Daily simple risk-free return from the key rate (as-of the previous published value)."""
    kr = key_rate.reindex(key_rate.index.union(calendar)).ffill().reindex(calendar)
    return ((1 + kr / 100) ** (1 / TRADING_DAYS) - 1).rename("rf")


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Point-in-time universe
# ═══════════════════════════════════════════════════════════════════════════════

def pit_universe(ret: pd.DataFrame, value: pd.DataFrame, stale: pd.DataFrame, min_history: int = 250,
                 min_median_value: float = 0.0, value_window: int = 60) -> pd.DataFrame:
    """Boolean eligibility at date d, using data <= d only: >= min_history observed returns,
    trailing median main-session value >= floor, and a fresh (non-stale) print on d."""
    hist = ret.notna().cumsum()
    liq = value.rolling(value_window, min_periods=value_window // 2).median()
    elig = (hist >= min_history) & (liq >= min_median_value) & ~stale.reindex_like(ret).fillna(False)
    return elig.fillna(False).astype(bool)


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Chronos forecast generation (pipeline injected)
# ═══════════════════════════════════════════════════════════════════════════════

def forecast_contexts(ret: pd.DataFrame, eligible: pd.DataFrame, anchor, ctx: int,
                      covariates: dict[str, pd.DataFrame] | None = None, stride: int = 1,
                      tickers: list | None = None) -> tuple[list, list]:
    """Contexts for one anchor: for every eligible ticker, the last `ctx` observed returns up to
    and including the anchor date (NaN gaps dropped; positions are all the model uses).
    With `covariates` ({name: wide date x ticker frame}), each input is a Chronos-2 dict
    {"target", "past_covariates"} whose covariate values sit on exactly the same dates as the
    target context (missing covariate values -> 0). Past-only: nothing after the anchor is used."""
    if tickers is None:
        row = eligible.loc[anchor]
        tickers = list(row.index[row.to_numpy()])
    hist = ret.loc[:anchor]
    inputs, keep = [], []
    for t in tickers:
        s = hist[t].dropna()
        if stride > 1:                      # e.g. non-overlapping 5-day blocks ending at the anchor
            s = s.iloc[::-1].iloc[::stride].iloc[::-1]
        s = s.iloc[-ctx:]
        if len(s) < min(ctx, 32):
            continue
        x = s.to_numpy().astype(np.float32)
        if covariates:
            pc = {k: v[t].reindex(s.index).fillna(0.0).to_numpy().astype(np.float32) for k, v in covariates.items()}
            inputs.append({"target": x, "past_covariates": pc})
        else:
            inputs.append(x)
        keep.append(t)
    return keep, inputs


def generate_forecasts(pipeline, ret: pd.DataFrame, eligible: pd.DataFrame, anchors: Sequence,
                       ctx: int = 250, H: int = 6, quantiles: Sequence[float] = NATIVE_QUANTILES,
                       anchors_per_call: int = 4, out_path=None, checkpoint_every: int = 50,
                       holdout_unlock: bool = False, progress: bool = True,
                       covariates: dict[str, pd.DataFrame] | None = None, cross_learning: bool = False,
                       batch_size: int = 256, group_fn: Callable | None = None,
                       extra_series: pd.DataFrame | None = None, stride: int = 1) -> pd.DataFrame:
    """Long frame [anchor, ticker, h, q<level>...]. One `predict_quantiles` call covers
    `anchors_per_call` anchors x all their eligible tickers. Resumes from
    `<out_path>.partial.parquet` if present.
    cross_learning=True: every series in a call attends to every other (group attention), so a
    call must hold exactly ONE anchor (else earlier anchors would see later data) and the whole
    cross-section must fit one model batch (`batch_size` counts target + covariate series).
    group_fn(anchor, tickers) -> list of ticker lists: separate attention groups (one call each).
    extra_series: wide frame of non-traded series (indexes, futures) co-forecast inside every
    group for their information only; their forecasts are discarded.
    stride: context subsampling (with a pre-summed panel, stride=5 gives weekly blocks)."""
    anchors = pd.DatetimeIndex(anchors)
    if cross_learning and anchors_per_call != 1:
        raise ValueError("cross_learning requires anchors_per_call=1 (no cross-anchor attention / look-ahead)")
    if not holdout_unlock and len(anchors) and anchors.max() >= HOLDOUT_START:
        raise AssertionError(f"holdout locked: anchor {anchors.max().date()} >= {HOLDOUT_START.date()}")
    qcols = [f"q{q:g}" for q in quantiles]
    partial = Path(str(out_path) + ".partial.parquet") if out_path else None
    done_frames = []
    if partial is not None and partial.exists():
        prev = pd.read_parquet(partial)
        done_frames.append(prev)
        anchors = anchors[~anchors.isin(pd.DatetimeIndex(prev["anchor"].unique()))]
    chunks = [anchors[i:i + anchors_per_call] for i in range(0, len(anchors), anchors_per_call)]
    it = chunks
    if progress:
        try:
            from tqdm.auto import tqdm
            it = tqdm(chunks, desc="forecast chunks")
        except ImportError:
            pass
    new_frames = []
    for ci, chunk in enumerate(it):
        meta, inputs = [], []
        calls = []                                        # (meta, inputs, n_extra) per model call
        for a in chunk:
            tick, ctxs = forecast_contexts(ret, eligible, a, ctx, covariates, stride)
            if not tick:
                continue
            groups = group_fn(a, tick) if (group_fn is not None and cross_learning) else [tick]
            pos = {t: i for i, t in enumerate(tick)}
            for g in groups:
                g = [t for t in g if t in pos]
                if not g:
                    continue
                inp = [ctxs[pos[t]] for t in g]
                n_extra = 0
                if extra_series is not None:
                    if covariates:
                        raise ValueError("extra_series with covariates is not supported")
                    _, ex = forecast_contexts(extra_series, pd.DataFrame(True, index=[a], columns=extra_series.columns),
                                              a, ctx, None, stride)
                    inp += ex; n_extra = len(ex)
                calls.append(([(a, t) for t in g], inp, n_extra))
        if not calls:
            continue
        if not cross_learning:                            # independent series: merge into one call
            calls = [([m for c in calls for m in c[0]], [x for c in calls for x in c[1]], 0)]
        arrs = []
        for cm, inp, n_extra in calls:
            n_series = len(inp) * (1 + (len(covariates) if covariates else 0))
            if cross_learning and n_series > batch_size:
                raise ValueError(f"cross-section of {n_series} series exceeds batch_size={batch_size}: "
                                 "it would be split into separate attention groups")
            kw = dict(cross_learning=True, batch_size=batch_size) if cross_learning else {}
            qs, _ = pipeline.predict_quantiles(inp, prediction_length=H, quantile_levels=list(quantiles), **kw)
            qs = qs[:len(inp) - n_extra]                   # drop co-forecast extra series
            arrs.append(np.stack([(q.numpy() if hasattr(q, 'numpy') else np.asarray(q))[0] for q in qs]))
            meta += cm
        arr = np.concatenate(arrs)                         # (n, H, n_q)
        n = arr.shape[0]
        frame = pd.DataFrame(arr.reshape(n * H, len(quantiles)), columns=qcols)
        frame.insert(0, "h", np.tile(np.arange(1, H + 1), n))
        frame.insert(0, "ticker", np.repeat([m[1] for m in meta], H))
        frame.insert(0, "anchor", np.repeat(pd.DatetimeIndex([m[0] for m in meta]), H))
        new_frames.append(frame)
        if partial is not None and (ci + 1) % checkpoint_every == 0:
            pd.concat(done_frames + new_frames, ignore_index=True).to_parquet(partial)
    out = pd.concat(done_frames + new_frames, ignore_index=True) if (done_frames or new_frames) else pd.DataFrame()
    if out_path is not None and not out.empty:
        out.to_parquet(out_path)
        if partial is not None and partial.exists():
            partial.unlink()
    return out


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Quantile-function features
# ═══════════════════════════════════════════════════════════════════════════════

def rearrange_quantiles(preds: pd.DataFrame, quantiles: Sequence[float] = NATIVE_QUANTILES) -> tuple[pd.DataFrame, int]:
    """Monotone rearrangement (sort each row's quantiles; Chernozhukov et al. 2010). Chronos outputs
    rare, tiny crossings near the median. Returns (fixed frame, number of rows that crossed)."""
    qcols = [f"q{q:g}" for q in quantiles]
    Q = preds[qcols].to_numpy()
    n_bad = int((np.diff(Q, axis=1) < 0).any(axis=1).sum())
    out = preds.copy()
    out[qcols] = np.sort(Q, axis=1)
    return out, n_bad


def quantile_moments(Q: np.ndarray, u: Sequence[float], tail: str = "flat") -> tuple[np.ndarray, np.ndarray]:
    """Mean and variance of the distribution whose quantile function is piecewise linear through
    (u_k, Q[..., k]). Exact segment integrals: E = Σ Δu (a+b)/2, E[X²] = Σ Δu (a²+ab+b²)/3.
    Tails outside [u_1, u_K]: 'flat' holds the end quantile; 'linear' extends the end segment
    slope to u=0 and u=1."""
    Q = np.asarray(Q, dtype=float)
    u = np.asarray(u, dtype=float)
    if tail == "linear":
        lo = Q[..., :1] - (Q[..., 1:2] - Q[..., :1]) / (u[1] - u[0]) * u[0]
        hi = Q[..., -1:] + (Q[..., -1:] - Q[..., -2:-1]) / (u[-1] - u[-2]) * (1 - u[-1])
    elif tail == "flat":
        lo, hi = Q[..., :1], Q[..., -1:]
    else:
        raise ValueError(tail)
    QQ = np.concatenate([lo, Q, hi], axis=-1)
    uu = np.concatenate([[0.0], u, [1.0]])
    du = np.diff(uu)
    a, b = QQ[..., :-1], QQ[..., 1:]
    m1 = np.sum(du * (a + b) / 2, axis=-1)
    m2 = np.sum(du * (a * a + a * b + b * b) / 3, axis=-1)
    return m1, np.maximum(m2 - m1 ** 2, 0.0)


def chronos_features(preds: pd.DataFrame, steps: Sequence[int], quantiles: Sequence[float] = NATIVE_QUANTILES,
                     tail: str = "flat") -> pd.DataFrame:
    """Per (anchor, ticker): MED (Σ q50), MU (Σ mean), SIG (√Σ var; assumes ~zero serial
    correlation across steps), MED_SIG (MED/SIG), SKEW1 (quantile skew of the first step in
    `steps`), SIG1 (σ of the first step). `steps` = forecast steps h the holding period covers."""
    qcols = [f"q{q:g}" for q in quantiles]
    p = preds[preds["h"].isin(list(steps))]
    m, v = quantile_moments(p[qcols].to_numpy(), quantiles, tail=tail)
    p = p[["anchor", "ticker", "h", "q0.5", "q0.1", "q0.9"]].assign(mean=m, var=v)
    g = p.groupby(["anchor", "ticker"])
    out = pd.DataFrame({"MED": g["q0.5"].sum(), "MU": g["mean"].sum(), "SIG": np.sqrt(g["var"].sum())})
    first = p[p["h"] == min(steps)].set_index(["anchor", "ticker"])
    out["SIG1"] = np.sqrt(first["var"])
    width = (first["q0.9"] - first["q0.1"]).replace(0, np.nan)
    out["SKEW1"] = (first["q0.9"] + first["q0.1"] - 2 * first["q0.5"]) / width
    out["MED_SIG"] = out["MED"] / out["SIG"].replace(0, np.nan)
    return out


def chronos_features_block(preds: pd.DataFrame, steps: Sequence[int] = (), quantiles: Sequence[float] = NATIVE_QUANTILES,
                           tail: str = "flat") -> pd.DataFrame:
    """Features when h=1 IS the whole holding-period block (5-day-sum target): MED = q50,
    SIG = σ of that block directly (no Σvar assumption). `steps` is ignored (same block for both lags)."""
    qcols = [f"q{q:g}" for q in quantiles]
    p = preds[preds["h"] == 1].set_index(["anchor", "ticker"])
    m, v = quantile_moments(p[qcols].to_numpy(), quantiles, tail=tail)
    out = pd.DataFrame({"MED": p["q0.5"], "MU": m, "SIG": np.sqrt(v)}, index=p.index)
    out["SIG1"] = out["SIG"] / np.sqrt(5)
    width = (p["q0.9"] - p["q0.1"]).replace(0, np.nan)
    out["SKEW1"] = (p["q0.9"] + p["q0.1"] - 2 * p["q0.5"]) / width
    out["MED_SIG"] = out["MED"] / out["SIG"].replace(0, np.nan)
    return out


def chronos_features_cumulative(preds: pd.DataFrame, steps: Sequence[int], quantiles: Sequence[float] = NATIVE_QUANTILES,
                                tail: str = "flat") -> pd.DataFrame:
    """Features from CUMULATIVE-return quantiles C_h = log P_{d+h} - log P_d (log-price target).
    Over steps a..b: MED = q50(C_b) - q50(C_{a-1}); var = var(C_b) - var(C_{a-1}) (independent-
    increment approximation, floored); SIG1/SKEW1 from the first step's increment when a == 1."""
    qcols = [f"q{q:g}" for q in quantiles]
    a, b = min(steps), max(steps)
    P = preds.set_index(["anchor", "ticker", "h"])
    def at(h):
        x = P.xs(h, level="h")
        m, v = quantile_moments(x[qcols].to_numpy(), quantiles, tail=tail)
        return x["q0.5"], pd.Series(v, index=x.index), x
    med_b, var_b, xb = at(b)
    if a > 1:
        med_a, var_a, _ = at(a - 1)
    else:
        med_a, var_a = 0.0 * med_b, 0.0 * var_b
    out = pd.DataFrame({"MED": med_b - med_a, "SIG": np.sqrt(np.maximum(var_b - var_a, 1e-10))})
    m1, v1, x1 = at(1)
    out["MU"] = out["MED"]
    out["SIG1"] = np.sqrt(v1)
    width = (x1["q0.9"] - x1["q0.1"]).replace(0, np.nan)
    out["SKEW1"] = (x1["q0.9"] + x1["q0.1"] - 2 * x1["q0.5"]) / width
    out["MED_SIG"] = out["MED"] / out["SIG"].replace(0, np.nan)
    return out


def loo_residual(ret: pd.DataFrame) -> pd.DataFrame:
    """NaN-aware leave-one-out market residual: r_i - mean of the OTHER names with data that day."""
    n = ret.notna().sum(axis=1)
    tot = ret.sum(axis=1, min_count=1)
    others = (tot.to_numpy()[:, None] - ret) / (n.to_numpy()[:, None] - 1).clip(min=1)
    return (ret - others).where(ret.notna() & (n.to_numpy()[:, None] > 2))


def futures_main_returns(fut_bars: pd.DataFrame, calendar: pd.DatetimeIndex) -> pd.DataFrame:
    """Daily log returns of continuous futures on the main-session close, NaN when the contract
    changed between the two closes (roll) — never a cross-contract return."""
    b = main_session_bars(fut_bars).sort_values("timestamp")
    last = b.groupby(["date", "ticker"])[["close", "contract"]].last()
    close = last["close"].unstack("ticker").reindex(calendar)
    con = last["contract"].unstack("ticker").reindex(calendar)
    r = np.log(close).diff()
    return r.where(con.eq(con.shift(1)))


def to_wide(feat: pd.DataFrame, col: str, calendar: pd.DatetimeIndex | None = None) -> pd.DataFrame:
    w = feat[col].unstack("ticker")
    return w.reindex(calendar) if calendar is not None else w


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Classic signals (all known at close d)
# ═══════════════════════════════════════════════════════════════════════════════

def classic_signals(ret: pd.DataFrame, value: pd.DataFrame, steps: Sequence[int] = (2, 3, 4, 5, 6),
                    ar_window: int = 250) -> dict[str, pd.DataFrame]:
    """mom_12_1, rev_5d, rev_1d, lowvol_60d, ar1 (rolling AR(1) forecast of Σ_h r_{d+h}), size."""
    out = {
        "mom_12_1": ret.rolling(231, min_periods=200).sum().shift(21),
        "rev_5d": -ret.rolling(5, min_periods=5).sum(),
        "rev_1d": -ret,
        "lowvol_60d": -ret.rolling(60, min_periods=40).std(),
        "size": np.log(value.rolling(60, min_periods=30).median()),
    }
    lag = ret.shift(1)
    mu = ret.rolling(ar_window, min_periods=120).mean()
    cov = (ret * lag).rolling(ar_window, min_periods=120).mean() - mu * lag.rolling(ar_window, min_periods=120).mean()
    var = ret.rolling(ar_window, min_periods=120).var(ddof=0)
    phi = (cov / var).clip(-0.99, 0.99)
    dev = ret - mu
    out["ar1"] = sum(mu + phi ** h * dev for h in steps)
    return out


def forward_returns(ret: pd.DataFrame, steps: Sequence[int]) -> pd.DataFrame:
    """Σ_{h in steps} r_{d+h}, indexed at the signal date d (NaN if any step missing)."""
    return sum(ret.shift(-h) for h in steps)


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Volatility models: forecasts of Σ_{h in steps} variance, known at close d
# ═══════════════════════════════════════════════════════════════════════════════

def vol_trailing(ret: pd.DataFrame, n_steps: int, window: int = 20) -> pd.DataFrame:
    return ret.rolling(window, min_periods=window).var() * n_steps


def vol_ewma(ret: pd.DataFrame, n_steps: int, lam: float = 0.94, warmup: int = 20) -> pd.DataFrame:
    v = (ret ** 2).ewm(alpha=1 - lam, adjust=False, ignore_na=True).mean()
    v[ret.notna().cumsum() < warmup] = np.nan
    return v * n_steps


def _garch_filter(x: np.ndarray, mu, omega, alpha, beta, s2_0) -> np.ndarray:
    """Conditional variances σ²_j of x_j given x_<j (σ²_0 = s2_0)."""
    s2 = np.empty(len(x))
    s2[0] = s2_0
    for j in range(1, len(x)):
        s2[j] = omega + alpha * (x[j - 1] - mu) ** 2 + beta * s2[j - 1]
    return s2


def vol_garch(ret: pd.DataFrame, steps: Sequence[int], refit_every: int = 21, min_obs: int = 250,
              max_obs: int = 1000) -> pd.DataFrame:
    """GARCH(1,1), normal, constant mean, fit on returns in percent. Parameters are refit every
    `refit_every` rows on data <= d (last `max_obs` obs); between refits σ² is updated causally
    with the latest parameters. Output: Σ_{h in steps} E[σ²_{d+h}] in log-return² units."""
    from arch import arch_model
    out = pd.DataFrame(np.nan, index=ret.index, columns=ret.columns)
    for t in ret.columns:
        x = (ret[t] * 100).to_numpy()
        obs = np.cumsum(np.isfinite(x))
        params, s2_next = None, None
        for i in range(len(x)):
            if not np.isfinite(x[i]) or obs[i] < min_obs:
                continue
            if params is None or i % refit_every == 0:
                hist = x[:i + 1][np.isfinite(x[:i + 1])][-max_obs:]
                try:
                    res = arch_model(hist, mean="Constant", vol="GARCH", p=1, q=1, dist="normal",
                                     rescale=False).fit(disp="off", show_warning=False)
                    params = (res.params["mu"], res.params["omega"], res.params["alpha[1]"], res.params["beta[1]"])
                except Exception:
                    if params is None:
                        continue
                mu, om, al, be = params
                path = _garch_filter(hist, mu, om, al, be, float(np.var(hist)))
                s2_next = om + al * (hist[-1] - mu) ** 2 + be * path[-1]
            else:
                mu, om, al, be = params
                s2_next = om + al * (x[i] - mu) ** 2 + be * s2_next
            pers = al + be
            unc = om / (1 - pers) if pers < 1 else s2_next
            out.iat[i, out.columns.get_loc(t)] = sum(unc + pers ** (h - 1) * (s2_next - unc) for h in steps) / 1e4
    return out


def _har_features(x: pd.DataFrame) -> dict:
    return {"d": x, "w": x.rolling(5, min_periods=5).mean(), "m": x.rolling(22, min_periods=22).mean()}


def vol_har(daily_var: pd.DataFrame, target_daily_var: pd.DataFrame, steps: Sequence[int],
            refit_every: int = 21, min_train: int = 250) -> pd.DataFrame:
    """Per-ticker HAR: Σ_{h in steps} target_{d+h} ~ 1 + d + w + m, where d/w/m are daily/weekly/
    monthly means of `daily_var` (squared daily returns for the fair rival, RV for the ceiling).
    Refit every `refit_every` days using only rows whose forward window has fully realized
    (row date <= d - max(steps)). Forecast floored at 10% of the monthly-mean level."""
    f = _har_features(daily_var)
    y = sum(target_daily_var.shift(-h) for h in steps)
    hmax = max(steps)
    out = pd.DataFrame(np.nan, index=daily_var.index, columns=daily_var.columns)
    for t in daily_var.columns:
        X = pd.concat({k: v[t] for k, v in f.items()}, axis=1)
        yy = y[t]
        beta = None
        for i in range(len(X)):
            if not X.iloc[i].notna().all():
                continue
            if beta is None or i % refit_every == 0:
                tr_end = i - hmax
                if tr_end < 0:
                    continue
                Xt, yt = X.iloc[:tr_end + 1], yy.iloc[:tr_end + 1]
                ok = Xt.notna().all(axis=1) & yt.notna()
                if ok.sum() < min_train:
                    continue
                A = np.column_stack([np.ones(ok.sum()), Xt[ok].to_numpy()])
                beta = np.linalg.lstsq(A, yt[ok].to_numpy(), rcond=None)[0]
            # linear HAR can go <= 0; floor at 10% of the model's own monthly variance level
            floor = 0.1 * X.iloc[i]["m"] * len(steps)
            out.iat[i, out.columns.get_loc(t)] = max(beta[0] + X.iloc[i].to_numpy() @ beta[1:], floor, 1e-12)
    return out


def vol_chronos(sig: pd.DataFrame) -> pd.DataFrame:
    """Chronos σ over the holding steps -> variance forecast."""
    return sig ** 2


# ═══════════════════════════════════════════════════════════════════════════════
# 7. Portfolio construction
# ═══════════════════════════════════════════════════════════════════════════════

def trailing_betas(ret: pd.DataFrame, mkt_ret: pd.Series, window: int = 250, min_periods: int = 120) -> pd.DataFrame:
    m = mkt_ret.reindex(ret.index)
    cov = ret.apply(lambda c: c.rolling(window, min_periods=min_periods).cov(m))
    var = m.rolling(window, min_periods=min_periods).var()
    return cov.div(var, axis=0)


def _xs_rank(sig: pd.DataFrame, eligible: pd.DataFrame) -> pd.DataFrame:
    s = sig.where(eligible.reindex_like(sig).fillna(False))
    return s.rank(axis=1, pct=True)


def w_ls_rank(sig: pd.DataFrame, eligible: pd.DataFrame, betas: pd.DataFrame | None = None,
              min_names: int = 10) -> pd.DataFrame:
    """Dollar-neutral rank weights with gross exposure 1; optionally also beta-neutral (project
    ranks off [1, β] cross-sectionally, then rescale)."""
    r = _xs_rank(sig, eligible)
    W = pd.DataFrame(0.0, index=r.index, columns=r.columns)
    for d in r.index:
        x = r.loc[d]
        ok = x.notna()
        if betas is not None:
            ok &= betas.loc[d].reindex(x.index).notna() if d in betas.index else False
        if ok.sum() < min_names:
            continue
        z = x[ok] - x[ok].mean()
        if betas is not None:
            A = np.column_stack([np.ones(ok.sum()), betas.loc[d, z.index].to_numpy()])
            z = z - A @ np.linalg.lstsq(A, z.to_numpy(), rcond=None)[0]
        g = np.abs(z).sum()
        if g > 0:
            W.loc[d, z.index] = z / g
    return W


def w_lo_topq(sig: pd.DataFrame, eligible: pd.DataFrame, q: float = 0.2, min_names: int = 10) -> pd.DataFrame:
    r = _xs_rank(sig, eligible)
    top = (r > 1 - q) & r.notna()
    cnt = r.notna().sum(axis=1)
    W = top.astype(float).div(top.sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)
    W[cnt < min_names] = 0.0
    return W


def w_equal(eligible: pd.DataFrame) -> pd.DataFrame:
    e = eligible.astype(float)
    return e.div(e.sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)


def w_inverse_vol(var_fc: pd.DataFrame, eligible: pd.DataFrame) -> pd.DataFrame:
    iv = (1 / np.sqrt(var_fc)).where(eligible.reindex_like(var_fc).fillna(False))
    iv = iv.replace([np.inf, -np.inf], np.nan)
    return iv.div(iv.sum(axis=1), axis=0).fillna(0.0)


def ewma_corr(ret: pd.DataFrame, lam: float = 0.97, min_obs: int = 60) -> dict:
    """{date: correlation DataFrame} using returns <= date (EWMA, pairwise NaN -> 0 update)."""
    cols = ret.columns
    X = ret.fillna(0.0).to_numpy()
    obs = ret.notna().cumsum().to_numpy()
    S = np.zeros((len(cols), len(cols)))
    out = {}
    for i, d in enumerate(ret.index):
        x = X[i][:, None]
        S = lam * S + (1 - lam) * (x @ x.T)
        if i + 1 >= min_obs:
            sd = np.sqrt(np.clip(np.diag(S), 1e-16, None))
            C = S / np.outer(sd, sd)
            C[obs[i] < min_obs, :] = np.nan; C[:, obs[i] < min_obs] = np.nan
            np.fill_diagonal(C, 1.0)
            out[d] = C
    return {"cols": cols, "C": out}


def vol_target_overlay(W: pd.DataFrame, var_fc: pd.DataFrame, corr: dict, n_steps: int,
                       target_ann: float = 0.10, lev_cap: float = 1.0) -> pd.DataFrame:
    """Scale each date's book so its forecast annualized vol equals `target_ann`
    (Σ = D C D with D from `var_fc` over n_steps and C from `ewma_corr`), capped at `lev_cap`."""
    cols = list(corr["cols"])
    out = W.copy() * 0.0
    for d in W.index:
        w = W.loc[d].reindex(cols).fillna(0.0).to_numpy()
        if not np.any(w) or d not in corr["C"] or d not in var_fc.index:
            continue
        sd = np.sqrt(var_fc.loc[d].reindex(cols).to_numpy())
        C = corr["C"][d]
        m = (w != 0)
        if not np.all(np.isfinite(sd[m])) or not np.all(np.isfinite(C[np.ix_(m, m)])):
            continue
        cov = np.outer(sd[m], sd[m]) * C[np.ix_(m, m)]
        vol = math.sqrt(max(w[m] @ cov @ w[m], 1e-16) * TRADING_DAYS / n_steps)
        out.loc[d, cols] = w * min(lev_cap, target_ann / vol)
    return out


# ═══════════════════════════════════════════════════════════════════════════════
# 8. Backtest: staggered weekly tranches, drifting holdings, costs, borrow, exec lag
# ═══════════════════════════════════════════════════════════════════════════════

def run_backtest(target_w: pd.DataFrame, R: pd.DataFrame, exec_lag: int = 1, n_tranches: int = 5,
                 cost_bps: float = 0.0, borrow_annual: float = 0.0, start=None, end=None) -> pd.DataFrame:
    """Daily P&L per unit notional of `n_tranches` staggered books.

    target_w: desired weights indexed at the SIGNAL date d (row = book decided at close d).
    Tranche k trades at close τ = d + exec_lag on calendar positions p(τ) ≡ k (mod n_tranches),
    holds positions that drift with (1+R), earns R from τ+1. Cost = cost_bps × |Δw| at τ.
    Borrow = borrow_annual/252 × short notional, daily. Returns are averaged over tranches.
    `start`/`end` restrict the *reporting* window (holdings may be set before `start`)."""
    Wt = target_w.reindex(R.index).shift(exec_lag)          # indexed at trade date τ
    R0 = R.fillna(0.0).to_numpy()
    Wa = Wt.to_numpy()
    n, m = R0.shape
    gross = np.zeros(n); cost = np.zeros(n); borrow = np.zeros(n); turn = np.zeros(n)
    long_e = np.zeros(n); short_e = np.zeros(n)
    has_book = np.isfinite(Wa).any(axis=1)                 # rows before the first signal are all-NaN
    for k in range(n_tranches):
        h = np.zeros(m)
        for i in range(n):
            if i > 0:
                gross[i] += h @ R0[i] / n_tranches
                borrow[i] += borrow_annual / TRADING_DAYS * np.clip(-h, 0, None).sum() / n_tranches
                h = h * (1 + R0[i])
            if i % n_tranches == k and has_book[i]:
                w_new = np.nan_to_num(Wa[i], nan=0.0)
                tv = np.abs(w_new - h).sum()
                turn[i] += tv / n_tranches
                cost[i] += cost_bps / 1e4 * tv / n_tranches
                h = w_new
            long_e[i] += np.clip(h, 0, None).sum() / n_tranches
            short_e[i] += np.clip(-h, 0, None).sum() / n_tranches
    out = pd.DataFrame({"gross": gross, "cost": cost, "borrow": borrow, "turnover": turn,
                        "long_exp": long_e, "short_exp": short_e}, index=R.index)
    out["net"] = out["gross"] - out["cost"] - out["borrow"]
    if start is not None:
        out = out[out.index >= pd.Timestamp(start)]
    if end is not None:
        out = out[out.index <= pd.Timestamp(end)]
    return out


# ═══════════════════════════════════════════════════════════════════════════════
# 9. Statistics
# ═══════════════════════════════════════════════════════════════════════════════

def ic_series(sig: pd.DataFrame, fwd: pd.DataFrame, eligible: pd.DataFrame, min_names: int = 10) -> pd.Series:
    """Cross-sectional Spearman IC per date over eligible names with both values."""
    s = sig.where(eligible.reindex_like(sig).fillna(False))
    f = fwd.reindex_like(s)
    ok = s.notna() & f.notna()
    rs = s.where(ok).rank(axis=1); rf = f.where(ok).rank(axis=1)
    rs = rs.sub(rs.mean(axis=1), axis=0); rf = rf.sub(rf.mean(axis=1), axis=0)
    ic = (rs * rf).sum(axis=1) / np.sqrt((rs ** 2).sum(axis=1) * (rf ** 2).sum(axis=1))
    return ic[ok.sum(axis=1) >= min_names].rename("ic")


def nw_tstat(x: pd.Series | np.ndarray, lags: int) -> dict:
    """Mean, Newey-West (Bartlett) s.e. and t-stat of a series."""
    x = pd.Series(x).dropna().to_numpy(dtype=float)
    n = len(x)
    if n < 3:
        return dict(mean=np.nan, se=np.nan, t=np.nan, n=n)
    e = x - x.mean()
    s = e @ e / n
    for L in range(1, min(lags, n - 1) + 1):
        s += 2 * (1 - L / (lags + 1)) * (e[L:] @ e[:-L]) / n
    se = math.sqrt(max(s, 0) / n)
    return dict(mean=float(x.mean()), se=se, t=float(x.mean() / se) if se > 0 else np.nan, n=n)


def ols_nw(y: pd.Series, X: pd.DataFrame, lags: int) -> pd.DataFrame:
    """OLS with constant and Newey-West covariance; returns coef, se, t per regressor."""
    import statsmodels.api as sm
    d = pd.concat([y.rename("y"), X], axis=1).dropna()
    res = sm.OLS(d["y"], sm.add_constant(d.drop(columns="y"))).fit(cov_type="HAC", cov_kwds={"maxlags": lags})
    return pd.DataFrame({"coef": res.params, "se": res.bse, "t": res.tvalues, "n": int(res.nobs)})


def perf_stats(r: pd.Series, rf: pd.Series | None = None, periods: int = TRADING_DAYS) -> dict:
    """Annualized stats of a daily simple-return series (excess over rf if given)."""
    r = r.dropna()
    x = r - rf.reindex(r.index).fillna(0.0) if rf is not None else r
    if len(x) < 2 or x.std() == 0:
        return dict(n=len(x))
    eq = (1 + r).cumprod()
    dd = eq / eq.cummax() - 1
    downside = x[x < 0].std()
    q = x.quantile(0.05)
    return dict(n=len(x), ann_ret=float(x.mean() * periods), ann_vol=float(x.std() * math.sqrt(periods)),
                sharpe=float(x.mean() / x.std() * math.sqrt(periods)),
                sortino=float(x.mean() / downside * math.sqrt(periods)) if downside > 0 else np.nan,
                max_dd=float(dd.min()), cvar5=float(x[x <= q].mean()),
                skew=float(sstats.skew(x)), kurt=float(sstats.kurtosis(x, fisher=False)))


def cost_breakeven_bps(bt: pd.DataFrame) -> float:
    """One-way cost (bps) at which mean net return (before borrow) hits zero."""
    tv = bt["turnover"].mean()
    return float((bt["gross"].mean() - bt["borrow"].mean()) / tv * 1e4) if tv > 0 else np.nan


def sharpe_diff_bootstrap(a: pd.Series, b: pd.Series, n_boot: int = 2000, block: int = 20, seed: int = 0) -> dict:
    """Stationary block bootstrap of Sharpe(a) - Sharpe(b) on aligned daily returns.
    p_one_sided = P*(diff <= 0) (small => a better)."""
    from arch.bootstrap import StationaryBootstrap
    d = pd.concat([a.rename("a"), b.rename("b")], axis=1).dropna()
    sr = lambda x: x.mean() / x.std() * math.sqrt(TRADING_DAYS)
    obs = sr(d["a"]) - sr(d["b"])
    bs = StationaryBootstrap(block, d.to_numpy(), seed=seed)
    diffs = np.array([sr(pd.Series(x[0][:, 0])) - sr(pd.Series(x[0][:, 1])) for x, _ in bs.bootstrap(n_boot)])
    centered = diffs - diffs.mean()             # null-centered (H0: equal Sharpe)
    return dict(diff=float(obs), ci_lo=float(np.quantile(diffs, 0.025)), ci_hi=float(np.quantile(diffs, 0.975)),
                p_one_sided=float((centered >= obs).mean()))


def deflated_sharpe(sr_period: float, n_obs: int, n_trials: int, sr_trials_var: float,
                    skew: float = 0.0, kurt: float = 3.0) -> float:
    """Bailey & López de Prado (2014) DSR. All Sharpe inputs are PER-PERIOD (not annualized).
    Returns P(true SR > max-of-N-trials null)."""
    if n_trials < 1 or n_obs < 3:
        return np.nan
    g = 0.5772156649
    if n_trials == 1:
        sr0 = 0.0
    else:
        sr0 = math.sqrt(max(sr_trials_var, 0)) * ((1 - g) * sstats.norm.ppf(1 - 1 / n_trials)
                                                  + g * sstats.norm.ppf(1 - 1 / (n_trials * math.e)))
    den = math.sqrt(max(1 - skew * sr_period + (kurt - 1) / 4 * sr_period ** 2, 1e-12))
    return float(sstats.norm.cdf((sr_period - sr0) * math.sqrt(n_obs - 1) / den))


def xs_standardize(sig: pd.DataFrame, eligible: pd.DataFrame) -> pd.DataFrame:
    """Cross-sectional rank -> centered on 0, unit variance per date (robust to outliers).
    A date on which the signal is constant across names carries no cross-sectional information
    and is set to 0 (not 0/0 = NaN)."""
    r = _xs_rank(sig, eligible)
    r = r.sub(r.mean(axis=1), axis=0)
    sd = r.std(axis=1)
    z = r.div(sd.where(sd > 0), axis=0)
    const = (sd == 0).to_numpy()
    z.loc[const] = r.loc[const]            # centered ranks of a constant row are already 0 (NaN kept)
    return z


def fama_macbeth(fwd: pd.DataFrame, signals: dict[str, pd.DataFrame], eligible: pd.DataFrame,
                 lags: int, dates: pd.DatetimeIndex | None = None, min_names: int = 15) -> pd.DataFrame:
    """Per-date cross-sectional OLS of forward return on standardized signals; NW t on the
    time series of slopes."""
    Z = {k: xs_standardize(v, eligible) for k, v in signals.items()}
    dates = dates if dates is not None else fwd.index
    rows = {}
    for d in dates:
        if d not in fwd.index:
            continue
        df = pd.DataFrame({k: z.loc[d] for k, z in Z.items() if d in z.index})
        if df.shape[1] != len(Z):
            continue
        df["y"] = fwd.loc[d]
        df = df.dropna()
        if len(df) < min_names:
            continue
        A = np.column_stack([np.ones(len(df)), df[list(Z)].to_numpy()])
        rows[d] = np.linalg.lstsq(A, df["y"].to_numpy(), rcond=None)[0]
    B = pd.DataFrame(rows, index=["const"] + list(Z)).T
    res = {k: nw_tstat(B[k], lags) for k in B.columns}
    return pd.DataFrame(res).T


def qlike(rv: np.ndarray, f: np.ndarray) -> np.ndarray:
    """QLIKE loss per observation (Patton 2011, robust to noisy RV proxies)."""
    x = rv / f
    return x - np.log(x) - 1


def vol_loss_panel(rv_fwd: pd.DataFrame, fc: pd.DataFrame, mask: pd.DataFrame, scale: float = 1.0) -> pd.Series:
    """Per-date mean QLIKE across masked names (panel -> time series for DM tests)."""
    f = fc.reindex_like(rv_fwd) * scale
    ok = mask.reindex_like(rv_fwd).fillna(False) & rv_fwd.gt(0) & f.gt(0)
    L = pd.DataFrame(qlike(rv_fwd.where(ok).to_numpy(), f.where(ok).to_numpy()), index=rv_fwd.index,
                     columns=rv_fwd.columns)
    return L.where(ok).mean(axis=1)


def qlike_scale(rv_fwd: pd.DataFrame, fc: pd.DataFrame, mask: pd.DataFrame) -> float:
    """QLIKE-optimal multiplicative scale c = mean(rv/f) (fit on dev, applied on test)."""
    f = fc.reindex_like(rv_fwd)
    ok = mask.reindex_like(rv_fwd).fillna(False) & rv_fwd.gt(0) & f.gt(0)
    return float((rv_fwd[ok] / f[ok]).stack().mean())


def dm_test(loss_a: pd.Series, loss_b: pd.Series, lags: int) -> dict:
    """Diebold-Mariano on per-date loss differential d = L_a - L_b; one-sided p for 'a better'
    (d < 0)."""
    d = (loss_a - loss_b).dropna()
    r = nw_tstat(d, lags)
    r["p_a_better"] = float(sstats.norm.cdf(r["t"])) if np.isfinite(r["t"]) else np.nan
    return r


def mincer_zarnowitz(rv_fwd: pd.DataFrame, fc: pd.DataFrame, mask: pd.DataFrame) -> dict:
    f = fc.reindex_like(rv_fwd)
    ok = mask.reindex_like(rv_fwd).fillna(False) & rv_fwd.gt(0) & f.gt(0)
    y = np.log(rv_fwd[ok].stack()); x = np.log(f[ok].stack())
    d = pd.concat([y, x], axis=1).dropna()
    b, a = np.polyfit(d.iloc[:, 1], d.iloc[:, 0], 1)
    r2 = np.corrcoef(d.iloc[:, 0], d.iloc[:, 1])[0, 1] ** 2
    return dict(intercept=float(a), slope=float(b), r2_log=float(r2), n=len(d))


def var_coverage(ret: pd.DataFrame, qfc: pd.DataFrame, level: float, mask: pd.DataFrame) -> dict:
    """VaR backtest of 1-step quantile forecasts (qfc at signal date d for r_{d+1}).
    Pooled hit rate, Kupiec LR (pooled, ignores cross-sectional dependence) and the share of
    tickers rejecting Christoffersen independence at 5%."""
    r1 = ret.shift(-1).reindex_like(qfc)
    ok = mask.reindex_like(qfc).fillna(False) & r1.notna() & qfc.notna()
    hits = (r1 < qfc).where(ok)
    x = hits.stack().dropna().astype(float)          # pandas>=3 stack keeps NaN -> drop explicitly
    n, k = len(x), x.sum()
    p = k / n if n else np.nan
    lr_uc = -2 * (k * math.log(level) + (n - k) * math.log(1 - level)
                  - (k * math.log(max(p, 1e-12)) + (n - k) * math.log(max(1 - p, 1e-12)))) if n else np.nan
    rej = []
    for t in hits.columns:
        h = hits[t].dropna().to_numpy().astype(int)
        if len(h) < 50:
            continue
        a, b = h[:-1], h[1:]
        n00 = ((a == 0) & (b == 0)).sum(); n01 = ((a == 0) & (b == 1)).sum()
        n10 = ((a == 1) & (b == 0)).sum(); n11 = ((a == 1) & (b == 1)).sum()
        p01 = n01 / max(n00 + n01, 1); p11 = n11 / max(n10 + n11, 1); p1 = (n01 + n11) / max(len(a), 1)
        ll = lambda q, c1, c0: (c1 * math.log(q) if c1 else 0) + (c0 * math.log(1 - q) if c0 else 0)
        if 0 < p1 < 1:
            lr = -2 * (ll(p1, n01 + n11, n00 + n10) - ll(p01, n01, n00) - ll(p11, n11, n10) if 0 < p01 < 1 else 0)
            rej.append(lr > sstats.chi2.ppf(0.95, 1))
    return dict(level=level, n=int(n), hit_rate=float(p), kupiec_lr=float(lr_uc),
                kupiec_p=float(1 - sstats.chi2.cdf(lr_uc, 1)) if n else np.nan,
                christoffersen_reject_share=float(np.mean(rej)) if rej else np.nan)


def ic_permutation_null(sig: pd.DataFrame, fwd: pd.DataFrame, eligible: pd.DataFrame, n_perm: int = 1000,
                        seed: int = 0, min_names: int = 10) -> np.ndarray:
    """Distribution of mean IC when signal ranks are shuffled within each date."""
    rng = np.random.default_rng(seed)
    s = sig.where(eligible.reindex_like(sig).fillna(False))
    f = fwd.reindex_like(s)
    ok = s.notna() & f.notna()
    keep = ok.sum(axis=1) >= min_names
    rs = s.where(ok).rank(axis=1)[keep].to_numpy(); rf = f.where(ok).rank(axis=1)[keep].to_numpy()
    total = np.zeros(n_perm)
    for i in range(rs.shape[0]):
        m = ~np.isnan(rs[i])
        a = rs[i, m] - rs[i, m].mean(); b = rf[i, m] - rf[i, m].mean()
        b = b / np.linalg.norm(b); a = a / np.linalg.norm(a)
        total += rng.permuted(np.tile(a, (n_perm, 1)), axis=1) @ b
    return total / rs.shape[0]


# ═══════════════════════════════════════════════════════════════════════════════
# 10. Harness validation helpers + trial ledger
# ═══════════════════════════════════════════════════════════════════════════════

def make_planted_panel(n_dates: int = 800, n_tickers: int = 60, ic: float = 0.05, vol: float = 0.02,
                       horizon: int = 5, seed: int = 0) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Synthetic daily log returns + a signal known at d. r_i loads ic/√horizon on each of the
    previous `horizon` signal values, so corr(sig_d, Σ_{h=1..horizon} r_{d+h}) ≈ ic."""
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2021-01-04", periods=n_dates)
    cols = [f"T{i:02d}" for i in range(n_tickers)]
    sig = rng.standard_normal((n_dates, n_tickers))
    eps = rng.standard_normal((n_dates, n_tickers))
    r = np.zeros((n_dates, n_tickers))
    # r_{d+h} gets ic * mean of the signal over the last `horizon` days (predictable part)
    for i in range(n_dates):
        lo = max(0, i - horizon)
        pred = sig[lo:i].mean(axis=0) * math.sqrt(horizon) if i > 0 else 0.0
        r[i] = vol * (ic * pred + math.sqrt(1 - ic ** 2) * eps[i])
    return (pd.DataFrame(r, index=idx, columns=cols), pd.DataFrame(sig, index=idx, columns=cols))


def append_trial(ledger_path, **row) -> None:
    """Append one row to the trial ledger CSV (every evaluated variant, every period)."""
    p = Path(ledger_path)
    row = {"logged_at": pd.Timestamp.now().isoformat(timespec="seconds"), **row}
    df = pd.DataFrame([row])
    df.to_csv(p, mode="a", header=not p.exists(), index=False)


# ═══════════════════════════════════════════════════════════════════════════════
# 11. Step-3 improvements: mimic, combination, turnover control, vol calibration
# ═══════════════════════════════════════════════════════════════════════════════

def context_features(ret: pd.DataFrame, shape: bool = False) -> dict[str, pd.DataFrame]:
    """Cheap statistics of each name's own return history, all known at close d (the inputs a
    'Chronos-mimic' may use): trailing means, trailing vols, last return, EWMA vol; with
    shape=True also trailing skewness, kurtosis and 20-day max/min return (shape mimic)."""
    f = {f"m{w}": ret.rolling(w, min_periods=max(3, w // 2)).mean() for w in (5, 20, 60, 120, 250)}
    f.update({f"s{w}": ret.rolling(w, min_periods=max(3, w // 2)).std() for w in (20, 60, 250)})
    f["r1"] = ret
    f["ewvol"] = np.sqrt((ret ** 2).ewm(alpha=0.06, adjust=False, ignore_na=True).mean())
    if shape:
        for w in (60, 250):
            f[f"skew{w}"] = ret.rolling(w, min_periods=w // 2).skew()
            f[f"kurt{w}"] = ret.rolling(w, min_periods=w // 2).kurt()
        f["max20"] = ret.rolling(20, min_periods=10).max()
        f["min20"] = ret.rolling(20, min_periods=10).min()
    return f


def _stack_z(frames: dict[str, pd.DataFrame], mask: pd.DataFrame) -> dict[str, pd.DataFrame]:
    return {k: xs_standardize(v, mask) for k, v in frames.items()}


def rolling_xs_fit(target: pd.DataFrame, features: dict[str, pd.DataFrame], mask: pd.DataFrame,
                   window: int = 250, refit_every: int = 21, min_rows: int = 2000) -> tuple[pd.DataFrame, pd.Series]:
    """Causal pooled regression of the cross-sectionally standardized `target` on standardized
    `features` (plus their squares). Coefficients used at date d are fit on dates (d-window, d-1]
    only, refit every `refit_every` dates. Returns (fitted values, per-date out-of-sample corr
    between fitted and actual target)."""
    Zt = xs_standardize(target, mask)
    Zf = _stack_z(features, mask)
    names = list(Zf) + [f"{k}^2" for k in Zf]
    Zf.update({f"{k}^2": v ** 2 for k, v in list(Zf.items())})
    dates = target.index
    fitted = pd.DataFrame(np.nan, index=dates, columns=target.columns)
    beta = None
    Y = Zt.to_numpy(); Xs = np.stack([Zf[k].to_numpy() for k in names], axis=-1)   # (T, N, K)
    for i, d in enumerate(dates):
        if beta is None or i % refit_every == 0:
            lo = max(0, i - window)
            y = Y[lo:i].reshape(-1); x = Xs[lo:i].reshape(-1, len(names))
            ok = np.isfinite(y) & np.isfinite(x).all(axis=1)
            if ok.sum() >= min_rows:
                A = np.column_stack([np.ones(ok.sum()), x[ok]])
                beta = np.linalg.lstsq(A, y[ok], rcond=None)[0]
        if beta is None:
            continue
        x = Xs[i]
        ok = np.isfinite(x).all(axis=1)
        v = np.full(x.shape[0], np.nan)
        v[ok] = beta[0] + x[ok] @ beta[1:]
        fitted.iloc[i] = v
    fitted = fitted.where(mask.reindex_like(fitted).fillna(False))
    oos = pd.Series({d: pd.concat([fitted.loc[d], Zt.loc[d]], axis=1).dropna().corr().iloc[0, 1]
                     for d in dates if fitted.loc[d].notna().sum() >= 10})
    return fitted, oos


def xs_slopes(fwd: pd.DataFrame, signals: dict[str, pd.DataFrame], mask: pd.DataFrame, min_names: int = 15) -> pd.DataFrame:
    """Per-date Fama-MacBeth slopes of forward return on standardized signals (row = signal date)."""
    Z = _stack_z(signals, mask)
    rows = {}
    for d in fwd.index:
        df = pd.DataFrame({k: z.loc[d] for k, z in Z.items()})
        df["y"] = fwd.loc[d]
        df = df.dropna()
        if len(df) < min_names:
            continue
        A = np.column_stack([np.ones(len(df)), df[list(Z)].to_numpy()])
        rows[d] = np.linalg.lstsq(A, df["y"].to_numpy(), rcond=None)[0][1:]
    return pd.DataFrame(rows, index=list(Z)).T.reindex(fwd.index)


def rolling_composite(fwd: pd.DataFrame, signals: dict[str, pd.DataFrame], mask: pd.DataFrame, horizon: int,
                      window: int = 250, min_obs: int = 120, slopes: pd.DataFrame | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Composite = Σ_k w_k(d) z_k(d), with w(d) = mean Fama-MacBeth slope over signal dates in
    (d-horizon-window, d-horizon] — only slopes whose forward return has fully realized by d.
    Returns (composite signal, weights)."""
    S = slopes if slopes is not None else xs_slopes(fwd, signals, mask)
    W = S.shift(horizon).rolling(window, min_periods=min_obs).mean()
    Z = _stack_z(signals, mask)
    comp = sum(Z[k].mul(W[k], axis=0) for k in signals)
    return comp.where(mask.reindex_like(comp).fillna(False)), W


def smooth_signal(sig: pd.DataFrame, mask: pd.DataFrame, halflife: float) -> pd.DataFrame:
    """Causal EMA (per name) of the cross-sectionally standardized signal; halflife in trading days."""
    z = xs_standardize(sig, mask)
    if not halflife:
        return z
    sm = z.ewm(halflife=halflife, adjust=False, ignore_na=True).mean()
    return sm.where(mask.reindex_like(sm).fillna(False))


def rolling_vol_scale(var_fc: pd.DataFrame, rv_fwd: pd.DataFrame, mask: pd.DataFrame, horizon: int,
                      window: int = 250, min_obs: int = 60) -> pd.Series:
    """Causal level recalibration: scale(d) = median over signal dates (d-horizon-window, d-horizon]
    of the cross-sectional mean of rv_fwd / var_fc (only fully realized windows)."""
    ok = mask.reindex_like(var_fc).fillna(False) & var_fc.gt(0) & rv_fwd.reindex_like(var_fc).gt(0)
    ratio = (rv_fwd.reindex_like(var_fc) / var_fc).where(ok).mean(axis=1)
    return ratio.shift(horizon).rolling(window, min_periods=min_obs).median()


def mean_exp_quantiles(Q: np.ndarray, u: Sequence[float] = NATIVE_QUANTILES, n_grid: int = 199) -> np.ndarray:
    """E[exp(X)] for X with piecewise-linear quantile function through (u_k, Q[..., k]) and flat
    tails: numerical ∫ exp(Q(u)) du on a fine u-grid. Used to turn log-RV quantiles into E[RV]."""
    Q = np.asarray(Q, dtype=float)
    u = np.asarray(u, dtype=float)
    g = (np.arange(n_grid) + 0.5) / n_grid
    idx = np.clip(np.searchsorted(u, g) - 1, 0, len(u) - 2)
    w = np.clip((g - u[idx]) / (u[idx + 1] - u[idx]), 0, 1)
    Qg = Q[..., idx] * (1 - w) + Q[..., idx + 1] * w
    Qg = np.where(g < u[0], Q[..., :1], np.where(g > u[-1], Q[..., -1:], Qg))
    return np.exp(Qg).mean(axis=-1)


def quantile_shape_features(preds: pd.DataFrame, steps: Sequence[int], quantiles: Sequence[float] = NATIVE_QUANTILES) -> pd.DataFrame:
    """Shape of the per-step forecast distribution, averaged over `steps`:
    SKEW = (q90+q10-2q50)/(q90-q10); UPDOWN = log((q90-q50)/(q50-q10)); TAIL = (q99-q01)/(q90-q10);
    DOWN = (q50-q05)/(q90-q10) (standardized downside); PUP = forecast P(r>0) from the piecewise-
    linear quantile function; plus robust per-step spreads for the vol track:
    VAR_IQR80 = Σ ((q90-q10)/2.5631)^2 and VAR_IQR50 = Σ ((q75-q25)/1.3490)^2 (Normal-equivalent)."""
    p = preds[preds["h"].isin(list(steps))].copy()
    w = (p["q0.9"] - p["q0.1"]).replace(0, np.nan)
    up = (p["q0.9"] - p["q0.5"]).clip(lower=1e-12); dn = (p["q0.5"] - p["q0.1"]).clip(lower=1e-12)
    p["SKEW"] = (p["q0.9"] + p["q0.1"] - 2 * p["q0.5"]) / w
    p["UPDOWN"] = np.log(up / dn)
    p["TAIL"] = (p["q0.99"] - p["q0.01"]) / w
    p["DOWN"] = (p["q0.5"] - p["q0.05"]) / w
    Q = p[[f"q{q:g}" for q in quantiles]].to_numpy(); u = np.asarray(quantiles)
    pup = np.empty(len(p))
    for i in range(len(p)):                       # P(r>0) = 1 - F(0), F from interpolating u over Q
        q = Q[i]
        pup[i] = 1 - (u[0] if 0 <= q[0] else u[-1] if 0 >= q[-1] else np.interp(0.0, q, u))
    p["PUP"] = pup
    p["V80"] = ((p["q0.9"] - p["q0.1"]) / 2.5631) ** 2
    p["V50"] = ((p["q0.75"] - p["q0.25"]) / 1.3490) ** 2
    g = p.groupby(["anchor", "ticker"])
    out = g[["SKEW", "UPDOWN", "TAIL", "DOWN", "PUP"]].mean()
    out["VAR_IQR80"] = g["V80"].sum(); out["VAR_IQR50"] = g["V50"].sum()
    return out


def vol_har_log(rv: pd.DataFrame, steps: Sequence[int], mask: pd.DataFrame | None = None, pooled: bool = False,
                market: bool = False, refit_every: int = 21, min_train: int = 250, eps: float = 1e-7) -> pd.DataFrame:
    """HAR on LOG realized variance (the standard strong RV benchmark):
    log Σ_{h in steps} RV_{d+h} ~ 1 + log RV_d + log mean RV_{d-4..d} + log mean RV_{d-21..d}
    [+ the same three terms for the market's cross-sectional mean log RV if `market`].
    Forecast = exp(fit + ½·σ²_resid) (log-normal smearing). Causal: coefficients used at d are fit
    on rows whose forward window has realized (row date <= d - max(steps)), refit every
    `refit_every` rows. `pooled`: one regression across all names (restricted to `mask`) instead of
    one per name — the classical analogue of Chronos cross-learning."""
    lrv = np.log(rv.clip(lower=0) + eps)
    feats = {"d": lrv, "w": np.log(rv.rolling(5, min_periods=5).mean() + eps),
             "m": np.log(rv.rolling(22, min_periods=22).mean() + eps)}
    if market:
        mk = (lrv.where(mask) if mask is not None else lrv).mean(axis=1)
        for k, v in {"md": mk, "mw": mk.rolling(5, min_periods=5).mean(), "mm": mk.rolling(22, min_periods=22).mean()}.items():
            feats[k] = pd.DataFrame(np.repeat(v.to_numpy()[:, None], rv.shape[1], 1), rv.index, rv.columns)
    y = np.log(sum(rv.shift(-h) for h in steps) + eps)
    names = list(feats)
    F = np.stack([feats[k].to_numpy() for k in names], axis=-1)          # (T, N, K)
    Y = y.to_numpy()
    M = mask.reindex_like(rv).fillna(False).to_numpy() if mask is not None else np.ones(rv.shape, bool)
    T, N, K = F.shape
    hmax = max(steps)
    out = np.full((T, N), np.nan)
    def fit(rows_x, rows_y):
        ok = np.isfinite(rows_y) & np.isfinite(rows_x).all(axis=1)
        if ok.sum() < min_train:
            return None
        A = np.column_stack([np.ones(ok.sum()), rows_x[ok]])
        b = np.linalg.lstsq(A, rows_y[ok], rcond=None)[0]
        res = rows_y[ok] - A @ b
        return b, float(res.var())
    cols = [slice(None)] if pooled else [slice(j, j + 1) for j in range(N)]
    for c in cols:
        par = None
        for i in range(T):
            if par is None or i % refit_every == 0:
                end = i - hmax
                if end >= 0:
                    xs = F[:end + 1, c].reshape(-1, K); ys = Y[:end + 1, c].reshape(-1)
                    ms = M[:end + 1, c].reshape(-1)
                    got = fit(xs[ms], ys[ms]) if pooled else fit(xs, ys)
                    par = got or par
            if par is None:
                continue
            b, s2 = par
            x = F[i, c]
            ok = np.isfinite(x).all(axis=1)
            v = np.full(x.shape[0], np.nan)
            v[ok] = np.exp(b[0] + x[ok] @ b[1:] + 0.5 * s2)
            out[i, c] = v
    return pd.DataFrame(out, index=rv.index, columns=rv.columns)
