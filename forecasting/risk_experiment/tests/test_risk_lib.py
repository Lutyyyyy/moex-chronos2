import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import risk_lib as rl  # noqa: E402

U21 = np.array([0.01] + [round(0.05 * k, 2) for k in range(1, 20)] + [0.99])


def normal_grid(n=1, sigma=1.0):
    return np.tile(stats.norm.ppf(U21) * sigma, (n, 1))


def t_returns(n, df=5, seed=0):
    rng = np.random.default_rng(seed)
    return stats.t.rvs(df, size=n, random_state=rng) * 0.02


# ── quantile arithmetic ───────────────────────────────────────────────────────

def test_quantile_at_exact_on_grid_and_interpolates():
    Q = normal_grid(2)
    assert np.allclose(rl.quantile_at(Q, U21, 0.05), stats.norm.ppf(0.05))
    mid = rl.quantile_at(Q, U21, 0.075)[0]
    assert stats.norm.ppf(0.05) < mid < stats.norm.ppf(0.10)
    assert rl.quantile_at(Q, U21, 0.005, tail="flat")[0] == pytest.approx(stats.norm.ppf(0.01))
    assert rl.quantile_at(Q, U21, 0.005, tail="linear")[0] < stats.norm.ppf(0.01)


def test_es_from_quantiles_brackets_normal_truth():
    true_es = -stats.norm.pdf(stats.norm.ppf(0.05)) / 0.05          # -2.0627
    var_l, es_lin = rl.es_from_quantiles(normal_grid(), U21, 0.05, tail="linear")
    _, es_flat = rl.es_from_quantiles(normal_grid(), U21, 0.05, tail="flat")
    assert var_l[0] == pytest.approx(stats.norm.ppf(0.05))
    assert es_lin[0] < true_es < es_flat[0]                          # linear tail heavier, flat lighter
    assert abs(es_lin[0] / true_es - 1) < 0.01 and abs(es_flat[0] / true_es - 1) < 0.01


def test_es_below_first_level_and_scaling():
    _, es = rl.es_from_quantiles(normal_grid(sigma=2.0), U21, 0.01, tail="flat")
    assert es[0] == pytest.approx(2 * stats.norm.ppf(0.01))
    _, e1 = rl.es_from_quantiles(normal_grid(sigma=1.0), U21, 0.05)
    _, e3 = rl.es_from_quantiles(normal_grid(sigma=3.0), U21, 0.05)
    assert e3[0] == pytest.approx(3 * e1[0])


# ── scoring and backtests ─────────────────────────────────────────────────────

def test_fz0_minimized_by_true_var_es():
    a = 0.05
    y = t_returns(200_000, seed=1)
    q = stats.t.ppf(a, 5) * 0.02
    es = -0.02 * (stats.t.pdf(stats.t.ppf(a, 5), 5) / a) * (5 + stats.t.ppf(a, 5) ** 2) / 4   # t(5) ES
    base = np.nanmean(rl.fz0_loss(y, np.full_like(y, q), np.full_like(y, es), a))
    for k in (0.8, 1.2):
        assert base < np.nanmean(rl.fz0_loss(y, np.full_like(y, k * q), np.full_like(y, k * es), a))
    assert np.isnan(rl.fz0_loss(np.array([0.0]), np.array([-0.01]), np.array([0.01]), a)[0])   # ES >= 0 invalid


def test_kupiec_and_christoffersen():
    rng = np.random.default_rng(2)
    ok = rng.uniform(size=5000) < 0.05
    assert rl.kupiec(ok, 0.05)["p"] > 0.01
    assert rl.kupiec(rng.uniform(size=5000) < 0.10, 0.05)["p"] < 1e-6
    assert rl.christoffersen(ok, 0.05)["p_ind"] > 0.01
    clustered = np.zeros(5000, dtype=int)
    for s in rng.choice(4900, 50, replace=False):
        clustered[s:s + 5] = 1                                         # hits come in runs
    assert rl.christoffersen(clustered, 0.05)["p_ind"] < 1e-6


def test_acerbi_szekely_detects_underestimated_es():
    a, n = 0.05, 4000
    rng = np.random.default_rng(3)
    y = rng.normal(0, 0.02, n)
    Q = normal_grid(n, 0.02)
    var, es = rl.es_from_quantiles(Q, U21, a)
    z_ok = rl.acerbi_szekely_z2(y, var, es, a)
    assert abs(z_ok) < 0.15
    assert rl.acerbi_szekely_pvalue(Q, U21, var, es, a, z_ok, n_sim=300) > 0.05
    Qn = normal_grid(n, 0.014)                                          # forecast too narrow
    vn, en = rl.es_from_quantiles(Qn, U21, a)
    z_bad = rl.acerbi_szekely_z2(y, vn, en, a)
    assert z_bad < -0.3
    assert rl.acerbi_szekely_pvalue(Qn, U21, vn, en, a, z_bad, n_sim=300) < 0.01


