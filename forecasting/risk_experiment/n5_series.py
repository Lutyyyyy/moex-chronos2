"""Source N5 inputs (plan section F5): realized-variance series for the correlation side of risk.

  (a) portfolio RV: the equal-weight portfolio of eligible names and IMOEX;
  (b) one-factor model: each stock's residual RV after removing β_i(d-1)·r_IMOEX bar by bar.

All series use the same 10m convention as alpha_lib.realized_variance: main-session bars on calendar
dates, the first bar of a day differenced against the previous main-session bar (overnight included),
adjusted prices. A series value at date t uses bars of t and information known at t only.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[0] / "alpha_experiment"))
import alpha_lib as al  # noqa: E402


def bar_returns(bars: pd.DataFrame, calendar: pd.DatetimeIndex, col: str = "close_adj") -> pd.DataFrame:
    """Wide timestamp x ticker 10m log returns (NaN where a ticker did not print), with a `date` column
    level in the index: MultiIndex (date, timestamp)."""
    b = al.main_session_bars(bars)
    b = b[b["date"].isin(calendar)].sort_values(["ticker", "timestamp"])
    b = b.assign(r=np.log(b[col]).groupby(b["ticker"]).diff())
    w = b.pivot_table(index=["date", "timestamp"], columns="ticker", values="r", aggfunc="last")
    return w.sort_index()


def _by_date(frame: pd.DataFrame, R: pd.DataFrame) -> np.ndarray:
    """Broadcast a date x ticker frame onto the bar rows of R (MultiIndex (date, timestamp))."""
    d = R.index.get_level_values("date")
    return frame.reindex(index=d, columns=R.columns).to_numpy()


def portfolio_rv(R: pd.DataFrame, weights: pd.DataFrame) -> pd.Series:
    """Σ over bars of (Σ_i w_i(t)·r_i)², where w(t) is the date-t weight row (a missing print counts as 0;
    the move then shows up in the ticker's next printed bar)."""
    W = np.nan_to_num(_by_date(weights, R))
    p = (np.nan_to_num(R.to_numpy()) * W).sum(axis=1)
    s = pd.Series(p ** 2, index=R.index.get_level_values("date"))
    return s.groupby(level=0).sum()


def residual_rv(R: pd.DataFrame, r_m: pd.Series, beta: pd.DataFrame) -> pd.DataFrame:
    """Per ticker Σ over bars of (r_i − β_i(t)·r_m)², with r_m the market bar return at the same timestamp.
    NaN on dates where the ticker has no printed bar or β is missing."""
    m = r_m.reindex(R.index).fillna(0.0).to_numpy()[:, None]
    B = _by_date(beta, R)
    X = R.to_numpy()
    e = np.where(np.isnan(X), 0.0, X) - B * m
    e2 = pd.DataFrame(e ** 2, index=R.index.get_level_values("date"), columns=R.columns)
    printed = pd.DataFrame(np.isfinite(X), index=e2.index, columns=R.columns).groupby(level=0).any()
    out = e2.groupby(level=0).sum(min_count=1)
    return out.where(printed & np.isfinite(beta.reindex_like(out)))


def futures_rv(fut_bars: pd.DataFrame, calendar: pd.DatetimeIndex) -> pd.DataFrame:
    """Daily realized variance of continuous futures (source N6 covariates): main-session 10m log returns
    on calendar dates, overnight included, but a return between two different contracts (the roll) is
    dropped, never counted as a price move. Wide date x ticker."""
    b = al.main_session_bars(fut_bars)
    b = b[b["date"].isin(calendar)].sort_values(["ticker", "timestamp"])
    g = b.groupby("ticker")
    r = np.log(b["close"]).groupby(b["ticker"]).diff().where(b["contract"].eq(g["contract"].shift()))
    rv = (r ** 2).groupby([b["date"], b["ticker"]]).sum(min_count=1)
    return rv.unstack("ticker").reindex(calendar)


def ew_weights(eligible: pd.DataFrame) -> pd.DataFrame:
    e = eligible.astype(float)
    return e.div(e.sum(axis=1).replace(0, np.nan), axis=0)
