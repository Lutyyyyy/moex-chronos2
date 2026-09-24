"""Unit tests + harness canaries for alpha_lib. Run: python3 -m pytest forecasting/alpha_experiment/tests -q"""
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from scipy import stats as sstats

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import alpha_lib as al  # noqa: E402


# ─── quantile moments ─────────────────────────────────────────────────────────

def test_quantile_moments_exact_for_uniform_linear_tails():
    u = np.array(al.NATIVE_QUANTILES)
    a, b = -0.03, 0.06                       # X ~ U(a, a+b): Q(u) = a + b u
    m, v = al.quantile_moments(a + b * u, u, tail="linear")
    assert m == pytest.approx(a + b / 2, abs=1e-12)
    assert v == pytest.approx(b ** 2 / 12, rel=1e-9)


def test_quantile_moments_normal_close_and_flat_tail_smaller():
    u = np.array(al.NATIVE_QUANTILES)
    Q = 0.001 + 0.02 * sstats.norm.ppf(u)
    m_lin, v_lin = al.quantile_moments(Q, u, tail="linear")
    m_flat, v_flat = al.quantile_moments(Q, u, tail="flat")
    assert m_lin == pytest.approx(0.001, abs=1e-6) and m_flat == pytest.approx(0.001, abs=1e-6)
    assert v_flat < v_lin
    assert math.sqrt(v_lin) == pytest.approx(0.02, rel=0.06)
    assert math.sqrt(v_flat) == pytest.approx(0.02, rel=0.10)


def test_quantile_moments_vectorized_shape():
    u = np.array(al.NATIVE_QUANTILES)
    Q = np.tile(sstats.norm.ppf(u), (3, 4, 1))
    m, v = al.quantile_moments(Q, u)
    assert m.shape == (3, 4) and v.shape == (3, 4)


def test_chronos_features_sums_steps():
    u = al.NATIVE_QUANTILES
    rows = []
    for h in range(1, 7):
        q = 0.001 * h + 0.01 * sstats.norm.ppf(u)
        rows.append({"anchor": pd.Timestamp("2022-01-10"), "ticker": "A", "h": h,
                     **{f"q{x:g}": y for x, y in zip(u, q)}})
    f = al.chronos_features(pd.DataFrame(rows), steps=(2, 3, 4, 5, 6)).loc[(pd.Timestamp("2022-01-10"), "A")]
    assert f["MED"] == pytest.approx(0.001 * (2 + 3 + 4 + 5 + 6), abs=1e-9)
    _, v1 = al.quantile_moments(0.01 * sstats.norm.ppf(u), u)
    assert f["SIG"] == pytest.approx(math.sqrt(5 * v1), rel=1e-9)
    assert f["SIG1"] == pytest.approx(math.sqrt(v1), rel=1e-9)
    assert f["SKEW1"] == pytest.approx(0.0, abs=1e-9)


# ─── panel construction ───────────────────────────────────────────────────────

def _bars(day, ticker, times_prices):
    return pd.DataFrame({"ticker": ticker, "timestamp": [pd.Timestamp(f"{day} {t}") for t, _ in times_prices],
                         "close_adj": [p for _, p in times_prices], "close": [p for _, p in times_prices],
                         "value": 1.0})


def test_main_session_close_ignores_evening_and_morning():
    b = _bars("2024-03-04", "A", [("07:00", 90), ("09:50", 99), ("10:00", 100), ("18:40", 101), ("19:00", 105),
                                  ("23:40", 110)])
    c = al.main_session_close(b)
    assert c.loc[pd.Timestamp("2024-03-04"), "A"] == 101


def _session(day, ticker, n_bars, price=1.0):
    """n_bars 10m bars from 10:00 (price constant)."""
    ts = pd.date_range(f"{day} 10:00", periods=n_bars, freq="10min")
    return _bars(day, ticker, [(t.strftime("%H:%M"), price) for t in ts])


def test_trading_calendar_keeps_short_sessions_and_working_saturdays():
    idx = pd.concat([_session("2024-03-04", "IMOEX", 54),     # Mon full
                     _session("2022-03-24", "IMOEX", 23),     # 2022 reopening short session: kept
                     _session("2024-03-05", "IMOEX", 5),      # fragment: dropped
                     _session("2024-04-27", "IMOEX", 54)])    # official working Saturday: kept
    cal = al.trading_calendar(idx)
    assert list(cal) == [pd.Timestamp("2022-03-24"), pd.Timestamp("2024-03-04"), pd.Timestamp("2024-04-27")]


