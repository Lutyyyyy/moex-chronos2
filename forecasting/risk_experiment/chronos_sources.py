"""New zero-shot Chronos-2 sources for the risk study (plan v3, R2).

N1  multivariate target [return, log-RV] per stock, daily, H=5: the return row gives VaR/ES informed
    by the intraday realized-variance history; the RV row gives a vol forecast informed by returns.
N4  the same pairing on non-overlapping 5-day blocks ending at the anchor, H=1: a direct 5-day
    distribution. Per-step daily quantiles have no joint distribution, so 5-day quantiles cannot be
    built from them.

In Chronos-2 a 2-D target (n_variates, T) is one item whose rows attend to each other (the same
mechanism as past covariates, but every row is forecast). cross_learning=True additionally lets all
items of one anchor attend to each other, so a call holds exactly one anchor.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Sequence

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "alpha_experiment"))
import alpha_lib as al  # noqa: E402

RV_EPS = 1e-7   # same floor as alpha_run.RV_EPS: log(RV + eps)


def rv_panels(ret: pd.DataFrame, rv: pd.DataFrame, block: int = 1) -> dict[str, pd.DataFrame]:
    """{'ret': returns, 'logrv': log realized variance}, summed over `block` days when block > 1
    (a 5-day log return and log 5-day RV). Both are known at the close of each row's date."""
    if block > 1:
        ret = ret.rolling(block, min_periods=block).sum()
        rv = rv.rolling(block, min_periods=block).sum()
    return {"ret": ret, "logrv": np.log(rv.clip(lower=0) + RV_EPS).where(rv.notna())}


def multivariate_contexts(panels: dict[str, pd.DataFrame], eligible: pd.DataFrame, anchor, ctx: int,
                          stride: int = 1, min_len: int = 32) -> tuple[list, list]:
    """One 2-D context (n_variates, T) per eligible ticker: the last `ctx` dates up to and including the
    anchor on which the FIRST panel is observed (optionally every `stride`-th date, counted back from
    the anchor). The other variates sit on exactly those dates; their missing values are
    forward-filled within the context, then 0. Nothing after the anchor is used."""
    names = list(panels)
    first = panels[names[0]]
    row = eligible.loc[anchor]
    tickers = list(row.index[row.fillna(False).to_numpy().astype(bool)])
    keep, inputs = [], []
    for t in tickers:
        s = first.loc[:anchor, t].dropna()
        if stride > 1:
            s = s.iloc[::-1].iloc[::stride].iloc[::-1]
        s = s.iloc[-ctx:]
        if len(s) < min(ctx, min_len):
            continue
        rows = [s.to_numpy()]
        for n in names[1:]:
            rows.append(panels[n][t].reindex(s.index).ffill().fillna(0.0).to_numpy())
        inputs.append(np.vstack(rows).astype(np.float32))
        keep.append(t)
    return keep, inputs


def generate_multivariate(pipeline, panels: dict[str, pd.DataFrame], eligible: pd.DataFrame, anchors: Sequence,
                          ctx: int, H: int, quantiles: Sequence[float] = al.NATIVE_QUANTILES, stride: int = 1,
                          cross_learning: bool = True, anchors_per_call: int = 1, batch_size: int = 256,
                          out_path=None, checkpoint_every: int = 50, holdout_unlock: bool = False,
                          progress: bool = True) -> pd.DataFrame:
    """Long frame [anchor, ticker, variate, h, q<level>...] with one block of rows per variate.
    Resumes from `<out_path>.partial.parquet`. The holdout lock and cross-learning guards match
    alpha_lib.generate_forecasts."""
    anchors = pd.DatetimeIndex(anchors)
    names = list(panels)
    if cross_learning and anchors_per_call != 1:
        raise ValueError("cross_learning requires anchors_per_call=1 (no cross-anchor attention / look-ahead)")
    if not holdout_unlock and len(anchors) and anchors.max() >= al.HOLDOUT_START:
        raise AssertionError(f"holdout locked: anchor {anchors.max().date()} >= {al.HOLDOUT_START.date()}")
    qcols = [f"q{q:g}" for q in quantiles]
    partial = Path(str(out_path) + ".partial.parquet") if out_path else None
    if out_path is not None:
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)   # checkpoints are written mid-run
    done = []
    if partial is not None and partial.exists():
        prev = pd.read_parquet(partial)
        done.append(prev)
        anchors = anchors[~anchors.isin(pd.DatetimeIndex(prev["anchor"].unique()))]
    chunks = [anchors[i:i + anchors_per_call] for i in range(0, len(anchors), anchors_per_call)]
    it = chunks
    if progress:
        try:
            from tqdm.auto import tqdm
            it = tqdm(chunks, desc="multivariate forecast chunks")
        except ImportError:
            pass
    new = []
    for ci, chunk in enumerate(it):
        meta, inp = [], []
        for a in chunk:
            tick, ctxs = multivariate_contexts(panels, eligible, a, ctx, stride)
            meta += [(a, t) for t in tick]
            inp += ctxs
        if not inp:
            continue
        n_series = len(inp) * len(names)
        if cross_learning and n_series > batch_size:
            raise ValueError(f"cross-section of {n_series} series exceeds batch_size={batch_size}: "
                             "it would be split into separate attention groups")
        kw = dict(cross_learning=True, batch_size=batch_size) if cross_learning else {}
        qs, _ = pipeline.predict_quantiles(inp, prediction_length=H, quantile_levels=list(quantiles), **kw)
        arr = np.stack([(q.numpy() if hasattr(q, "numpy") else np.asarray(q)) for q in qs])   # (n, V, H, Q)
        n, V = arr.shape[0], arr.shape[1]
        if V != len(names):
            raise ValueError(f"model returned {V} variates, expected {len(names)}")
        frame = pd.DataFrame(arr.reshape(n * V * H, len(quantiles)), columns=qcols)
        frame.insert(0, "h", np.tile(np.arange(1, H + 1), n * V))
        frame.insert(0, "variate", np.tile(np.repeat(names, H), n))
        frame.insert(0, "ticker", np.repeat([m[1] for m in meta], V * H))
        frame.insert(0, "anchor", np.repeat(pd.DatetimeIndex([m[0] for m in meta]), V * H))
        new.append(frame)
        if partial is not None and (ci + 1) % checkpoint_every == 0:
            pd.concat(done + new, ignore_index=True).to_parquet(partial)
    out = pd.concat(done + new, ignore_index=True) if (done or new) else pd.DataFrame()
    if out_path is not None and not out.empty:
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        out.to_parquet(out_path)
        if partial is not None and partial.exists():
            partial.unlink()
    return out