def test_basel_traffic_light_zones():
    h = pd.Series([0] * 250)
    h.iloc[:4] = 1
    assert rl.basel_traffic_light(h)["zone"].iloc[-1] == "green"
    h.iloc[:7] = 1
    assert rl.basel_traffic_light(h)["zone"].iloc[-1] == "yellow"
    h.iloc[:12] = 1
    assert rl.basel_traffic_light(h)["zone"].iloc[-1] == "red"
    assert rl.basel_traffic_light(h)["zone"].iloc[:249].isna().all()


# ── regimes and conditional tests ─────────────────────────────────────────────

def _mkt(n=1500, seed=4):
    rng = np.random.default_rng(seed)
    x = np.cumsum(rng.normal(0, 0.05, n)) * 0.3 + rng.normal(0, 0.2, n)
    x[700:760] += 2.0                                                   # a vol shock
    return pd.Series(x - 9, index=pd.bdate_range("2019-01-01", periods=n))


def test_stress_indicator_is_causal_and_flags_shock():
    m = _mkt()
    s = rl.stress_indicator(m, 0.9)
    m2 = m.copy(); m2.iloc[1000:] += 5.0                                # change only the future
    s2 = rl.stress_indicator(m2, 0.9)
    pd.testing.assert_series_equal(s.iloc[:1000], s2.iloc[:1000])
    assert s.iloc[702:720].mean() > 0.8                                 # shock days flagged
    cal = rl.calibrate_stress_pct(m, m.index[300:], target=0.12)
    assert abs(cal["freq"] - 0.12) < 0.03


def test_giacomini_white_state_dependence():
    rng = np.random.default_rng(5)
    n = 2000
    idx = pd.RangeIndex(n)
    S = pd.Series((rng.uniform(size=n) < 0.15).astype(float), idx)
    lb = pd.Series(rng.normal(1, 0.3, n), idx)
    la = lb - 0.1 * (1 - S) + 0.2 * S + pd.Series(rng.normal(0, 0.05, n), idx)   # a better in calm, worse in stress
    H = pd.DataFrame({"const": 1.0, "stress": S})
    r = rl.giacomini_white(la, lb, H, lags=5)
    assert r["p"] < 1e-6
    assert r["coefs"].loc["const", "coef"] == pytest.approx(-0.1, abs=0.02)
    assert r["coefs"].loc["stress", "coef"] == pytest.approx(0.3, abs=0.03)
    null = rl.giacomini_white(lb + pd.Series(rng.normal(0, 0.05, n), idx), lb, H, lags=5)
    assert null["p"] > 0.01


# ── calibration / FHS ─────────────────────────────────────────────────────────

def _panel_returns(T=600, N=40, seed=6):
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2021-01-01", periods=T)
    sig = pd.DataFrame(np.exp(rng.normal(np.log(0.02), 0.3, (T, N))), dates, [f"S{i}" for i in range(N)])
    y = sig * rng.standard_normal((T, N))
    return y, sig, pd.DataFrame(True, dates, sig.columns)


def test_conformal_restores_coverage_of_misscaled_quantile():
    a = 0.05
    y, sig, mask = _panel_returns()
    q_bad = 0.7 * stats.norm.ppf(a) * sig                                # too narrow
    c = rl.conformal_quantile_scale(y, q_bad, mask, a, horizon=1)
    q_cal = q_bad.mul(c, axis=0)
    late = y.index[300:]
    raw_hit = (y.loc[late] < q_bad.loc[late]).to_numpy().mean()
    cal_hit = (y.loc[late] < q_cal.loc[late]).to_numpy().mean()
    assert raw_hit > 0.09 and abs(cal_hit - a) < 0.01
    assert c.iloc[300:].median() == pytest.approx(1 / 0.7, rel=0.05)


def test_conformal_scale_is_causal():
    a = 0.05
    y, sig, mask = _panel_returns()
    q = stats.norm.ppf(a) * sig
    c1 = rl.conformal_quantile_scale(y, q, mask, a, horizon=5)
    y2 = y.copy(); y2.iloc[400:] *= 10
    c2 = rl.conformal_quantile_scale(y2, q, mask, a, horizon=5)
    pd.testing.assert_series_equal(c1.iloc[:405], c2.iloc[:405])       # t uses only s <= t-5


def test_fhs_coverage_with_true_sigma():
    a = 0.05
    y, sig, mask = _panel_returns()
    var, es = rl.fhs_var_es(y / sig, sig, mask, a, horizon=1)
    late = y.index[300:]
    assert abs((y.loc[late] < var.loc[late]).to_numpy().mean() - a) < 0.01
    assert (es.loc[late] < var.loc[late]).to_numpy().all()


# ── mixtures ──────────────────────────────────────────────────────────────────

def _vol_panel(T=700, N=30, seed=7):
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2021-01-01", periods=T)
    cols = [f"S{i}" for i in range(N)]
    F1 = pd.DataFrame(np.exp(rng.normal(-8, 0.5, (T, N))), dates, cols)
    F2 = pd.DataFrame(np.exp(rng.normal(-8, 0.5, (T, N))), dates, cols)
    truth = np.exp(0.7 * np.log(F1) + 0.3 * np.log(F2))
    y = truth * rng.gamma(4.0, 0.25, (T, N))                             # E[noise] = 1 -> QLIKE optimum = truth
    return y, F1, F2, pd.DataFrame(True, dates, cols)