def test_realized_variance_includes_overnight_term():
    b = pd.concat([_bars("2024-03-04", "A", [("10:00", 100.0), ("18:40", 101.0), ("23:40", 130.0)]),
                   _bars("2024-03-05", "A", [("09:50", 102.0), ("18:40", 100.0)])])
    cal = pd.DatetimeIndex(["2024-03-04", "2024-03-05"])
    rv = al.realized_variance(b, cal)
    expect = math.log(102 / 101) ** 2 + math.log(100 / 102) ** 2   # evening 23:40 print ignored
    assert rv.loc[pd.Timestamp("2024-03-05"), "A"] == pytest.approx(expect)
    assert rv.loc[pd.Timestamp("2024-03-04"), "A"] == pytest.approx(math.log(101 / 100) ** 2)


def test_pit_universe_history_liquidity_stale():
    idx = pd.bdate_range("2022-01-03", periods=10)
    ret = pd.DataFrame({"A": 0.01, "B": np.r_[[np.nan] * 5, [0.01] * 5]}, index=idx)
    val = pd.DataFrame({"A": 100.0, "B": 1.0}, index=idx)
    stale = pd.DataFrame(False, index=idx, columns=["A", "B"]); stale.iloc[-1, 0] = True
    e = al.pit_universe(ret, val, stale, min_history=3, min_median_value=10, value_window=2)
    assert e["A"].iloc[3] and not e["A"].iloc[1] and not e["A"].iloc[-1]
    assert not e["B"].any()


# ─── portfolio construction ───────────────────────────────────────────────────

def test_ls_rank_dollar_and_beta_neutral():
    rng = np.random.default_rng(1)
    idx = pd.bdate_range("2022-01-03", periods=3); cols = [f"T{i}" for i in range(20)]
    sig = pd.DataFrame(rng.standard_normal((3, 20)), idx, cols)
    elig = pd.DataFrame(True, idx, cols); elig.iloc[0, :3] = False
    betas = pd.DataFrame(rng.uniform(0.5, 1.5, (3, 20)), idx, cols)
    W = al.w_ls_rank(sig, elig, betas=betas)
    assert np.allclose(W.sum(axis=1), 0, atol=1e-12)
    assert np.allclose(W.abs().sum(axis=1), 1)
    assert np.allclose((W * betas).sum(axis=1), 0, atol=1e-12)
    assert (W.iloc[0, :3] == 0).all()


def test_lo_topq_and_equal():
    idx = pd.bdate_range("2022-01-03", periods=2); cols = [f"T{i}" for i in range(20)]
    sig = pd.DataFrame(np.tile(np.arange(20.0), (2, 1)), idx, cols)
    W = al.w_lo_topq(sig, pd.DataFrame(True, idx, cols), q=0.2)
    assert np.allclose(W.sum(axis=1), 1) and (W.iloc[0, -4:] == 0.25).all()
    assert np.allclose(al.w_equal(pd.DataFrame(True, idx, cols)).sum(axis=1), 1)


# ─── backtest mechanics ───────────────────────────────────────────────────────

def test_backtest_exec_lag_timing_and_costs():
    idx = pd.bdate_range("2022-01-03", periods=6)
    R = pd.DataFrame({"A": [0.0, 0.10, 0.20, 0.30, 0.40, 0.50]}, idx)
    W = pd.DataFrame({"A": [1.0] + [np.nan] * 5}, idx)             # one book decided at close of day 0
    bt0 = al.run_backtest(W, R, exec_lag=0, n_tranches=1, cost_bps=10)
    bt1 = al.run_backtest(W, R, exec_lag=1, n_tranches=1, cost_bps=10)
    assert bt0["gross"].iloc[1] == pytest.approx(0.10)             # lag 0: earns day-1 return
    assert bt1["gross"].iloc[1] == 0 and bt1["gross"].iloc[2] == pytest.approx(0.20)  # lag 1: from day 2
    assert bt1["cost"].iloc[1] == pytest.approx(1e-3) and bt1["turnover"].iloc[1] == pytest.approx(1.0)
    # drift: after day 2 the position is worth 1.2, so day-3 gross = 1.2 * 0.30
    assert bt1["gross"].iloc[3] == pytest.approx(1.2 * 0.30)


