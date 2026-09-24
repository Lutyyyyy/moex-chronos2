import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import n5_series as n5  # noqa: E402


def _bars(n_days=4, seed=0, beta=1.5):
    rng = np.random.default_rng(seed)
    cal = pd.bdate_range("2022-06-01", periods=n_days)
    ts = [d + pd.Timedelta(hours=10) + pd.Timedelta(minutes=10 * k) for d in cal for k in range(52)]
    m = np.cumsum(rng.normal(0, 0.002, len(ts)))
    a = beta * m                                                    # exactly β times the market
    b = np.cumsum(rng.normal(0, 0.003, len(ts)))
    rows = [pd.DataFrame({"ticker": t, "timestamp": ts, "close_adj": np.exp(x), "close": np.exp(x)})
            for t, x in (("MKT", m), ("A", a), ("B", b))]
    return pd.concat(rows, ignore_index=True), cal


def test_portfolio_rv_single_name_equals_realized_variance():
    bars, cal = _bars()
    R = n5.bar_returns(bars, cal)
    w = pd.DataFrame(0.0, cal, R.columns); w["B"] = 1.0
    ref = n5.al.realized_variance(bars, cal)["B"]
    got = n5.portfolio_rv(R, w)
    pd.testing.assert_series_equal(got.iloc[1:], ref.iloc[1:], check_names=False, check_freq=False, check_index_type=False)


def test_residual_rv_removes_the_factor():
    bars, cal = _bars()
    R = n5.bar_returns(bars[bars.ticker != "MKT"], cal)
    r_m = n5.bar_returns(bars[bars.ticker == "MKT"], cal)["MKT"]
    beta = pd.DataFrame({"A": 1.5, "B": 0.0}, index=cal)
    e = n5.residual_rv(R, r_m, beta)
    assert (e["A"].iloc[1:] < 1e-20).all()                          # A is exactly 1.5·market
    ref = n5.al.realized_variance(bars, cal)["B"]
    assert np.allclose(e["B"].iloc[1:], ref.iloc[1:])               # β = 0 leaves the total RV
    beta.iloc[2, 0] = np.nan
    assert np.isnan(n5.residual_rv(R, r_m, beta).iloc[2, 0])


def test_ew_weights_sum_to_one():
    e = pd.DataFrame([[True, True, False], [False, False, False]], columns=list("abc"))
    w = n5.ew_weights(e)
    assert w.iloc[0].sum() == pytest.approx(1.0) and w.iloc[1].isna().all()