def test_fit_vol_mix_recovers_planted_weights():
    y, F1, F2, mask = _vol_panel()
    logF = np.stack([np.log(F1.to_numpy().ravel()), np.log(F2.to_numpy().ravel())], axis=1)
    p = rl.fit_vol_mix(logF, y.to_numpy().ravel())
    assert p[0] == pytest.approx(0.7, abs=0.03) and p[1] == pytest.approx(0.3, abs=0.03)
    assert abs(p[2]) < 0.05


def test_rolling_mixture_is_causal_and_regime_splits():
    y, F1, F2, mask = _vol_panel()
    comb, wt = rl.rolling_mixture("vol", {"a": F1, "b": F2}, y, mask, horizon=5, window=200, refit_every=21, min_obs=500)
    y2 = y.copy(); y2.iloc[450:] *= 50
    comb2, _ = rl.rolling_mixture("vol", {"a": F1, "b": F2}, y2, mask, horizon=5, window=200, refit_every=21, min_obs=500)
    pd.testing.assert_frame_equal(comb.iloc[:455], comb2.iloc[:455])
    assert wt["a"].iloc[-1] == pytest.approx(0.7, abs=0.08)
    state = pd.Series((np.arange(len(y)) % 7 == 0).astype(float), y.index)
    _, wts = rl.rolling_mixture("vol", {"a": F1, "b": F2}, y, mask, horizon=5, window=300, refit_every=21,
                                min_obs=500, state=state)
    assert set(wts["state"]) == {0.0, 1.0}


def test_vares_mixture_prefers_calibrated_component():
    a = 0.05
    y, sig, mask = _panel_returns(T=500, N=40, seed=8)
    good = (stats.norm.ppf(a) * sig, -stats.norm.pdf(stats.norm.ppf(a)) / a * sig)
    bad = (0.5 * good[0], 0.5 * good[1])
    V = np.stack([good[0].to_numpy().ravel(), bad[0].to_numpy().ravel()], 1)
    E = np.stack([good[1].to_numpy().ravel(), bad[1].to_numpy().ravel()], 1)
    p = rl.fit_vares_mix(V, E, y.to_numpy().ravel(), a, scale=False)
    assert p[0] > 0.8


# ── portfolio uses ────────────────────────────────────────────────────────────

def test_gmv_weights_properties():
    rng = np.random.default_rng(9)
    A = rng.normal(size=(20, 20))
    cov = A @ A.T / 20 + np.eye(20) * 0.1
    w = rl.gmv_weights(cov, long_only=True)
    assert w.sum() == pytest.approx(1) and (w >= -1e-12).all()
    wu = rl.gmv_weights(cov, long_only=False)
    inv1 = np.linalg.solve(cov, np.ones(20))
    assert np.allclose(wu, inv1 / inv1.sum())
    assert wu @ cov @ wu <= w @ cov @ w + 1e-12


def test_oracle_vol_gives_lower_gmv_variance_than_noisy():
    rng = np.random.default_rng(10)
    N, T = 25, 400
    R = np.full((N, N), 0.3) + np.eye(N) * 0.7
    Lc = np.linalg.cholesky(R)
    real_true, real_noisy = [], []
    for _ in range(T):
        v = np.exp(rng.normal(np.log(4e-4), 0.6, N))
        r = np.sqrt(v) * (Lc @ rng.standard_normal(N))
        w_t = rl.gmv_weights(rl.drd_cov(v, R))
        w_n = rl.gmv_weights(rl.drd_cov(v * np.exp(rng.normal(0, 0.8, N)), R))
        real_true.append(w_t @ r); real_noisy.append(w_n @ r)
    assert np.var(real_true) < np.var(real_noisy)


def test_fko_fee():
    rng = np.random.default_rng(11)
    b = pd.Series(rng.normal(0.001, 0.02, 3000))
    assert rl.fko_performance_fee(b, b, 5, 52)["delta"] == pytest.approx(0, abs=1e-12)
    a = 0.5 * (b - b.mean()) + b.mean()                                  # paired: same mean, half the vol
    f = rl.fko_performance_fee(a, b, 5, 52)
    assert f["delta"] > 0 and f["fee_bps_annual"] > 0
    assert rl.fko_fee_bootstrap(a, b, 5, 52, n_boot=200)["p_one_sided"] < 0.05


def test_hedge_and_vol_target():
    rng = np.random.default_rng(12)
    f = rng.normal(0, 0.02, 5000)
    s = 0.8 * f + rng.normal(0, 0.005, 5000)
    rho = np.corrcoef(s, f)[0, 1]
    h = rl.hedge_ratio(rho, s.std(), f.std())
    assert h == pytest.approx(0.8, abs=0.02)
    assert rl.hedge_effectiveness(s, s - h * f) > 0.9
    lev = rl.vol_target_leverage(pd.Series([0.05, 0.10, 0.20]), 0.10, cap=1.5)
    assert list(lev) == [1.5, 1.0, 0.5]