def test_backtest_borrow_and_staggering():
    idx = pd.bdate_range("2022-01-03", periods=12)
    R = pd.DataFrame({"A": 0.0, "B": 0.0}, idx)
    W = pd.DataFrame({"A": 0.5, "B": -0.5}, idx)
    bt = al.run_backtest(W, R, exec_lag=0, n_tranches=5, borrow_annual=0.252)
    # after all 5 tranches are in (day 4), short notional 0.5 -> borrow 0.5 * 0.252 / 252 per day
    assert bt["borrow"].iloc[6] == pytest.approx(0.5e-3)
    assert bt["short_exp"].iloc[6] == pytest.approx(0.5)
    assert bt["turnover"].iloc[:5].sum() == pytest.approx(1.0)       # each tranche enters once (1/5 each)
    assert bt["turnover"].iloc[5:].sum() == pytest.approx(0.0)       # zero returns -> no drift -> no trades


# ─── statistics ───────────────────────────────────────────────────────────────

def test_ic_series_matches_scipy():
    rng = np.random.default_rng(2)
    idx = pd.bdate_range("2022-01-03", periods=4); cols = [f"T{i}" for i in range(15)]
    s = pd.DataFrame(rng.standard_normal((4, 15)), idx, cols); f = pd.DataFrame(rng.standard_normal((4, 15)), idx, cols)
    f.iloc[1, 2] = np.nan
    ic = al.ic_series(s, f, pd.DataFrame(True, idx, cols))
    m = f.iloc[1].notna()
    assert ic.iloc[1] == pytest.approx(sstats.spearmanr(s.iloc[1][m], f.iloc[1][m])[0])


def test_nw_tstat_lag0_is_plain_t():
    x = np.random.default_rng(3).standard_normal(200) + 0.1
    r = al.nw_tstat(x, 0)
    assert r["t"] == pytest.approx(x.mean() / (x.std(ddof=0) / math.sqrt(200)))


def test_deflated_sharpe_single_trial_is_psr():
    assert al.deflated_sharpe(0.1, 101, 1, 0.0) == pytest.approx(sstats.norm.cdf(0.1 * 10 / math.sqrt(1 + 0.5 * 0.01)))
    assert al.deflated_sharpe(0.1, 101, 100, 0.01) < al.deflated_sharpe(0.1, 101, 1, 0.01)


def test_fama_macbeth_recovers_known_slope():
    rng = np.random.default_rng(4)
    idx = pd.bdate_range("2022-01-03", periods=200); cols = [f"T{i}" for i in range(40)]
    x = pd.DataFrame(rng.standard_normal((200, 40)), idx, cols)
    elig = pd.DataFrame(True, idx, cols)
    z = al.xs_standardize(x, elig)
    y = 0.01 * z + 0.01 * pd.DataFrame(rng.standard_normal((200, 40)), idx, cols)
    fm = al.fama_macbeth(y, {"x": x}, elig, lags=0)
    assert fm.loc["x", "mean"] == pytest.approx(0.01, rel=0.05) and fm.loc["x", "t"] > 20


def test_qlike_minimized_at_truth_and_scale():
    rv = np.array([1.0, 2.0, 0.5])
    assert al.qlike(rv, rv).sum() == pytest.approx(0)
    assert al.qlike(rv, 1.3 * rv).sum() > 0 and al.qlike(rv, 0.7 * rv).sum() > 0


def test_har_has_no_lookahead():
    rng = np.random.default_rng(5)
    idx = pd.bdate_range("2021-01-04", periods=400)
    x = pd.DataFrame({"A": rng.chisquare(1, 400) * 1e-4}, idx)
    f1 = al.vol_har(x, x, steps=range(1, 6), refit_every=21, min_train=100)
    x2 = x.copy(); x2.iloc[300:] *= 50                                 # change the future only
    f2 = al.vol_har(x2, x2, steps=range(1, 6), refit_every=21, min_train=100)
    d = idx[299]
    assert f1.loc[:d].equals(f2.loc[:d])


