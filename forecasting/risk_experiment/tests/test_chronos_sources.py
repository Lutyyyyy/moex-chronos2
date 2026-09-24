import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import chronos_sources as cs  # noqa: E402


class FakePipe:
    """Mimics Chronos2Pipeline.predict_quantiles for 1-D/2-D inputs: every quantile of every step of
    variate v equals that variate's LAST context value (so tests can check alignment), and records
    the calls."""
    def __init__(self):
        self.calls = []

    def predict_quantiles(self, inputs, prediction_length, quantile_levels, **kw):
        self.calls.append(dict(n=len(inputs), kw=kw, shapes=[np.shape(x) for x in inputs]))
        out = []
        for x in inputs:
            x = np.atleast_2d(x)
            out.append(np.repeat(x[:, -1][:, None, None], prediction_length, 1).repeat(len(quantile_levels), 2))
        return out, None


def _panels(T=400, N=5, seed=0):
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2023-01-02", periods=T)
    cols = [f"S{i}" for i in range(N)]
    ret = pd.DataFrame(rng.normal(0, 0.02, (T, N)), dates, cols)
    rv = pd.DataFrame(np.exp(rng.normal(-8, 0.5, (T, N))), dates, cols)
    ret.iloc[10:15, 0] = np.nan; rv.iloc[10:15, 0] = np.nan          # a stale stretch
    elig = pd.DataFrame(True, dates, cols)
    elig.iloc[:, 4] = False                                          # never eligible
    return ret, rv, elig


def test_rv_panels_block_sums():
    ret, rv, _ = _panels()
    p = cs.rv_panels(ret, rv, block=5)
    d = ret.index[100]
    assert p["ret"].loc[d, "S1"] == pytest.approx(ret["S1"].iloc[96:101].sum())
    assert p["logrv"].loc[d, "S1"] == pytest.approx(np.log(rv["S1"].iloc[96:101].sum() + cs.RV_EPS))


def test_contexts_are_2d_aligned_and_causal():
    ret, rv, elig = _panels()
    P = cs.rv_panels(ret, rv)
    a = ret.index[300]
    tick, ctx = cs.multivariate_contexts(P, elig, a, ctx=250)
    assert tick == ["S0", "S1", "S2", "S3"]                          # S4 not eligible
    x = ctx[tick.index("S1")]
    assert x.shape == (2, 250)
    assert x[0, -1] == pytest.approx(ret.loc[a, "S1"]) and x[1, -1] == pytest.approx(np.log(rv.loc[a, "S1"] + cs.RV_EPS))
    P2 = {k: v.copy() for k, v in P.items()}
    for v in P2.values():
        v.iloc[301:] = 99.0                                          # future values must not matter
    _, ctx2 = cs.multivariate_contexts(P2, elig, a, ctx=250)
    assert all(np.array_equal(u, w) for u, w in zip(ctx, ctx2))


def test_contexts_stride_ends_at_anchor():
    ret, rv, elig = _panels()
    P = cs.rv_panels(ret, rv, block=5)
    a = ret.index[350]
    tick, ctx = cs.multivariate_contexts(P, elig, a, ctx=40, stride=5)
    x = ctx[tick.index("S2")]
    assert x.shape == (2, 40)
    assert x[0, -1] == pytest.approx(P["ret"].loc[a, "S2"])
    assert x[0, -2] == pytest.approx(P["ret"].loc[ret.index[345], "S2"])   # previous non-overlapping block


def test_generate_multivariate_layout_and_guards():
    ret, rv, elig = _panels()
    P = cs.rv_panels(ret, rv)
    pipe = FakePipe()
    anchors = ret.index[300:303]
    out = cs.generate_multivariate(pipe, P, elig, anchors, ctx=250, H=5, progress=False)
    assert len(pipe.calls) == 3 and all(c["kw"].get("cross_learning") for c in pipe.calls)   # one anchor per call
    assert set(out["variate"]) == {"ret", "logrv"} and out["h"].max() == 5
    row = out[(out.anchor == anchors[0]) & (out.ticker == "S3") & (out.variate == "logrv") & (out.h == 1)]
    assert row["q0.5"].iloc[0] == pytest.approx(np.log(rv.loc[anchors[0], "S3"] + cs.RV_EPS))
    row = out[(out.anchor == anchors[0]) & (out.ticker == "S3") & (out.variate == "ret") & (out.h == 3)]
    assert row["q0.5"].iloc[0] == pytest.approx(ret.loc[anchors[0], "S3"])
    with pytest.raises(ValueError):
        cs.generate_multivariate(pipe, P, elig, anchors, ctx=250, H=5, anchors_per_call=2, progress=False)
    with pytest.raises(ValueError):
        cs.generate_multivariate(pipe, P, elig, anchors[:1], ctx=250, H=5, batch_size=4, progress=False)


def test_holdout_lock():
    ret, rv, elig = _panels()
    P = cs.rv_panels(ret, rv)
    late = pd.DatetimeIndex(["2025-01-02"])
    elig2 = pd.concat([elig, pd.DataFrame(True, late, elig.columns)])
    with pytest.raises(AssertionError):
        cs.generate_multivariate(FakePipe(), P, elig2, late, ctx=250, H=5, progress=False)
