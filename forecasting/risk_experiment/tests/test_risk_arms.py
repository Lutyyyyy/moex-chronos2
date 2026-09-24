import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import risk_arms as ra  # noqa: E402


def test_t_var_es_matches_simulation():
    nu, sig, a = 5.0, 0.02, 0.05
    S = pd.DataFrame([[sig]]); N = pd.DataFrame([[nu]])
    v, e = ra.t_var_es(S, N, a)
    x = stats.t.rvs(nu, size=2_000_000, random_state=np.random.default_rng(0)) * np.sqrt((nu - 2) / nu) * sig
    q = np.quantile(x, a)
    assert v.iat[0, 0] == pytest.approx(q, rel=0.01)
    assert e.iat[0, 0] == pytest.approx(x[x <= q].mean(), rel=0.01)
    assert x.std() == pytest.approx(sig, rel=0.01)                      # unit-variance scaling


def test_normal_var_es():
    v, e = ra.normal_var_es(pd.DataFrame([[1.0]]), 0.05)
    assert v.iat[0, 0] == pytest.approx(stats.norm.ppf(0.05))
    assert e.iat[0, 0] == pytest.approx(-stats.norm.pdf(stats.norm.ppf(0.05)) / 0.05)


def test_hs_is_causal():
    rng = np.random.default_rng(1)
    ret = pd.DataFrame(rng.normal(0, 0.02, (400, 2)), pd.bdate_range("2021-01-01", periods=400), ["A", "B"])
    v, e = ra.hs_var_es(ret, 0.05)
    r2 = ret.copy(); r2.iloc[300:] = -1.0
    v2, e2 = ra.hs_var_es(r2, 0.05)
    pd.testing.assert_frame_equal(v.iloc[:300], v2.iloc[:300]); pd.testing.assert_frame_equal(e.iloc[:300], e2.iloc[:300])
    assert (e.dropna() < v.dropna()).all().all()


def test_chronos_vares_alignment():
    cal = pd.bdate_range("2022-01-03", periods=3)
    U = np.asarray(ra.al.NATIVE_QUANTILES)
    rows = []
    for d in cal:
        for t, sig in (("A", 0.01), ("B", 0.03)):
            for h in (1, 2):
                rows.append({"anchor": d, "ticker": t, "h": h, **{c: stats.norm.ppf(u) * sig * h for c, u in zip(ra.QCOLS, U)}})
    out = ra.chronos_vares(pd.DataFrame(rows), [0.05], cal, ["A", "B"], h=1)
    V, E = out[0.05]
    assert V.loc[cal[1], "B"] == pytest.approx(stats.norm.ppf(0.05) * 0.03)
    assert (E < V).all().all()


def test_portfolio_paths_share_and_scale_invariance():
    rng = np.random.default_rng(2)
    dates = pd.bdate_range("2022-01-03", periods=30); cols = [f"S{i}" for i in range(12)]
    V = pd.DataFrame(np.exp(rng.normal(-7, 0.4, (30, 12))), dates, cols)
    R5 = pd.DataFrame(rng.normal(0, 0.03, (30, 12)), dates, cols)
    C = pd.DataFrame(np.eye(12) * 0.7 + 0.3, cols, cols)
    corr = {d: C for d in dates}
    U = pd.DataFrame(True, dates, cols)
    rf5 = pd.Series(0.001, dates)
    arms = {"a": V, "a_cal": V * 3.0}
    shared = ra.portfolio_paths(arms, corr, R5, rf5, U, dates, 0.02, gmv_share={"a_cal": "a"})
    solved = ra.portfolio_paths(arms, corr, R5, rf5, U, dates, 0.02)
    pd.testing.assert_series_equal(shared["a_cal"]["gmv"], solved["a_cal"]["gmv"], check_names=False, atol=1e-10)
    assert not np.allclose(solved["a"]["vt_exposure"], solved["a_cal"]["vt_exposure"])   # vol targeting is level-sensitive