def test_garch_positive_and_tracks_variance():
    rng = np.random.default_rng(6)
    n = 400; r = np.zeros(n); s2 = 1e-4
    for i in range(1, n):
        s2 = 2e-6 + 0.1 * r[i - 1] ** 2 + 0.85 * s2
        r[i] = math.sqrt(s2) * rng.standard_normal()
    ret = pd.DataFrame({"A": r}, pd.bdate_range("2021-01-04", periods=n))
    g = al.vol_garch(ret, steps=range(1, 6), refit_every=50, min_obs=250)
    v = g["A"].dropna()
    assert len(v) > 100 and (v > 0).all()


def test_classic_mom_skips_last_month():
    idx = pd.bdate_range("2020-01-02", periods=300)
    ret = pd.DataFrame({"A": 0.0}, idx); ret.iloc[-5:] = 1.0            # recent month move
    s = al.classic_signals(ret, pd.DataFrame({"A": 1.0}, idx))
    assert s["mom_12_1"]["A"].iloc[-1] == 0.0 and s["rev_5d"]["A"].iloc[-1] == -5.0


# ─── forecast generation (fake pipeline) ──────────────────────────────────────

class FakePipe:
    """Returns quantiles = last context value + N(0,1) quantile * 0.01, per series."""
    def __init__(self):
        self.calls = 0

    def predict_quantiles(self, inputs, prediction_length, quantile_levels, **kw):
        import torch
        self.calls += 1; self.kw = kw; self.last_inputs = inputs
        z = sstats.norm.ppf(quantile_levels)
        tgt = [x["target"] if isinstance(x, dict) else x for x in inputs]
        out = [torch.tensor(np.tile(x[-1] + 0.01 * z, (1, prediction_length, 1)), dtype=torch.float32) for x in tgt]
        return out, [o[..., len(quantile_levels) // 2] for o in out]


def _toy_panel(n=300, k=5, start="2023-01-02"):
    idx = pd.bdate_range(start, periods=n)
    ret = pd.DataFrame(np.random.default_rng(7).standard_normal((n, k)) * 0.01, idx, [f"T{i}" for i in range(k)])
    return ret, pd.DataFrame(True, idx, ret.columns)


def test_generate_forecasts_shape_and_alignment(tmp_path):
    ret, elig = _toy_panel()
    anchors = ret.index[260:270]
    out = al.generate_forecasts(FakePipe(), ret, elig, anchors, ctx=250, H=6, out_path=tmp_path / "p.parquet",
                                progress=False)
    assert len(out) == 10 * 5 * 6
    row = out[(out.anchor == anchors[3]) & (out.ticker == "T2") & (out.h == 1)].iloc[0]
    assert row["q0.5"] == pytest.approx(ret.loc[anchors[3], "T2"], abs=1e-6)   # context ends AT the anchor
    assert (tmp_path / "p.parquet").exists()


def test_generate_forecasts_holdout_lock():
    ret, elig = _toy_panel(start="2024-01-02")
    anchors = ret.index[ret.index >= al.HOLDOUT_START][:2]
    with pytest.raises(AssertionError, match="holdout locked"):
        al.generate_forecasts(FakePipe(), ret, elig, anchors, progress=False)


def test_generate_forecasts_resume(tmp_path):
    ret, elig = _toy_panel()
    anchors = ret.index[260:268]
    p = tmp_path / "p.parquet"
    first = al.generate_forecasts(FakePipe(), ret, elig, anchors[:4], ctx=250, H=6, progress=False)
    first.to_parquet(str(p) + ".partial.parquet")
    pipe = FakePipe()
    out = al.generate_forecasts(pipe, ret, elig, anchors, ctx=250, H=6, out_path=p, anchors_per_call=4,
                                progress=False)
    assert pipe.calls == 1 and out["anchor"].nunique() == 8


# ─── harness canaries ─────────────────────────────────────────────────────────

def test_canary_planted_signal_recovered():
    ret, sig = al.make_planted_panel(n_dates=800, n_tickers=60, ic=0.08, seed=11)
    elig = pd.DataFrame(True, ret.index, ret.columns)
    fwd = al.forward_returns(ret, range(1, 6))
    ic = al.ic_series(sig, fwd, elig)
    expected = 6 / math.pi * math.asin(0.08 / 2)                     # Spearman of a Pearson-0.08 pair
    assert ic.mean() == pytest.approx(expected, abs=0.012)
    bt = al.run_backtest(al.w_ls_rank(sig, elig), np.expm1(ret), exec_lag=0)
    assert al.perf_stats(bt["gross"])["sharpe"] > 2


def test_canary_leak_and_lagged_leak():
    ret, _ = al.make_planted_panel(n_dates=600, n_tickers=40, ic=0.0, seed=12)
    elig = pd.DataFrame(True, ret.index, ret.columns)
    fwd = al.forward_returns(ret, range(1, 6))
    leak = al.run_backtest(al.w_ls_rank(fwd, elig), np.expm1(ret), exec_lag=0)
    assert al.perf_stats(leak["gross"])["sharpe"] > 10               # the harness would expose a leak
    stale = al.run_backtest(al.w_ls_rank(fwd.shift(6), elig), np.expm1(ret), exec_lag=0)
    assert abs(al.perf_stats(stale["gross"])["sharpe"]) < 1.5


def test_canary_random_signal_and_permutation_null():
    ret, _ = al.make_planted_panel(n_dates=500, n_tickers=40, ic=0.0, seed=13)
    rnd = pd.DataFrame(np.random.default_rng(14).standard_normal(ret.shape), ret.index, ret.columns)
    elig = pd.DataFrame(True, ret.index, ret.columns)
    fwd = al.forward_returns(ret, range(1, 6))
    ic = al.ic_series(rnd, fwd, elig)
    assert abs(al.nw_tstat(ic, 8)["t"]) < 3
    null = al.ic_permutation_null(rnd, fwd, elig, n_perm=200)
    assert abs(null.mean()) < 0.003 and null.std() > 0


def test_build_daily_panel_drops_index_only_day():
    days = pd.bdate_range("2022-01-03", periods=6)
    idx = pd.concat([_session(d.date(), "IMOEX", 54) for d in days])
    sh = pd.concat([_bars(d.date(), t, [("10:00", 100.0 + i), ("18:40", 100.0 + i)])
                    for i, d in enumerate(days) if i != 3 for t in ["A", "B", "C"]])   # day 3: no share prints
    P = al.build_daily_panel(sh, idx)
    assert days[3] not in P["calendar"] and len(P["calendar"]) == 5
    assert P["ret"].loc[days[4], "A"] == pytest.approx(math.log(104 / 102))            # return spans the gap


def test_rearrange_quantiles_sorts_and_counts():
    u = al.NATIVE_QUANTILES
    q = list(sstats.norm.ppf(u)); q[10], q[11] = q[11], q[10]                  # cross q0.5 / q0.55
    df = pd.DataFrame([{f"q{x:g}": y for x, y in zip(u, q)}, {f"q{x:g}": y for x, y in zip(u, sstats.norm.ppf(u))}])
    out, n = al.rearrange_quantiles(df)
    assert n == 1 and (np.diff(out.to_numpy(), axis=1) >= 0).all()


def test_var_coverage_ignores_missing_forecasts():
    rng = np.random.default_rng(8)
    idx = pd.bdate_range("2022-01-03", periods=400); cols = [f"T{i}" for i in range(5)]
    ret = pd.DataFrame(rng.standard_normal((400, 5)), idx, cols)
    q = pd.DataFrame(sstats.norm.ppf(0.05), idx, cols); q.iloc[200:] = np.nan    # half the forecasts missing
    r = al.var_coverage(ret, q, 0.05, pd.DataFrame(True, idx, cols))
    assert r["n"] == 199 * 5 + 5 and r["hit_rate"] == pytest.approx(0.05, abs=0.02)


def test_covariates_aligned_to_target_dates_with_gaps():
    ret, elig = _toy_panel(n=300, k=3)
    ret.iloc[100:103, 1] = np.nan                                    # gap inside T1's context
    cov = pd.DataFrame(np.arange(300.0)[:, None].repeat(3, axis=1), ret.index, ret.columns)   # value = row number
    a = ret.index[280]
    tick, inp = al.forecast_contexts(ret, elig, a, ctx=250, covariates={"c": cov})
    d = inp[tick.index("T1")]
    s = ret["T1"].loc[:a].dropna().iloc[-250:]
    assert len(d["target"]) == len(d["past_covariates"]["c"]) == 250
    assert np.allclose(d["past_covariates"]["c"], [ret.index.get_loc(x) for x in s.index])   # same dates, gap skipped
    assert d["past_covariates"]["c"][-1] == 280                                            # nothing after the anchor


def test_cross_learning_one_anchor_per_call_and_kwargs():
    ret, elig = _toy_panel()
    with pytest.raises(ValueError, match="anchors_per_call=1"):
        al.generate_forecasts(FakePipe(), ret, elig, ret.index[260:262], cross_learning=True, progress=False)
    pipe = FakePipe()
    out = al.generate_forecasts(pipe, ret, elig, ret.index[260:263], anchors_per_call=1, cross_learning=True,
                                progress=False)
    assert pipe.calls == 3 and pipe.kw["cross_learning"] is True and out["anchor"].nunique() == 3
    with pytest.raises(ValueError, match="exceeds batch_size"):
        al.generate_forecasts(FakePipe(), ret, elig, ret.index[260:261], anchors_per_call=1, cross_learning=True,
                              batch_size=3, progress=False)


def test_groups_and_extra_series_are_dropped():
    ret, elig = _toy_panel(k=6)
    extras = pd.DataFrame({"IMOEX": 0.001, "BR": -0.002}, index=ret.index)
    pipe = FakePipe()
    gf = lambda a, tick: [tick[:3], tick[3:]]
    out = al.generate_forecasts(pipe, ret, elig, ret.index[260:262], anchors_per_call=1, cross_learning=True,
                                group_fn=gf, extra_series=extras, progress=False)
    assert pipe.calls == 4                                              # 2 anchors x 2 groups
    assert len(pipe.last_inputs) == 3 + 2                                # group members + 2 extras
    assert set(out["ticker"]) == set(ret.columns) and len(out) == 2 * 6 * 6   # extras never in output
    row = out[(out.anchor == ret.index[261]) & (out.ticker == "T4") & (out.h == 1)].iloc[0]
    assert row["q0.5"] == pytest.approx(ret.loc[ret.index[261], "T4"], abs=1e-6)   # ticker/output alignment kept


def test_stride_contexts_are_blocks_ending_at_anchor():
    ret, elig = _toy_panel(n=300, k=2)
    r5 = ret.rolling(5).sum()
    a = ret.index[299]
    _, inp = al.forecast_contexts(r5, elig, a, ctx=40, stride=5)
    assert len(inp[0]) == 40 and inp[0][-1] == pytest.approx(r5.loc[a, "T0"])
    assert inp[0][-2] == pytest.approx(r5["T0"].iloc[294])


def test_loo_residual_nan_aware():
    ret = pd.DataFrame({"A": [0.03, 0.01], "B": [0.00, np.nan], "C": [0.00, 0.01], "D": [0.01, 0.04]})
    r = al.loo_residual(ret)
    assert r.loc[0, "A"] == pytest.approx(0.03 - (0.00 + 0.00 + 0.01) / 3)
    assert r.loc[1, "A"] == pytest.approx(0.01 - (0.01 + 0.04) / 2) and np.isnan(r.loc[1, "B"])


def test_futures_returns_masked_on_roll():
    days = pd.bdate_range("2024-03-11", periods=3)
    bars = pd.DataFrame({"ticker": "BR", "timestamp": [pd.Timestamp(f"{d.date()} 18:40") for d in days],
                         "contract": ["BRJ4", "BRK4", "BRK4"], "close": [80.0, 85.0, 86.0]})
    r = al.futures_main_returns(bars, days)["BR"]
    assert np.isnan(r.iloc[1]) and r.iloc[2] == pytest.approx(math.log(86 / 85))


def test_block_and_cumulative_features():
    u = al.NATIVE_QUANTILES; z = sstats.norm.ppf(u); a = pd.Timestamp("2022-01-10")
    blk = pd.DataFrame([{"anchor": a, "ticker": "A", "h": 1, **{f"q{x:g}": 0.01 + 0.05 * y for x, y in zip(u, z)}}])
    fb = al.chronos_features_block(blk).loc[(a, "A")]
    _, v = al.quantile_moments(0.05 * z, u)
    assert fb["MED"] == pytest.approx(0.01) and fb["SIG"] == pytest.approx(math.sqrt(v))
    # cumulative: C_h ~ N(0.001 h, 0.01^2 h)
    rows = [{"anchor": a, "ticker": "A", "h": h, **{f"q{x:g}": 0.001 * h + 0.01 * math.sqrt(h) * y for x, y in zip(u, z)}}
            for h in range(1, 7)]
    fc = al.chronos_features_cumulative(pd.DataFrame(rows), steps=(2, 3, 4, 5, 6)).loc[(a, "A")]
    _, v1 = al.quantile_moments(0.01 * z, u)
    assert fc["MED"] == pytest.approx(0.005) and fc["SIG"] == pytest.approx(math.sqrt(5 * v1), rel=1e-6)


# ─── step-3 improvement helpers (causality is the point) ─────────────────────

def test_rolling_xs_fit_recovers_mimic_and_is_causal():
    rng = np.random.default_rng(21)
    idx = pd.bdate_range("2021-01-04", periods=320); cols = [f"T{i}" for i in range(40)]
    ret = pd.DataFrame(rng.standard_normal((320, 40)) * 0.02, idx, cols)
    feats = al.context_features(ret)
    mask = pd.DataFrame(True, idx, cols)
    target = 2 * feats["m20"] - feats["s60"]                               # a signal that IS a mimic
    fit, oos = al.rolling_xs_fit(target, feats, mask, window=60, refit_every=10, min_rows=500)
    assert oos.iloc[-50:].mean() > 0.95
    t2 = target.copy(); t2.iloc[250:] = rng.standard_normal((70, 40))        # change the future only
    fit2, _ = al.rolling_xs_fit(t2, feats, mask, window=60, refit_every=10, min_rows=500)
    assert np.allclose(fit.iloc[:251].fillna(0).to_numpy(), fit2.iloc[:251].fillna(0).to_numpy())


def test_rolling_composite_uses_only_realized_slopes():
    rng = np.random.default_rng(22)
    idx = pd.bdate_range("2021-01-04", periods=300); cols = [f"T{i}" for i in range(30)]
    mask = pd.DataFrame(True, idx, cols)
    a = pd.DataFrame(rng.standard_normal((300, 30)), idx, cols); b = pd.DataFrame(rng.standard_normal((300, 30)), idx, cols)
    fwd = 0.01 * al.xs_standardize(a, mask) + 0.01 * pd.DataFrame(rng.standard_normal((300, 30)), idx, cols)
    comp, W = al.rolling_composite(fwd, {"a": a, "b": b}, mask, horizon=6, window=100, min_obs=50)
    assert W["a"].iloc[-1] > 5 * abs(W["b"].iloc[-1])                        # learns that only `a` predicts
    fwd2 = fwd.copy(); fwd2.iloc[200:] = 0.0                                 # future returns changed
    _, W2 = al.rolling_composite(fwd2, {"a": a, "b": b}, mask, horizon=6, window=100, min_obs=50)
    assert np.allclose(W.iloc[:206].fillna(0), W2.iloc[:206].fillna(0))      # weights at d<=205 use slopes <=199


def test_smooth_signal_is_causal_and_identity_at_zero():
    rng = np.random.default_rng(23)
    idx = pd.bdate_range("2021-01-04", periods=50); cols = [f"T{i}" for i in range(12)]
    sig = pd.DataFrame(rng.standard_normal((50, 12)), idx, cols); mask = pd.DataFrame(True, idx, cols)
    assert np.allclose(al.smooth_signal(sig, mask, 0), al.xs_standardize(sig, mask))
    s1 = al.smooth_signal(sig, mask, 5); sig2 = sig.copy(); sig2.iloc[30:] = 0
    assert np.allclose(s1.iloc[:30], al.smooth_signal(sig2, mask, 5).iloc[:30])


def test_rolling_vol_scale_lagged():
    idx = pd.bdate_range("2021-01-04", periods=200); cols = ["A", "B"]
    fc = pd.DataFrame(1.0, idx, cols); rv = pd.DataFrame(2.0, idx, cols); rv.iloc[150:] = 50.0
    sc = al.rolling_vol_scale(fc, rv, pd.DataFrame(True, idx, cols), horizon=5, window=60, min_obs=20)
    assert sc.iloc[154] == pytest.approx(2.0)                                # future spike not yet visible


def test_mean_exp_quantiles_lognormal():
    u = np.array(al.NATIVE_QUANTILES); mu, sd = -9.0, 0.5
    Q = mu + sd * sstats.norm.ppf(u)
    got = al.mean_exp_quantiles(Q, u)
    assert got == pytest.approx(math.exp(mu + sd ** 2 / 2), rel=0.03)      # grid-truncated tails -> small bias


def test_quantile_shape_features_normal_and_skewed():
    u = al.NATIVE_QUANTILES; z = sstats.norm.ppf(u); a = pd.Timestamp("2022-01-10")
    rows = [{"anchor": a, "ticker": "N", "h": h, **{f"q{x:g}": 0.0 + 0.01 * y for x, y in zip(u, z)}} for h in (1, 2)]
    lz = sstats.lognorm.ppf(u, 0.8); lz = (lz - np.median(lz)) * 0.01            # right-skewed, median 0
    rows += [{"anchor": a, "ticker": "S", "h": h, **{f"q{x:g}": y for x, y in zip(u, lz)}} for h in (1, 2)]
    f = al.quantile_shape_features(pd.DataFrame(rows), steps=(1, 2))
    n, sk = f.loc[(a, "N")], f.loc[(a, "S")]
    assert n["SKEW"] == pytest.approx(0, abs=1e-9) and n["UPDOWN"] == pytest.approx(0, abs=1e-9)
    assert n["PUP"] == pytest.approx(0.5, abs=1e-6)
    assert n["VAR_IQR80"] == pytest.approx(2 * 0.01 ** 2, rel=1e-3) and n["VAR_IQR50"] == pytest.approx(2 * 0.01 ** 2, rel=1e-3)
    assert sk["SKEW"] > 0.2 and sk["UPDOWN"] > 0 and sk["TAIL"] > n["TAIL"]


def test_vol_har_log_fits_logar_and_is_causal():
    rng = np.random.default_rng(31)
    idx = pd.bdate_range("2021-01-04", periods=500); cols = [f"T{i}" for i in range(6)]
    lv = np.zeros((500, 6)); lv[0] = -8
    for i in range(1, 500):                                                  # persistent log-variance process
        lv[i] = -8 + 0.9 * (lv[i - 1] + 8) + 0.3 * rng.standard_normal(6)
    rv = pd.DataFrame(np.exp(lv), idx, cols)
    mask = pd.DataFrame(True, idx, cols)
    for pooled, market in [(False, False), (True, False), (True, True)]:
        f = al.vol_har_log(rv, range(1, 6), mask, pooled=pooled, market=market, min_train=150)
        rv5 = sum(rv.shift(-h) for h in range(1, 6))
        ok = f.notna() & rv5.notna()
        pair = pd.concat([np.log(f.where(ok)).stack(), np.log(rv5.where(ok)).stack()], axis=1).dropna()
        c = np.corrcoef(pair.iloc[:, 0], pair.iloc[:, 1])[0, 1]
        assert c > 0.6, (pooled, market, c)
    rv2 = rv.copy(); rv2.iloc[400:] *= 100                                   # future only
    a = al.vol_har_log(rv, range(1, 6), mask, pooled=True, market=True, min_train=150)
    b = al.vol_har_log(rv2, range(1, 6), mask, pooled=True, market=True, min_train=150)
    assert np.allclose(a.iloc[:400].fillna(0), b.iloc[:400].fillna(0))


def test_xs_standardize_constant_row_is_zero_not_nan():
    idx = pd.bdate_range("2022-01-03", periods=2); cols = list("ABCD")
    sig = pd.DataFrame([[1.0, 1.0, 1.0, 1.0], [1.0, 2.0, 3.0, np.nan]], idx, cols)
    z = al.xs_standardize(sig, pd.DataFrame(True, idx, cols))
    assert (z.iloc[0] == 0).all() and np.isnan(z.iloc[1, 3]) and z.iloc[1, :3].std() == pytest.approx(1.0)
