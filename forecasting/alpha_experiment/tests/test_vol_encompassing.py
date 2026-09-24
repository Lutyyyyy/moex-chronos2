import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from vol_encompassing import encompassing, ols_driscoll_kraay  # noqa: E402


def _panel(T=300, N=40, seed=0):
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2021-01-01", periods=T)
    cols = [f"S{i}" for i in range(N)]
    common = rng.normal(size=(T, 1))                     # date effect -> cross-sectional correlation
    x1 = pd.DataFrame(rng.normal(size=(T, N)) + common, dates, cols)
    x2 = pd.DataFrame(0.7 * x1.to_numpy() + rng.normal(size=(T, N)), dates, cols)
    return dates, cols, common, x1, x2, rng


def test_dk_recovers_coefficients_and_matches_ols():
    dates, cols, common, x1, x2, rng = _panel()
    shock = rng.normal(size=(len(dates), 1))             # date effect in the error, independent of x
    y = 0.5 + 1.0 * x2 + 0.0 * x1 + pd.DataFrame(rng.normal(size=x1.shape) + shock, dates, cols)
    r = ols_driscoll_kraay(y.stack(), pd.DataFrame({"x1": x1.stack(), "x2": x2.stack()}), lags=8)
    assert abs(r.loc["x2", "coef"] - 1.0) < 0.05
    assert abs(r.loc["x1", "t"]) < 3                     # encompassed forecast gets no weight
    assert r.loc["x2", "t"] > 10


def test_dk_se_wider_than_iid_under_date_effects():
    dates, cols, common, x1, x2, rng = _panel(seed=1)
    y = x1 + pd.DataFrame(np.repeat(rng.normal(size=(len(dates), 1)) * 3, len(cols), 1), dates, cols)
    X = pd.DataFrame({"x1": x1.stack()})
    dk = ols_driscoll_kraay(y.stack(), X, lags=0)
    A = np.column_stack([np.ones(len(X)), X.to_numpy()])
    e = y.stack().to_numpy() - A @ dk["coef"].to_numpy()
    iid = np.sqrt(np.diag(np.linalg.inv(A.T @ A) * e.var()))
    assert dk.loc["const", "se"] > 3 * iid[0]            # common shocks inflate the intercept s.e.


def test_encompassing_respects_mask_and_dates():
    dates, cols, common, x1, x2, rng = _panel(seed=2)
    y = x1 + 0.1 * pd.DataFrame(rng.normal(size=x1.shape), dates, cols)
    mask = pd.DataFrame(True, dates, cols)
    y_bad = y.copy(); y_bad.iloc[:, :5] = 1e6            # garbage in masked-out names
    mask.iloc[:, :5] = False
    r = encompassing(y_bad, {"a": x1, "b": x2}, mask, dates[10:], lags=4)
    assert abs(r.loc["a", "coef"] - 1.0) < 0.02
