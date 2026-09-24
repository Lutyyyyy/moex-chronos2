# %% [markdown]
# # Chronos-2 as an alpha generator — driver
# Stages (run in order; each caches its output under `forecasting/runs/`):
#   `data` → `forecast` → `dev` → (README pre-registration commit) → `test` → `holdout` (once).
# From the repo root: `.venv/bin/python forecasting/alpha_experiment/alpha_run.py <stage>`.
# All logic lives in `alpha_lib.py`; this file only wires stages together.

# %%
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

HERE = Path(__file__).resolve().parent if "__file__" in globals() else Path.cwd()
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import alpha_lib as al  # noqa: E402

FC_CFG = yaml.safe_load(open(HERE / "configs/alpha_forecast_dev_test.yaml"))
BT_CFG = yaml.safe_load(open(HERE / "configs/alpha_backtest.yaml"))
DATA_DIR = ROOT / "forecasting/runs/alpha_data"
FC_DIR = ROOT / FC_CFG["output_dir"]
CACHE = ROOT / "forecasting/moex_cache"
LEDGER = HERE / "trial_ledger.csv"


# %% [markdown]
# ## Stage `data`: main-session panel, universe, realized variance, benchmarks

# %%
def stage_data(cfg=FC_CFG, out_dir=DATA_DIR, allow_download=True):
    out_dir.mkdir(parents=True, exist_ok=True)
    end = cfg["date_till"]
    shares = al.load_long(ROOT / cfg["shares_10m"], columns=["ticker", "timestamp", "close", "close_adj", "value"], end=end)
    index = al.load_long(ROOT / cfg["index_10m"], tickers=["IMOEX"], columns=["ticker", "timestamp", "close"], end=end)
    print(f"10m bars: shares={len(shares):,} ({shares.ticker.nunique()} tickers), IMOEX={len(index):,}")
    P = al.build_daily_panel(shares, index, ffill_limit=cfg["universe"]["ffill_limit"])
    rv = al.realized_variance(shares, P["calendar"])
    u = cfg["universe"]
    elig = al.pit_universe(P["ret"], P["value"], P["stale"], min_history=u["min_history"],
                           min_median_value=u["min_median_value_rub"], value_window=u["value_window"])
    mcftr_cache = CACHE / f"alpha_MCFTR_1d_2020-01-01_{end}.csv"
    if mcftr_cache.exists() or allow_download:
        mcftr = al.fetch_iss_index_daily("MCFTR", "2020-01-01", end, mcftr_cache)
    else:   # no network pull requested: MCFTR left missing (reported in data_checks)
        mcftr = pd.Series(np.nan, index=P["calendar"], name="MCFTR")
    kr = al.fetch_key_rate(CACHE / "key_rate.csv")
    for name, df in dict(close=P["close"], ret=P["ret"], stale=P["stale"], value=P["value"], rv=rv, eligible=elig).items():
        df.to_parquet(out_dir / f"{name}.parquet")
    bench = pd.DataFrame({"imoex_close": P["mkt_close"], "imoex_ret": P["mkt_ret"],
                          "mcftr_close": mcftr.reindex(P["calendar"]),
                          "rf": al.rf_daily(kr[kr.index <= pd.Timestamp(end)], P["calendar"])})
    bench["mcftr_ret"] = np.log(bench["mcftr_close"]).diff()
    bench.to_parquet(out_dir / "bench.parquet")
    return data_checks(shares, P, rv, elig, bench, cfg, out_dir)


def data_checks(shares, P, rv, elig, bench, cfg=FC_CFG, out_dir=DATA_DIR) -> dict:
    """Sanity checks listed in the plan's Verification section."""
    cal = P["calendar"]
    # (1) main close differs from the evening 1d close on most post-2021 days
    d1 = al.load_long(ROOT / "data_pipeline/data/processed/candles_1d/shares.parquet",
                      tickers=["SBER", "GAZP", "LKOH"], columns=["ticker", "timestamp", "close"], end=cfg["date_till"])
    d1["date"] = d1["timestamp"].dt.normalize()
    raw_main = al.main_session_close(shares[shares.ticker.isin(["SBER", "GAZP", "LKOH"])], col="close")
    j = d1.set_index(["date", "ticker"])["close"].rename("c1d").to_frame().join(raw_main.stack().rename("cmain"))
    j = j.dropna(); j = j[j.index.get_level_values(0) >= "2021-01-01"]
    frac_equal = float(((j.c1d - j.cmain).abs() < 1e-9).mean())
    # (2) no holiday zero-return rows: share of calendar days where >=80% of names have exactly 0 return
    zero_days = int(((P["ret"] == 0).sum(axis=1) >= 0.8 * P["ret"].notna().sum(axis=1).clip(lower=1)).sum())
    # (3) adjustment: largest |ret| should not be dividend gaps -> report top absolute daily returns
    top = P["ret"].stack().abs().sort_values(ascending=False).head(8)
    # (4) intraday vs daily: RV should be ~ r^2 on average (ratio ~ 1 means consistent scale)
    ratio = float((rv.where(elig).stack().mean()) / ((P["ret"] ** 2).where(elig).stack().mean()))
    n_elig = elig.sum(axis=1)
    checks = dict(
        calendar=[str(cal[0].date()), str(cal[-1].date()), len(cal)],
        days_2022_closure_gap=str(cal[(cal > "2022-02-20") & (cal < "2022-04-01")][:3].date.tolist()),
        frac_1d_close_equals_main_close_post2021=round(frac_equal, 4),
        holiday_like_zero_return_days=zero_days,
        top_abs_daily_returns=[(str(i[0].date()), i[1], round(float(v), 3)) for i, v in top.items()],
        rv_to_sq_ret_ratio=round(ratio, 3),
        eligible_names=dict(first_date=str(n_elig[n_elig > 0].index[0].date()),
                            min_after_2021=int(n_elig["2021":].min()), median_2021=int(n_elig["2021"].median()),
                            median_2023=int(n_elig["2023"].median()), median_2024=int(n_elig["2024"].median()),
                            median_last_year=int(n_elig.iloc[-250:].median()),
                            ever=int(elig.any().sum())),
        mcftr_missing_on_calendar=int(bench["mcftr_close"]["2021":].isna().sum()),
        rf_last=float(bench["rf"].iloc[-1]),
    )
    print(json.dumps(checks, indent=2, default=str))
    (out_dir / "data_checks.json").write_text(json.dumps(checks, indent=2, default=str))
    return checks


def load_data(data_dir=DATA_DIR) -> dict:
    D = {n: pd.read_parquet(data_dir / f"{n}.parquet") for n in ["close", "ret", "stale", "value", "rv", "eligible", "bench"]}
    D["eligible"] = D["eligible"].astype(bool)
    D["R"] = np.expm1(D["ret"])
    return D


# %% [markdown]
# ## Stage `forecast`: Chronos-2 quantile forecasts at every trading day (holdout locked)

# %%
def load_pipeline(model=FC_CFG["model"]):
    import torch
    from chronos import Chronos2Pipeline
    return Chronos2Pipeline.from_pretrained(model, device_map="cpu", torch_dtype=torch.float32)


def stage_forecast(smoke: bool = False, cfg=FC_CFG):
    D = load_data()
    cal = D["ret"].index
    anchors = cal[cal >= pd.Timestamp(cfg["first_anchor"])]
    elig = D["eligible"]
    out = FC_DIR / "preds.parquet"
    if smoke:   # 3-month slice, separate output
        anchors = anchors[:63]   # all eligible names, so every downstream step has a real cross-section
        out = FC_DIR / "preds_smoke.parquet"
    FC_DIR.mkdir(parents=True, exist_ok=True)
    pipe = load_pipeline()
    import time
    t0 = time.time()
    preds = al.generate_forecasts(pipe, D["ret"][elig.columns], elig, anchors, ctx=cfg["context_len"],
                                  H=cfg["horizon"], quantiles=al.NATIVE_QUANTILES,
                                  anchors_per_call=cfg["anchors_per_call"], out_path=out)
    secs = time.time() - t0
    qcols = [f"q{q:g}" for q in al.NATIVE_QUANTILES]
    exp_rows = int(elig.loc[anchors].sum().sum()) * cfg["horizon"]
    checks = dict(rows=len(preds), expected_rows=exp_rows, anchors=int(preds["anchor"].nunique()),
                  max_anchor=str(preds["anchor"].max().date()), seconds=round(secs, 1),
                  rows_with_quantile_crossing=int((np.diff(preds[qcols].to_numpy(), axis=1) < -1e-7).any(axis=1).sum()),
                  any_nan=bool(preds[qcols].isna().any().any()))
    print(json.dumps(checks, indent=2))
    assert checks["rows"] == checks["expected_rows"], "missing (anchor, eligible ticker) forecasts"
    assert pd.Timestamp(checks["max_anchor"]) < al.HOLDOUT_START
    (FC_DIR / ("forecast_checks_smoke.json" if smoke else "forecast_checks.json")).write_text(json.dumps(checks, indent=2))
    return preds


# %% [markdown]
# ## Shared evaluation (identical code for dev, test, holdout)
# Selection rules (fixed in code BEFORE any dev result was computed):
# * Track A v1 primary = the Chronos candidate with the highest dev IC Newey-West t (A1 statistic),
#   evaluated with the gated construction (beta-neutral long-short rank book, exec_lag=1).
# * Track B v1 primary = the SIG use with the largest dev net-Sharpe gain of the Chronos-vol version
#   over the identical EWMA-vol version.

# %%
LAG = BT_CFG["rebalance"]["exec_lag_primary"]
STEPS = {0: tuple(range(1, 6)), 1: tuple(range(2, 7))}
NW = BT_CFG["nw_lags_daily_overlapping"]
COST, BORROW = BT_CFG["cost_bps_gate"], BT_CFG["borrow_annual_gate"]


def period_bounds(name):
    lo, hi = BT_CFG["periods"][name]
    return pd.Timestamp(lo), pd.Timestamp(hi)


def build_inputs(preds: pd.DataFrame, D: dict, feat_fn=None) -> dict:
    """Everything derived from data + forecasts (signals, vol forecasts, masks). Causal by construction."""
    cal = D["ret"].index
    ret, value = D["ret"], D["value"]
    X = {"D": D, "cal": cal}
    feat_fn = feat_fn or al.chronos_features
    for lag, steps in STEPS.items():
        F = feat_fn(preds, steps)
        X[f"F{lag}"] = {c: al.to_wide(F, c, cal).reindex(columns=ret.columns) for c in F.columns}
        X[f"classic{lag}"] = al.classic_signals(ret, value, steps)
        X[f"fwd{lag}"] = al.forward_returns(ret, steps)
    bc = BT_CFG["constructions"]["ls_rank_beta_neutral"]
    X["betas"] = al.trailing_betas(ret, D["bench"]["imoex_ret"], window=bc["beta_window"], min_periods=bc["beta_min_periods"])
    c1 = X[f"classic{LAG}"]
    X["mask"] = (D["eligible"] & X[f"F{LAG}"]["MED"].notna() & X["betas"].notna()
                 & c1["mom_12_1"].notna() & c1["lowvol_60d"].notna() & c1["ar1"].notna() & c1["size"].notna())
    return X


def ic_dates(X, period, steps):
    """Signal dates whose whole forward window lies inside the period (no bleed across split)."""
    lo, hi = period_bounds(period)
    cal = X["cal"]
    last_ok = cal[cal <= hi][-1 - max(steps)] if (cal <= hi).sum() > max(steps) else lo
    return cal[(cal >= lo) & (cal <= last_ok)]


def excl(idx, period):
    if period != "dev":
        return idx
    for lo, hi in BT_CFG["periods"]["dev_ex_2022_shock"]:
        idx = idx[(idx < lo) | (idx > hi)]
    return idx


def ic_stats(sig, X, period, lag=LAG, mask=None):
    mask = X["mask"] if mask is None else mask
    d = ic_dates(X, period, STEPS[lag])
    ic = al.ic_series(sig, X[f"fwd{lag}"], mask).reindex(d).dropna()
    r = al.nw_tstat(ic, NW)
    weekly_t = np.mean([al.nw_tstat(ic.iloc[k::5], 0)["t"] for k in range(5)])
    ex = al.nw_tstat(ic.reindex(excl(ic.index, period)).dropna(), NW)
    return dict(ic_mean=r["mean"], ic_se=r["se"], ic_t=r["t"], ic_n=r["n"], ic_std=float(ic.std()),
                ic_hit=float((ic > 0).mean()), ic_t_weekly_nonoverlap=float(weekly_t),
                ic_t_ex2022shock=ex["t"]), ic


def bt_stats(W, X, period, lag=LAG, cost=COST, borrow=BORROW, excess=False, n_tranches=None):
    lo, hi = period_bounds(period)
    bt = al.run_backtest(W, X["D"]["R"], exec_lag=lag, n_tranches=n_tranches or BT_CFG["rebalance"]["n_tranches"],
                         cost_bps=cost, borrow_annual=borrow, start=lo, end=hi)
    rf = X["D"]["bench"]["rf"] if excess else None
    s = al.perf_stats(bt["net"], rf)
    s.update(gross_sharpe=al.perf_stats(bt["gross"], rf).get("sharpe"), turnover_ann=float(bt["turnover"].mean() * 252),
             breakeven_bps=al.cost_breakeven_bps(bt))
    return s, bt


def books(sig, X, kind):
    m = X["mask"]
    if kind == "LS":
        return al.w_ls_rank(sig, m, betas=X["betas"])
    if kind == "LO":
        return al.w_lo_topq(sig, m, q=BT_CFG["constructions"]["lo_top_quintile"]["q"])
    raise ValueError(kind)


def evaluate_track_a(X, period, candidates, ledger_tag):
    """IC + LS/LO books for Chronos candidates and classic baselines; cost/borrow/lag sweeps for LS."""
    F, C = X[f"F{LAG}"], X[f"classic{LAG}"]
    sigs = {**{f"chronos_{c}": F[c] for c in candidates},
            **{k: C[k] for k in BT_CFG["classic"]}}
    rows, pnl, ics = [], {}, {}
    bench = X["D"]["bench"]
    ew_s, ew_bt = bt_stats(al.w_equal(X["mask"]), X, period, excess=True)
    pnl["EW_universe"] = ew_bt["net"]
    lo, hi = period_bounds(period)
    for name, s in sigs.items():
        st, ic = ic_stats(s, X, period); ics[name] = ic
        for kind in ["LS", "LO"]:
            W = books(s, X, kind)
            p, bt = bt_stats(W, X, period, excess=(kind == "LO"))
            pnl[f"{name}|{kind}"] = bt["net"]
            row = dict(signal=name, book=kind, period=period, **st, **{f"net_{k}": v for k, v in p.items()})
            if kind == "LS":
                for c in BT_CFG["costs_bps_one_way"]:
                    row[f"sharpe_cost{c}"] = bt_stats(W, X, period, cost=c)[0].get("sharpe")
                for b in BT_CFG["borrow_annual"]:
                    row[f"sharpe_borrow{b}"] = bt_stats(W, X, period, borrow=b)[0].get("sharpe")
                row["sharpe_lag0"] = bt_stats(W, X, period, lag=0)[0].get("sharpe")
            else:
                act = (bt["net"] - ew_bt["net"]).dropna()
                row["active_ann"] = float(act.mean() * 252)
                row["info_ratio_vs_EW"] = float(act.mean() / act.std() * np.sqrt(252))
                y = bt["net"] - bench["rf"].reindex(bt.index)
                xm = np.expm1(bench["imoex_ret"]).reindex(bt.index) - bench["rf"].reindex(bt.index)
                capm = al.ols_nw(y, xm.rename("mkt").to_frame(), lags=10)
                row["capm_alpha_ann"] = float(capm.loc["const", "coef"] * 252)
                row["capm_alpha_t"] = float(capm.loc["const", "t"])
                row["capm_beta"] = float(capm.loc["mkt", "coef"])
            rows.append(row)
            if name.startswith("chronos_"):
                al.append_trial(LEDGER, track="A", tag=ledger_tag, period=period, signal=name, book=kind,
                                exec_lag=LAG, cost_bps=COST, borrow=BORROW, ic_t=st["ic_t"],
                                net_sharpe=p.get("sharpe"), daily_sr=p.get("sharpe", np.nan) / np.sqrt(252))
    table = pd.DataFrame(rows)
    # buy-and-hold benchmarks (excess of rf)
    bh = []
    for nm, r in [("IMOEX", np.expm1(bench["imoex_ret"])), ("MCFTR", np.expm1(bench["mcftr_ret"]))]:
        r = r[(r.index >= lo) & (r.index <= hi)]
        bh.append(dict(signal=nm, book="buy_hold", period=period,
                       **{f"net_{k}": v for k, v in al.perf_stats(r, bench["rf"]).items()}))
    bh.append(dict(signal="EW_universe", book="weekly_EW", period=period, **{f"net_{k}": v for k, v in ew_s.items()}))
    table = pd.concat([table, pd.DataFrame(bh)], ignore_index=True)
    return table, pnl, ics


def spanning_and_fm(X, period, cand, pnl):
    """A2: Chronos LS net returns on classic LS net returns + IMOEX. A3: Fama-MacBeth incremental."""
    lo, hi = period_bounds(period)
    y = pnl[f"chronos_{cand}|LS"]
    Xs = pd.DataFrame({k: pnl[f"{k}|LS"] for k in BT_CFG["classic"]})
    Xs["IMOEX"] = np.expm1(X["D"]["bench"]["imoex_ret"]).reindex(y.index)
    span = al.ols_nw(y, Xs, lags=10)
    C = X[f"classic{LAG}"]
    d = ic_dates(X, period, STEPS[LAG])
    fm = al.fama_macbeth(X[f"fwd{LAG}"], {"chronos": X[f"F{LAG}"][cand], "mom_12_1": C["mom_12_1"],
                                           "rev_5d": C["rev_5d"], "rev_1d": C["rev_1d"],
                                           "lowvol_60d": C["lowvol_60d"], "size": C["size"]},
                         X["mask"], lags=NW, dates=d)
    return span, fm


def vol_inputs(X, cache_dir):
    """Variance forecasts over steps 1..5 (statistical track) and 2..6 (sizing at lag 1). Cached."""
    D = X["D"]; ret = D["ret"]
    out = {}
    for lag, steps in STEPS.items():
        f = cache_dir / f"vol_fc_lag{lag}.parquet"
        if f.exists():
            V = pd.read_parquet(f)
            out[lag] = {k: V.xs(k, axis=1, level=0) for k in V.columns.levels[0]}
            continue
        n = len(steps)
        V = {"chronos": al.vol_chronos(X[f"F{lag}"]["SIG"]),
             "trailing20": al.vol_trailing(ret, n),
             "ewma": al.vol_ewma(ret, n),
             "garch": al.vol_garch(ret, steps),
             "har_daily": al.vol_har(ret ** 2, ret ** 2, steps),
             "har_rv_ceiling": al.vol_har(D["rv"], D["rv"], steps)}
        pd.concat(V, axis=1).to_parquet(f)
        out[lag] = V
    return out


def evaluate_track_b(X, V, period, ledger_tag, scales=None):
    """B1 statistical (steps 1..5 vs RV) + B2 economic uses (steps 2..6, exec_lag=1)."""
    D = X["D"]
    steps = STEPS[0]
    rv_fwd = sum(D["rv"].shift(-h) for h in steps)
    models = list(V[0])
    mask = X["mask"].copy()
    for k in models:
        mask &= V[0][k].notna()
    d = ic_dates(X, period, steps)
    m = mask.loc[d]
    if scales is None:
        scales = {k: al.qlike_scale(rv_fwd.loc[d], V[0][k].loc[d], m) for k in models}
    loss = {k: al.vol_loss_panel(rv_fwd.loc[d], V[0][k].loc[d], m) for k in models}
    loss_sc = {k: al.vol_loss_panel(rv_fwd.loc[d], V[0][k].loc[d], m, scale=scales[k]) for k in models}
    stat = []
    for k in models:
        row = dict(model=k, period=period, qlike=float(loss[k].mean()), qlike_scaled=float(loss_sc[k].mean()),
                   scale=scales[k], **{f"mz_{a}": b for a, b in al.mincer_zarnowitz(rv_fwd.loc[d], V[0][k].loc[d], m).items()})
        if k != "chronos":
            dm = al.dm_test(loss["chronos"], loss[k], NW); dms = al.dm_test(loss_sc["chronos"], loss_sc[k], NW)
            row.update(dm_t_chronos_vs=dm["t"], dm_p_chronos_better=dm["p_a_better"],
                       dm_scaled_t=dms["t"], dm_scaled_p_chronos_better=dms["p_a_better"])
        stat.append(row)
    stat = pd.DataFrame(stat)
    # VaR coverage of 1-step quantiles
    P = X["preds"]; p1 = P[P["h"] == 1]
    cov = []
    for lvl in (0.05, 0.1):
        q = p1.pivot(index="anchor", columns="ticker", values=f"q{lvl:g}").reindex(index=X["cal"], columns=D["ret"].columns)
        dd = d[d <= d[-1]]
        cov.append(al.var_coverage(D["ret"], q.loc[dd], lvl, mask.loc[dd]))
    # B2 economic uses (steps 2..6 vol forecasts, exec_lag = LAG)
    V1 = V[LAG]; nst = len(STEPS[LAG])
    corr = X.get("corr") or al.ewma_corr(D["ret"], lam=BT_CFG["vol_target"]["corr_lambda"])
    X["corr"] = corr
    vt = BT_CFG["vol_target"]
    mom_ls = books(X[f"classic{LAG}"]["mom_12_1"], X, "LS")
    ew = al.w_equal(X["mask"])
    uses = {
        "lowvol_factor": lambda v: books(-np.sqrt(v), X, "LS"),
        "inverse_vol_ew": lambda v: al.w_inverse_vol(v, X["mask"]),
        "voltarget_ew": lambda v: al.vol_target_overlay(ew, v, corr, nst, vt["target_ann"], vt["lev_cap_lo"]),
        "voltarget_mom": lambda v: al.vol_target_overlay(mom_ls, v, corr, nst, vt["target_ann"], vt["lev_cap_ls"]),
    }
    econ, pnl = [], {}
    for use, fn in uses.items():
        res = {}
        for model in ["chronos", "ewma", "garch"]:
            W = fn(V1[model])
            s, bt = bt_stats(W, X, period, excess=(use in ("inverse_vol_ew", "voltarget_ew")))
            pnl[f"{use}|{model}"] = bt["net"]
            rv63 = bt["net"].rolling(63).std() * np.sqrt(252)
            res[model] = s
            econ.append(dict(use=use, vol_model=model, period=period, **{f"net_{k}": v for k, v in s.items()},
                             vol_tracking_err=float((rv63 - vt["target_ann"]).abs().mean()) if use.startswith("voltarget") else np.nan))
        boot = al.sharpe_diff_bootstrap(pnl[f"{use}|chronos"], pnl[f"{use}|ewma"])
        econ[-3].update(boot_diff_vs_ewma=boot["diff"], boot_p_vs_ewma=boot["p_one_sided"],
                        boot_ci_lo=boot["ci_lo"], boot_ci_hi=boot["ci_hi"])
        al.append_trial(LEDGER, track="B", tag=ledger_tag, period=period, signal=f"{use}|chronos", book=use,
                        exec_lag=LAG, cost_bps=COST, borrow=BORROW, net_sharpe=res["chronos"].get("sharpe"),
                        daily_sr=res["chronos"].get("sharpe", np.nan) / np.sqrt(252),
                        sharpe_gain_vs_ewma=res["chronos"].get("sharpe", np.nan) - res["ewma"].get("sharpe", np.nan))
    return stat, pd.DataFrame(cov), pd.DataFrame(econ), pnl, scales


# %% [markdown]
# ## Stage `dev`: evaluate everything on 2021-2023, select v1 primaries, power statement

# %%
DEV_DIR = ROOT / "forecasting/runs/alpha_dev"


def load_preds(path=None):
    preds, n_bad = al.rearrange_quantiles(pd.read_parquet(path or FC_DIR / "preds.parquet"))
    print(f"load_preds: {n_bad} of {len(preds)} rows had crossing quantiles -> rearranged (sorted)")
    return preds


def unique_trials(led, track, period, tag=None):
    """Distinct variants (a re-run of the same variant is not a new trial); last row wins.
    `tag` restricts to one run (the corrected-data re-run evaluates the same 4 variants, not new ones)."""
    t = led[(led.track == track) & (led.period == period)]
    if tag is not None:
        t = t[t.tag == tag]
    return t.drop_duplicates(subset=["tag", "signal", "book", "exec_lag", "cost_bps", "borrow"], keep="last")


def stage_dev(preds_path=None, out_dir=DEV_DIR, tag="v1_dev", ledger=None):
    global LEDGER
    if ledger is not None:
        LEDGER = Path(ledger)
    out_dir.mkdir(parents=True, exist_ok=True)
    D = load_data(); preds = load_preds(preds_path)
    X = build_inputs(preds, D); X["preds"] = preds
    candA = BT_CFG["track_a_candidates"]
    A, pnlA, icsA = evaluate_track_a(X, "dev", candA, tag)
    A.to_csv(out_dir / "track_a_dev.csv", index=False)
    # selection A (rule fixed above): highest dev IC NW t among Chronos candidates, LS book
    chron = A[(A.signal.str.startswith("chronos_")) & (A.book == "LS")].set_index("signal")
    primary_a = chron["ic_t"].idxmax().replace("chronos_", "")
    span, fm = spanning_and_fm(X, "dev", primary_a, pnlA)
    span.to_csv(out_dir / "spanning_dev.csv"); fm.to_csv(out_dir / "fama_macbeth_dev.csv")
    # DSR at selection: all Track A Chronos trials evaluated on dev so far (ledger)
    led = pd.read_csv(LEDGER)
    ta = unique_trials(led, "A", "dev", tag)
    sel = pnlA[f"chronos_{primary_a}|LS"].dropna()
    ps = al.perf_stats(sel)
    dsr = al.deflated_sharpe(sel.mean() / sel.std(), len(sel), len(ta), float(ta["daily_sr"].var(ddof=1)),
                             ps["skew"], ps["kurt"])
    # power statement for the 2024 test (A1): se scales with 1/sqrt(n)
    ic_sel = icsA[f"chronos_{primary_a}"]
    r = al.nw_tstat(ic_sel.reindex(ic_dates(X, "dev", STEPS[LAG])).dropna(), NW)
    n_test = len(ic_dates(X, "test", STEPS[LAG])) if X["cal"].max() >= period_bounds("test")[0] else 245
    se_test = r["se"] * np.sqrt(r["n"] / n_test)
    mde = 2 * se_test
    from scipy import stats as sst
    power_at_dev_ic = float(1 - sst.norm.cdf(2 - r["mean"] / se_test)) if np.isfinite(r["mean"]) else np.nan
    # Track B
    V = vol_inputs(X, out_dir)
    B1, cov, B2, pnlB, scales = evaluate_track_b(X, V, "dev", tag)
    B1.to_csv(out_dir / "track_b_stat_dev.csv", index=False); cov.to_csv(out_dir / "var_coverage_dev.csv", index=False)
    B2.to_csv(out_dir / "track_b_econ_dev.csv", index=False)
    gains = B2[B2.vol_model == "chronos"].set_index("use")["net_sharpe"] - B2[B2.vol_model == "ewma"].set_index("use")["net_sharpe"]
    primary_b = gains.idxmax()
    led = pd.read_csv(LEDGER); tb = unique_trials(led, "B", "dev", tag)
    selb = pnlB[f"{primary_b}|chronos"].dropna(); psb = al.perf_stats(selb)
    dsr_b = al.deflated_sharpe(selb.mean() / selb.std(), len(selb), len(tb), float(tb["daily_sr"].var(ddof=1)),
                               psb["skew"], psb["kurt"])
    # daily-return serial correlation check (SIG5 = sqrt(sum var) assumption)
    ac = {L: float(np.nanmean([X["D"]["ret"][t].loc[:"2023"].autocorr(L) for t in X["D"]["ret"].columns])) for L in range(1, 6)}
    ew_mkt = X["D"]["ret"].where(X["mask"]).mean(axis=1).loc["2021":"2023"]
    ac_mkt = {L: float(ew_mkt.autocorr(L)) for L in range(1, 6)}
    summary = dict(primary_a=primary_a, dsr_a_dev=dsr, n_trials_a=int(len(ta)),
                   primary_b=primary_b, dsr_b_dev=dsr_b, n_trials_b=int(len(tb)),
                   b_scales_dev=scales, sharpe_gain_vs_ewma=gains.to_dict(),
                   power=dict(dev_ic_mean=r["mean"], dev_ic_se=r["se"], dev_n=r["n"], test_n=n_test,
                              test_se=se_test, mde_ic_t2=mde, power_if_true_ic_equals_dev=power_at_dev_ic),
                   mean_ticker_autocorr=ac, ew_market_autocorr=ac_mkt)
    (out_dir / "dev_summary.json").write_text(json.dumps(summary, indent=2, default=float))
    pd.concat({k: v for k, v in pnlA.items()}, axis=1).to_parquet(out_dir / "pnl_track_a_dev.parquet")
    pd.concat(pnlB, axis=1).to_parquet(out_dir / "pnl_track_b_dev.parquet")
    print(json.dumps(summary, indent=2, default=float))
    return summary


# %% [markdown]
# ## Stage `test`: the 2024 gate, run ONCE for the frozen v1 primaries (see README pre-registration)

# %%
TEST_DIR = ROOT / "forecasting/runs/alpha_test"


def gate_verdicts(primary_a, A, span, fm, B1, B2, primary_b) -> dict:
    g = BT_CFG["gate"]
    ra = A[(A.signal == f"chronos_{primary_a}") & (A.book == "LS")].iloc[0]
    a1 = float(ra["ic_t"]); a2 = float(span.loc["const", "t"]); a3 = float(fm.loc["chronos", "t"])
    b1 = B1.set_index("model")
    b1_raw = {m: float(b1.loc[m, "dm_p_chronos_better"]) for m in ["ewma", "garch"]}
    b1_sc = {m: float(b1.loc[m, "dm_scaled_p_chronos_better"]) for m in ["ewma", "garch"]}
    rb = B2[(B2.use == primary_b) & (B2.vol_model == "chronos")].iloc[0]
    out = dict(
        A1=dict(stat="IC NW t", value=a1, threshold=g["A1_ic_nw_t"], pass_=a1 > g["A1_ic_nw_t"]),
        A2=dict(stat="net spanning alpha t", value=a2, alpha_ann=float(span.loc["const", "coef"] * 252),
                threshold=g["A2_spanning_alpha_t"], pass_=a2 > g["A2_spanning_alpha_t"]),
        A3=dict(stat="Fama-MacBeth chronos t", value=a3, threshold=g["A3_fm_t"], pass_=a3 > g["A3_fm_t"]),
        B1=dict(stat="DM p (chronos better), raw & scaled QLIKE, vs EWMA and GARCH", raw=b1_raw, scaled=b1_sc,
                threshold=g["B1_dm_p"], pass_=all(v < g["B1_dm_p"] for v in [*b1_raw.values(), *b1_sc.values()])),
        B2=dict(stat=f"bootstrap p Sharpe({primary_b}|chronos) > Sharpe(|ewma)", value=float(rb["boot_p_vs_ewma"]),
                sharpe_diff=float(rb["boot_diff_vs_ewma"]), threshold=g["B2_boot_p"],
                pass_=float(rb["boot_p_vs_ewma"]) < g["B2_boot_p"]),
    )
    out["TRACK_A_PASS"] = all(out[k]["pass_"] for k in ["A1", "A2", "A3"])
    out["TRACK_B_PASS"] = all(out[k]["pass_"] for k in ["B1", "B2"])
    return out


def stage_test(out_dir=TEST_DIR, tag="v1_test"):
    dev = json.loads((DEV_DIR / "dev_summary.json").read_text())
    primary_a, primary_b = dev["primary_a"], dev["primary_b"]
    if out_dir.exists() and any(out_dir.iterdir()):
        raise SystemExit(f"{out_dir} is not empty — the 2024 gate is single-use (a crashed attempt must be "
                         "reported, not silently retried)")
    out_dir.mkdir(parents=True, exist_ok=True)
    D = load_data(); preds = load_preds()
    X = build_inputs(preds, D); X["preds"] = preds
    A, pnlA, _ = evaluate_track_a(X, "test", [primary_a], tag)
    span, fm = spanning_and_fm(X, "test", primary_a, pnlA)
    V = vol_inputs(X, DEV_DIR)                                  # same cached forecasts (computed on full panel, causal)
    lo, hi = period_bounds("test")
    for lag in V:
        for k, v in V[lag].items():
            cov_share = float(v.loc[lo:hi].notna().any(axis=1).mean())
            assert cov_share > 0.95, f"vol cache {k} lag{lag} covers only {cov_share:.0%} of test dates"
    assert set(dev["b_scales_dev"]) == set(V[0]), "dev QLIKE scales do not match the model set"
    B1, cov, B2, pnlB, _ = evaluate_track_b(X, V, "test", tag, scales=dev["b_scales_dev"])
    gate = gate_verdicts(primary_a, A, span, fm, B1, B2, primary_b)
    for name, df in dict(track_a_test=A, track_b_stat_test=B1, var_coverage_test=cov, track_b_econ_test=B2).items():
        df.to_csv(out_dir / f"{name}.csv", index=False)
    span.to_csv(out_dir / "spanning_test.csv"); fm.to_csv(out_dir / "fama_macbeth_test.csv")
    pd.concat(pnlA, axis=1).to_parquet(out_dir / "pnl_track_a_test.parquet")
    pd.concat(pnlB, axis=1).to_parquet(out_dir / "pnl_track_b_test.parquet")
    (out_dir / "gate.json").write_text(json.dumps(dict(primary_a=primary_a, primary_b=primary_b, **gate), indent=2, default=float))
    print(json.dumps(gate, indent=2, default=float))
    return gate


# %% [markdown]
# ## Stage `variants` (improvement I0): 2x2 of cross_learning x covariates, on extended dev 2021-2024
# Baseline = the corrected v1 forecasts (univariate, no covariates). Every variant, the baseline
# included, is evaluated by the same function. Holdout stays sealed.

# %%
VAR_DIR = ROOT / "forecasting/runs/alpha_variants"
VARIANTS = {
    "uni": dict(),                                                       # baseline (re-uses v1c preds)
    "xl": dict(cross_learning=True, anchors_per_call=1),
    "cov": dict(covariates=True),
    "xl_cov": dict(covariates=True, cross_learning=True, anchors_per_call=1),
}


def covariate_panels(D) -> dict:
    """Past covariates: IMOEX daily log return (same for all names) and the name's own
    log change in main-session traded value. Both known at the close of each context day."""
    ret = D["ret"]
    mkt = pd.DataFrame(np.repeat(D["bench"]["imoex_ret"].reindex(ret.index).to_numpy()[:, None], ret.shape[1], 1),
                       ret.index, ret.columns)
    dlogval = np.log(D["value"].replace(0, np.nan)).diff().reindex_like(ret)
    return {"mkt": mkt, "dlogval": dlogval}


def pinball_1step(preds, ret, mask, dates):
    """Mean pinball loss of the h=1 21-quantile forecast vs realized r_{d+1} (proper score, whole distribution)."""
    p = preds[(preds["h"] == 1) & preds["anchor"].isin(dates)]
    y = ret.shift(-1).stack().rename("y"); y.index.names = ["anchor", "ticker"]
    p = p.join(y, on=["anchor", "ticker"])
    ok = mask.stack().rename("m"); ok.index.names = ["anchor", "ticker"]
    p = p.join(ok, on=["anchor", "ticker"])
    p = p[p["m"].fillna(False).astype(bool) & p["y"].notna()]
    losses = []
    for q in al.NATIVE_QUANTILES:
        e = p["y"] - p[f"q{q:g}"]
        losses.append(np.maximum(q * e, (q - 1) * e))
    p = p.assign(loss=np.mean(np.stack(losses), axis=0))
    return p.groupby("anchor")["loss"].mean()                            # per-date series (for paired tests)


def evaluate_variant(name, preds, D, classic_pnl, V_base, period="ext_dev", tag="I0_2x2",
                     feat_fn=None, base_mask=None, base_sig=None):
    X = build_inputs(preds, D, feat_fn); X["preds"] = preds
    F = X[f"F{LAG}"]
    out = dict(variant=name)
    if base_mask is not None:            # same evaluation universe for every config (paired comparisons)
        own = X["mask"]
        X["mask"] = base_mask & F["MED"].notna()
        d0 = ic_dates(X, period, STEPS[LAG])
        out["coverage_vs_base"] = float(X["mask"].loc[d0].sum().sum() / max(base_mask.loc[d0].sum().sum(), 1))
    ics = {}
    for sig in ["MED_SIG", "MED"]:
        st, ic = ic_stats(F[sig], X, period); ics[sig] = ic
        out[f"{sig}_ic"] = st["ic_mean"]; out[f"{sig}_ic_t"] = st["ic_t"]
    W = books(F["MED_SIG"], X, "LS")
    s, bt = bt_stats(W, X, period)
    out.update(ls_net_sharpe=s.get("sharpe"), ls_gross_sharpe=s.get("gross_sharpe"), ls_turnover=s.get("turnover_ann"))
    Xs = pd.DataFrame({k: classic_pnl[k] for k in BT_CFG["classic"]})
    Xs["IMOEX"] = np.expm1(D["bench"]["imoex_ret"]).reindex(bt.index)
    span = al.ols_nw(bt["net"], Xs.reindex(bt.index), lags=10)
    out.update(span_alpha_ann=float(span.loc["const", "coef"] * 252), span_alpha_t=float(span.loc["const", "t"]))
    C = X[f"classic{LAG}"]
    fm = al.fama_macbeth(X[f"fwd{LAG}"], {"chronos": F["MED_SIG"], "mom_12_1": C["mom_12_1"], "rev_5d": C["rev_5d"],
                                          "rev_1d": C["rev_1d"], "lowvol_60d": C["lowvol_60d"], "size": C["size"]},
                         X["mask"], lags=NW, dates=ic_dates(X, period, STEPS[LAG]))
    out["fm_t"] = float(fm.loc["chronos", "t"])
    if base_sig is not None and name != "uni":   # incremental over the baseline Chronos signal + classic factors
        fm2 = al.fama_macbeth(X[f"fwd{LAG}"], {"chronos": F["MED_SIG"], "chronos_uni": base_sig, "mom_12_1": C["mom_12_1"],
                                               "rev_5d": C["rev_5d"], "rev_1d": C["rev_1d"], "lowvol_60d": C["lowvol_60d"],
                                               "size": C["size"]}, X["mask"], lags=NW, dates=ic_dates(X, period, STEPS[LAG]))
        out["fm_t_over_uni"] = float(fm2.loc["chronos", "t"])
    # Track B: variance over steps 1..5 vs realized variance
    steps = STEPS[0]
    rv_fwd = sum(D["rv"].shift(-h) for h in steps)
    d = ic_dates(X, period, steps)
    vc = al.vol_chronos(X["F0"]["SIG"])
    m = X["mask"].loc[d] & vc.loc[d].notna() & V_base["ewma"].loc[d].notna() & V_base["garch"].loc[d].notna()
    loss = al.vol_loss_panel(rv_fwd.loc[d], vc.loc[d], m)
    sc = al.qlike_scale(rv_fwd.loc[d], vc.loc[d], m)
    loss_sc = al.vol_loss_panel(rv_fwd.loc[d], vc.loc[d], m, scale=sc)
    out.update(qlike=float(loss.mean()), qlike_scaled=float(loss_sc.mean()))
    for k in ["ewma", "garch"]:
        lb = al.vol_loss_panel(rv_fwd.loc[d], V_base[k].loc[d], m)
        out[f"dm_t_vs_{k}"] = al.dm_test(loss, lb, NW)["t"]          # negative = Chronos variant better
    pb = pinball_1step(preds, D["ret"], X["mask"], d)
    out["pinball_h1"] = float(pb.mean())
    cov = al.var_coverage(D["ret"], preds[preds.h == 1].pivot(index="anchor", columns="ticker", values="q0.05")
                          .reindex(index=X["cal"], columns=D["ret"].columns).loc[d], 0.05, X["mask"].loc[d])
    out["q05_hit"] = cov["hit_rate"]
    al.append_trial(LEDGER, track="A", tag=tag, period=period, signal=f"{name}|MED_SIG", book="LS", exec_lag=LAG,
                    cost_bps=COST, borrow=BORROW, ic_t=out["MED_SIG_ic_t"], net_sharpe=out["ls_net_sharpe"],
                    daily_sr=(out["ls_net_sharpe"] or np.nan) / np.sqrt(252))
    al.append_trial(LEDGER, track="B", tag=tag, period=period, signal=f"{name}|SIG", book="vol_forecast",
                    exec_lag=0, cost_bps=np.nan, borrow=np.nan, net_sharpe=np.nan, daily_sr=np.nan)
    series = dict(ic=ics["MED_SIG"], qlike=loss, qlike_sc=loss_sc, pinball=pb, pnl=bt["net"])
    return out, series


def stage_variants(names=None):
    VAR_DIR.mkdir(parents=True, exist_ok=True)
    D = load_data()
    cov = covariate_panels(D)
    names = names or list(VARIANTS)
    base_preds = load_preds()
    preds = {"uni": base_preds}
    pipe = None
    for nm in names:
        if nm == "uni":
            continue
        f = VAR_DIR / nm / "preds.parquet"
        if not f.exists():
            (VAR_DIR / nm).mkdir(parents=True, exist_ok=True)
            pipe = pipe or load_pipeline()
            kw = dict(VARIANTS[nm]); use_cov = kw.pop("covariates", False)
            cal = D["ret"].index
            anchors = cal[cal >= pd.Timestamp(FC_CFG["first_anchor"])]
            al.generate_forecasts(pipe, D["ret"], D["eligible"], anchors, ctx=FC_CFG["context_len"], H=FC_CFG["horizon"],
                                  out_path=f, covariates=cov if use_cov else None,
                                  anchors_per_call=kw.pop("anchors_per_call", FC_CFG["anchors_per_call"]), **kw)
        preds[nm] = load_preds(f)
    # classic long-short net PnL on ext_dev (same universe mask as the baseline)
    Xb = build_inputs(base_preds, D)
    classic_pnl = {k: bt_stats(books(Xb[f"classic{LAG}"][k], Xb, "LS"), Xb, "ext_dev")[1]["net"] for k in BT_CFG["classic"]}
    V = vol_inputs(Xb, DEV_DIR)[0]
    rows, S = [], {}
    for nm in names:
        r, S[nm] = evaluate_variant(nm, preds[nm], D, classic_pnl, V)
        rows.append(r)
    T = pd.DataFrame(rows).set_index("variant")
    # paired tests vs the baseline (uni): IC difference, QLIKE / pinball Diebold-Mariano, Sharpe bootstrap
    for nm in names:
        if nm == "uni":
            continue
        T.loc[nm, "ic_diff_t_vs_uni"] = al.nw_tstat((S[nm]["ic"] - S["uni"]["ic"]).dropna(), NW)["t"]
        T.loc[nm, "qlike_dm_t_vs_uni"] = al.dm_test(S[nm]["qlike"], S["uni"]["qlike"], NW)["t"]
        T.loc[nm, "qlike_sc_dm_t_vs_uni"] = al.dm_test(S[nm]["qlike_sc"], S["uni"]["qlike_sc"], NW)["t"]
        T.loc[nm, "pinball_dm_t_vs_uni"] = al.dm_test(S[nm]["pinball"], S["uni"]["pinball"], 0)["t"]
        T.loc[nm, "sharpe_boot_p_vs_uni"] = al.sharpe_diff_bootstrap(S[nm]["pnl"], S["uni"]["pnl"])["p_one_sided"]
    T.to_csv(VAR_DIR / "variants_2x2.csv")
    pd.set_option("display.width", 250)
    print(T.round(4).T.to_string())
    return T


# %% [markdown]
# ## Stage `configs` (Phase C): configuration sweep C0-C4 on extended dev 2021-2024

# %%
# Sector map: forecasting/scratchpads/phase_sector_scratch_pad.md (research-agent classification 2026-09-17)
SECTORS = {
    "oil_gas": "GAZP ROSN LKOH NVTK TATN SNGS SNGSP TATNP SIBN RNFT BANEP TRNFP EUTR",
    "metals_mining": "PLZL GMKN MAGN ALRS NLMK CHMF RUAL MTLR MTLRP SELG UGLD ENPG RASP VSMO",
    "financials": "SBER SBERP T VTBR SVCB SPBE MOEX BSPB DOMRF CBOM RENI",
    "tech_telecom": "YDEX VKCO POSI HEAD ASTR MTSS RTKM RTKMP",
    "consumer": "OZON X5 MGNT LENT MVID BELU MDMG PRMD OZPH RAGR",
    "transport_industrial": "AFLT FLOT FESH NMTP WUSH DELI IRKT UNAC SGZH UWGN PHOR AFKS SFIN SMLT PIKK CNRU",
    "utilities": "IRAO FEES UPRO HYDR MSNG MRKC MSRS TORS",
}
SECTOR_OF = {t: sec for sec, ts in SECTORS.items() for t in ts.split()}
SECTOR_INDEX = {"oil_gas": "MOEXOG", "metals_mining": "MOEXMM", "financials": "MOEXFN"}   # only these are cached


def market_series(D) -> pd.DataFrame:
    """IMOEX, sector indexes (ISS daily cache) and BR/Si/GD (main-session close, roll-masked) daily
    log returns on the calendar; missing -> 0 so positions stay aligned with the stock contexts."""
    cal = D["ret"].index
    out = {"IMOEX": D["bench"]["imoex_ret"]}
    for sec, idx in SECTOR_INDEX.items():   # all cached ISS daily files for the index, combined (no download)
        parts = []
        for f in sorted(CACHE.glob(f"stock_index_{idx}_24_*.parquet")):
            x = pd.read_parquet(f)
            if not x.empty:
                parts.append(pd.Series(x["close"].to_numpy(), index=pd.to_datetime(x["begin"]).dt.normalize()))
        c = pd.concat(parts)
        c = c[~c.index.duplicated(keep="last")].sort_index()
        out[idx] = np.log(c.reindex(cal)).diff()
    fut = al.load_long(ROOT / "data_pipeline/data/processed/candles_10m/futures.parquet",
                       tickers=["BR", "Si", "GD"], end=cal.max())
    fr = al.futures_main_returns(fut, cal)
    for k in fr.columns:
        out[k] = fr[k]
    return pd.DataFrame(out).reindex(cal).fillna(0.0)


def broadcast(series: pd.Series, like: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(np.repeat(series.reindex(like.index).to_numpy()[:, None], like.shape[1], 1), like.index, like.columns)


def covariate_sets(D, M) -> dict:
    base = covariate_panels(D)
    ret = D["ret"]
    sec = pd.DataFrame({t: M[SECTOR_INDEX[SECTOR_OF[t]]] if SECTOR_OF.get(t) in SECTOR_INDEX else M["IMOEX"]
                        for t in ret.columns}).reindex(ret.index)
    with_sec = {**base, "sector": sec}
    with_fut = {**with_sec, **{k: broadcast(M[k], ret) for k in ["BR", "Si", "GD"]}}
    return {"base": base, "sector": with_sec, "futures": with_fut}


def group_fns(D):
    val = D["value"].rolling(60, min_periods=30).median()
    def sector(a, tick):
        g = {}
        for t in tick:
            g.setdefault(SECTOR_OF.get(t, "misc"), []).append(t)
        small = [t for k, v in g.items() if len(v) < 3 for t in v]
        groups = [v for v in g.values() if len(v) >= 3]
        return groups + ([small] if small else [])
    def liquidity(a, tick):
        v = val.loc[a, tick].sort_values(ascending=False)
        h = len(v) // 2
        return [list(v.index[:h]), list(v.index[h:])]
    def random20(a, tick):
        rng = np.random.default_rng(int(a.value // 86_400_000_000_000))
        perm = list(rng.permutation(tick)); k = max(1, round(len(perm) / 20))
        return [list(x) for x in np.array_split(perm, k)]
    return {"sector": sector, "liquidity": liquidity, "random20": random20}


CONFIGS = {   # name: (phase, spec)
    "uni":        ("C0", dict()),
    "xl":         ("C0", dict(xl=True)),
    "cov":        ("C0", dict(cov="base")),
    "xl_cov":     ("C0", dict(xl=True, cov="base")),
    "xl_sector":  ("C1", dict(xl=True, groups="sector")),
    "xl_market":  ("C1", dict(xl=True, extras=True)),
    "xl_liq":     ("C1", dict(xl=True, groups="liquidity")),
    "xl_rand20":  ("C1", dict(xl=True, groups="random20")),
    "cov_sector": ("C2", dict(cov="sector")),
    "cov_fut":    ("C2", dict(cov="futures")),
    "ctx64":      ("C3", dict(ctx=64)),
    "ctx128":     ("C3", dict(ctx=128)),
    "ctx512":     ("C3", dict(ctx=512)),
    "resid":      ("C4", dict(target="resid")),
    "weekly":     ("C4", dict(target="weekly")),
    "logprice":   ("C4", dict(target="logprice")),
}


def config_preds_path(name):
    if name == "uni":
        return FC_DIR / "preds.parquet"
    return VAR_DIR / name / "preds.parquet"


def run_config_forecast(name, spec, D, M, COV, G, pipe, anchors=None, out=None):
    f = out or config_preds_path(name)
    if f.exists():
        return pd.read_parquet(f)
    f.parent.mkdir(parents=True, exist_ok=True)
    cal = D["ret"].index
    if anchors is None:
        anchors = cal[cal >= pd.Timestamp(FC_CFG["first_anchor"])]
    target = spec.get("target", "ret")
    panel, H, stride, ctx = D["ret"], FC_CFG["horizon"], 1, spec.get("ctx", FC_CFG["context_len"])
    if target == "resid":
        panel = al.loo_residual(D["ret"])
    elif target == "weekly":
        panel, H, stride, ctx = D["ret"].rolling(5, min_periods=5).sum(), 1, 5, 100
    elif target == "logprice":
        panel = np.log(D["close"])
    xl = spec.get("xl", False)
    p = al.generate_forecasts(pipe, panel, D["eligible"], anchors, ctx=ctx, H=H,
                              anchors_per_call=1 if xl else FC_CFG["anchors_per_call"],
                              out_path=None, covariates=COV[spec["cov"]] if "cov" in spec else None,
                              cross_learning=xl, group_fn=G[spec["groups"]] if "groups" in spec else None,
                              extra_series=M if spec.get("extras") else None, stride=stride)
    if target == "logprice":            # levels -> cumulative log returns from the anchor
        lvl = np.log(D["close"]).stack(); lvl.index.names = ["anchor", "ticker"]
        base = p.join(lvl.rename("lvl"), on=["anchor", "ticker"])["lvl"].to_numpy()
        qcols = [c for c in p.columns if c.startswith("q")]
        p[qcols] = p[qcols].to_numpy() - base[:, None]
    p.to_parquet(f)
    return p


def stage_configs(only=None):
    VAR_DIR.mkdir(parents=True, exist_ok=True)
    D = load_data(); M = market_series(D); COV = covariate_sets(D, M); G = group_fns(D)
    names = only or list(CONFIGS)
    pipe = None
    import time
    for nm in names:
        if not config_preds_path(nm).exists():
            pipe = pipe or load_pipeline()
            t0 = time.time()
            run_config_forecast(nm, CONFIGS[nm][1], D, M, COV, G, pipe)
            print(f"[{nm}] forecast done in {time.time() - t0:.0f}s", flush=True)
    base_preds = load_preds()
    Xb = build_inputs(base_preds, D)
    base_mask, base_sig = Xb["mask"], Xb[f"F{LAG}"]["MED_SIG"]
    classic_pnl = {k: bt_stats(books(Xb[f"classic{LAG}"][k], Xb, "LS"), Xb, "ext_dev")[1]["net"]
                   for k in BT_CFG["classic"]}
    V = vol_inputs(Xb, DEV_DIR)[0]
    rows, S = [], {}
    for nm in list(CONFIGS):
        f = config_preds_path(nm)
        if not f.exists():
            continue
        spec = CONFIGS[nm][1]
        feat = {"weekly": al.chronos_features_block, "logprice": al.chronos_features_cumulative}.get(spec.get("target"))
        r, S[nm] = evaluate_variant(nm, load_preds(f), D, classic_pnl, V, tag=f"C_{CONFIGS[nm][0]}",
                                    feat_fn=feat, base_mask=base_mask, base_sig=base_sig)
        r["phase"] = CONFIGS[nm][0]; r["spec"] = json.dumps(spec)
        r["trackB_comparable"] = spec.get("target") != "resid"
        rows.append(r)
        print(f"[{nm}] evaluated", flush=True)
    T = pd.DataFrame(rows).set_index("variant")
    for nm in T.index:
        if nm == "uni":
            continue
        T.loc[nm, "ic_diff_t_vs_uni"] = al.nw_tstat((S[nm]["ic"] - S["uni"]["ic"]).dropna(), NW)["t"]
        T.loc[nm, "qlike_sc_dm_t_vs_uni"] = al.dm_test(S[nm]["qlike_sc"], S["uni"]["qlike_sc"], NW)["t"]
        T.loc[nm, "qlike_dm_t_vs_uni"] = al.dm_test(S[nm]["qlike"], S["uni"]["qlike"], NW)["t"]
        T.loc[nm, "pinball_dm_t_vs_uni"] = al.dm_test(S[nm]["pinball"], S["uni"]["pinball"], 0)["t"]
        T.loc[nm, "sharpe_boot_p_vs_uni"] = al.sharpe_diff_bootstrap(S[nm]["pnl"], S["uni"]["pnl"])["p_one_sided"]
    T.to_csv(VAR_DIR / "configs_map.csv")
    pd.set_option("display.width", 250)
    print(T.drop(columns=["spec"]).round(3).T.to_string())
    return T


# %% [markdown]
# ## Stage `improve` (step 3): mimic, combination, turnover control, vol calibration
# Config-agnostic: `improve <config>` evaluates on that config's forecasts (default: baseline `uni`),
# on the baseline universe mask, extended dev 2021-2024. Every variant is logged as a trial.

# %%
IMP_DIR = ROOT / "forecasting/runs/alpha_improve"
MONTHLY = 21


def eval_signal(name, sig, X, classic_pnl, fwd=None, n_tranches=None, period="ext_dev", tag="S3", log=True):
    """IC (vs the matching-horizon forward return), LS net Sharpe/turnover, spanning alpha t vs the
    classic LS books, Fama-MacBeth t with classic controls. Returns (row, pnl series, ic series)."""
    nt = n_tranches or BT_CFG["rebalance"]["n_tranches"]
    steps = tuple(range(LAG + 1, LAG + 1 + nt))
    fwd = fwd if fwd is not None else al.forward_returns(X["D"]["ret"], steps)
    lo, hi = period_bounds(period)
    cal = X["cal"]; last_ok = cal[cal <= hi][-1 - max(steps)]
    d = cal[(cal >= lo) & (cal <= last_ok)]
    ic = al.ic_series(sig, fwd, X["mask"]).reindex(d).dropna()
    r = al.nw_tstat(ic, 2 * (nt - 1))
    W = books(sig, X, "LS")
    st, bt = bt_stats(W, X, period, n_tranches=nt)
    Xs = pd.DataFrame({k: classic_pnl[(k, nt)] for k in BT_CFG["classic"]}).reindex(bt.index)
    Xs["IMOEX"] = np.expm1(X["D"]["bench"]["imoex_ret"]).reindex(bt.index)
    span = al.ols_nw(bt["net"], Xs, lags=2 * nt)
    C = X[f"classic{LAG}"]
    fm = al.fama_macbeth(fwd, {"sig": sig, "mom_12_1": C["mom_12_1"], "rev_5d": C["rev_5d"], "rev_1d": C["rev_1d"],
                               "lowvol_60d": C["lowvol_60d"], "size": C["size"]}, X["mask"], lags=2 * (nt - 1), dates=d)
    row = dict(variant=name, rebalance_days=nt, ic=r["mean"], ic_t=r["t"], ls_net_sharpe=st.get("sharpe"),
               ls_gross_sharpe=st.get("gross_sharpe"), turnover=st.get("turnover_ann"), breakeven_bps=st.get("breakeven_bps"),
               span_alpha_ann=float(span.loc["const", "coef"] * 252), span_alpha_t=float(span.loc["const", "t"]),
               fm_t=float(fm.loc["sig", "t"]))
    if log:
        al.append_trial(LEDGER, track="A", tag=tag, period=period, signal=name, book=f"LS_{nt}d", exec_lag=LAG,
                        cost_bps=COST, borrow=BORROW, ic_t=r["t"], net_sharpe=st.get("sharpe"),
                        daily_sr=(st.get("sharpe") or np.nan) / np.sqrt(252))
    return row, bt["net"], ic


def stage_improve(config="uni"):
    out = IMP_DIR / config; out.mkdir(parents=True, exist_ok=True)
    D = load_data()
    base = build_inputs(load_preds(), D)
    spec = CONFIGS[config][1]
    feat = {"weekly": al.chronos_features_block, "logprice": al.chronos_features_cumulative}.get(spec.get("target"))
    preds = load_preds(config_preds_path(config))
    X = build_inputs(preds, D, feat); X["preds"] = preds
    X["mask"] = base["mask"] & X[f"F{LAG}"]["MED"].notna()
    C = X[f"classic{LAG}"]
    chron = X[f"F{LAG}"]["MED_SIG"]
    classic_pnl = {(k, nt): bt_stats(books(C[k], X, "LS"), X, "ext_dev", n_tranches=nt)[1]["net"]
                   for k in BT_CFG["classic"] for nt in (BT_CFG["rebalance"]["n_tranches"], MONTHLY)}
    rows, pnl, ics = [], {}, {}
    def add(name, sig, nt=None, tag="S3"):
        r, p, i = eval_signal(name, sig, X, classic_pnl, n_tranches=nt, tag=f"{tag}_{config}")
        rows.append(r); pnl[name] = p; ics[name] = i
        print(f"  {name:28s} IC {r['ic']:+.3f} (t {r['ic_t']:+.2f})  netSR {r['ls_net_sharpe']:+.2f}  "
              f"TO {r['turnover']:5.1f}  span t {r['span_alpha_t']:+.2f}  FM t {r['fm_t']:+.2f}", flush=True)
    print(f"[{config}] A) Chronos-mimic")
    add("chronos", chron, tag="S3ref")
    fit, oos = al.rolling_xs_fit(chron, al.context_features(D["ret"]), X["mask"])
    mimic_r2 = float((oos.loc["2021":"2024"] ** 2).mean())
    add("mimic", fit, tag="S3mimic")
    add("chronos_minus_mimic", al.xs_standardize(chron, X["mask"]) - fit, tag="S3mimic")
    print(f"  mimic out-of-sample R^2 of the Chronos signal (mean per-date corr^2): {mimic_r2:.3f}")
    print(f"[{config}] B) combination (weights = trailing realized Fama-MacBeth slopes)")
    fwd = X[f"fwd{LAG}"]
    csig = {k: C[k] for k in BT_CFG["classic"]}
    slopes_all = al.xs_slopes(fwd, {**csig, "chronos": chron}, X["mask"])
    comp_c, Wc = al.rolling_composite(fwd, csig, X["mask"], horizon=max(STEPS[LAG]))
    comp_a, Wa = al.rolling_composite(fwd, {**csig, "chronos": chron}, X["mask"], horizon=max(STEPS[LAG]), slopes=slopes_all)
    add("combo_classic", comp_c, tag="S3combo"); add("combo_plus_chronos", comp_a, tag="S3combo")
    print(f"[{config}] C) turnover control")
    for hl in (5, 10, 21):
        add(f"chronos_smooth_hl{hl}", al.smooth_signal(chron, X["mask"], hl), tag="S3turn")
    add("chronos_monthly", chron, nt=MONTHLY, tag="S3turn")
    add("chronos_smooth_hl10_monthly", al.smooth_signal(chron, X["mask"], 10), nt=MONTHLY, tag="S3turn")
    add("combo_plus_chronos_hl10", al.smooth_signal(comp_a, X["mask"], 10), tag="S3turn")
    add("combo_classic_hl10", al.smooth_signal(comp_c, X["mask"], 10), tag="S3turn")
    T = pd.DataFrame(rows).set_index("variant")
    # paired: Chronos' contribution inside the composite, and each variant vs the raw Chronos book
    boot = al.sharpe_diff_bootstrap(pnl["combo_plus_chronos"], pnl["combo_classic"])
    sp = al.ols_nw(pnl["combo_plus_chronos"], pd.DataFrame({"combo_classic": pnl["combo_classic"],
                   **{k: classic_pnl[(k, 5)] for k in BT_CFG["classic"]}}).reindex(pnl["combo_plus_chronos"].index), lags=10)
    extra = dict(mimic_oos_r2=mimic_r2,
                 combo_chronos_vs_classic=dict(sharpe_diff=boot["diff"], boot_p=boot["p_one_sided"],
                                               ic_diff_t=al.nw_tstat((ics["combo_plus_chronos"] - ics["combo_classic"]).dropna(), NW)["t"],
                                               alpha_over_classic_combo_t=float(sp.loc["const", "t"]),
                                               mean_weight_chronos=float(Wa["chronos"].loc["2021":"2024"].mean())))
    for nm in T.index:
        if nm != "chronos" and T.loc[nm, "rebalance_days"] == 5:
            T.loc[nm, "sharpe_boot_p_vs_chronos"] = al.sharpe_diff_bootstrap(pnl[nm], pnl["chronos"])["p_one_sided"]
    print(f"[{config}] D) vol calibration (Chronos σ level rescaled by trailing realized/forecast ratio)")
    steps = STEPS[0]
    rv_fwd = sum(D["rv"].shift(-h) for h in steps)
    vc = al.vol_chronos(X["F0"]["SIG"])
    V = vol_inputs(base, DEV_DIR)[0]
    d = ic_dates(X, "ext_dev", steps)
    scale = al.rolling_vol_scale(vc, rv_fwd, X["mask"], horizon=max(steps))
    vcal = vc.mul(scale, axis=0)
    m = X["mask"].loc[d] & vcal.loc[d].notna() & V["ewma"].loc[d].notna() & V["garch"].loc[d].notna()
    Lc = al.vol_loss_panel(rv_fwd.loc[d], vcal.loc[d], m); L0 = al.vol_loss_panel(rv_fwd.loc[d], vc.loc[d], m)
    vol = dict(qlike_raw=float(L0.mean()), qlike_calibrated=float(Lc.mean()),
               dm_t_calibrated_vs_raw=al.dm_test(Lc, L0, NW)["t"])
    for k in ["ewma", "garch", "har_daily"]:
        # competitors get the identical causal level recalibration (fair: calibration is not Chronos-specific)
        sk = al.rolling_vol_scale(V[k], rv_fwd, X["mask"], horizon=max(steps))
        Lk = al.vol_loss_panel(rv_fwd.loc[d], V[k].mul(sk, axis=0).loc[d], m)
        vol[f"dm_t_vs_{k}_both_calibrated"] = al.dm_test(Lc, Lk, NW)["t"]      # negative = Chronos better
    p1 = preds[preds.h == 1]
    s1 = np.sqrt(scale).reindex(p1["anchor"]).to_numpy()
    for lvl in (0.05, 0.1):
        q = (p1["q0.5"] + (p1[f"q{lvl:g}"] - p1["q0.5"]) * s1).rename("q")
        qw = pd.concat([p1[["anchor", "ticker"]], q], axis=1).pivot(index="anchor", columns="ticker", values="q")
        vol[f"q{lvl:g}_hit_calibrated"] = al.var_coverage(D["ret"], qw.reindex(index=X["cal"], columns=D["ret"].columns).loc[d],
                                                           lvl, X["mask"].loc[d])["hit_rate"]
    al.append_trial(LEDGER, track="B", tag=f"S3volcal_{config}", period="ext_dev", signal="chronos_sig_calibrated",
                    book="vol_forecast", exec_lag=0, cost_bps=np.nan, borrow=np.nan, net_sharpe=np.nan, daily_sr=np.nan)
    extra["vol_calibration"] = vol
    print(json.dumps(extra, indent=1, default=float))
    T.to_csv(out / "improve_table.csv")
    (out / "improve_extra.json").write_text(json.dumps(extra, indent=1, default=float))
    return T, extra


# %% [markdown]
# ## Stage `rvtarget` (step 3, Track B / I1): Chronos forecasts the log realized-variance series itself

# %%
RV_EPS = 1e-7   # floor for log(RV): ~0.03% daily vol; days with no trades would otherwise be -inf


def rv_forecast_path(name):
    return VAR_DIR / f"rv_{name}" / "preds.parquet"


def stage_rvtarget(threads=3):
    import torch
    torch.set_num_threads(threads)
    D = load_data()
    panel = np.log(D["rv"].clip(lower=0) + RV_EPS)
    cal = D["ret"].index
    anchors = cal[cal >= pd.Timestamp(FC_CFG["first_anchor"])]
    pipe = None
    for name, kw in {"uni": dict(), "xl": dict(cross_learning=True, anchors_per_call=1)}.items():
        f = rv_forecast_path(name)
        if f.exists():
            continue
        f.parent.mkdir(parents=True, exist_ok=True)
        pipe = pipe or load_pipeline()
        kw = dict(kw); apc = kw.pop("anchors_per_call", FC_CFG["anchors_per_call"])
        al.generate_forecasts(pipe, panel, D["eligible"], anchors, ctx=FC_CFG["context_len"], H=5,
                              anchors_per_call=apc, out_path=f, **kw)
        print(f"[rv_{name}] forecast done", flush=True)
    return evaluate_rvtarget(D)


def rv_var_forecast(preds, cal, cols):
    """Σ_{h=1..5} E[RV_{d+h}] from log-RV quantiles (E[exp] per step, minus the floor)."""
    qcols = [f"q{q:g}" for q in al.NATIVE_QUANTILES]
    e = al.mean_exp_quantiles(preds[qcols].to_numpy()) - RV_EPS
    s = pd.Series(np.maximum(e, 1e-10), index=pd.MultiIndex.from_frame(preds[["anchor", "ticker"]]))
    return s.groupby(level=[0, 1]).sum().unstack("ticker").reindex(index=cal, columns=cols)


def evaluate_rvtarget(D):
    base = build_inputs(load_preds(), D)
    V = vol_inputs(base, DEV_DIR)[0]
    steps = STEPS[0]
    rv_fwd = sum(D["rv"].shift(-h) for h in steps)
    d = ic_dates(base, "ext_dev", steps)
    models = {k: V[k] for k in ["ewma", "garch", "har_daily", "har_rv_ceiling"]}
    models["chronos_ret_uni"] = V["chronos"]
    xlp = config_preds_path("xl")
    if xlp.exists():
        models["chronos_ret_xl"] = al.vol_chronos(build_inputs(load_preds(xlp), D)["F0"]["SIG"])
    for nm in ["uni", "xl"]:
        f = rv_forecast_path(nm)
        if f.exists():
            models[f"chronos_rv_{nm}"] = rv_var_forecast(pd.read_parquet(f), D["ret"].index, D["ret"].columns)
    m = base["mask"].loc[d]
    for v in models.values():
        m &= v.loc[d].notna()
    rows, L, Lc = [], {}, {}
    for k, v in models.items():
        sc = al.rolling_vol_scale(v, rv_fwd, base["mask"], horizon=max(steps))      # identical causal calibration for all
        L[k] = al.vol_loss_panel(rv_fwd.loc[d], v.loc[d], m)
        Lc[k] = al.vol_loss_panel(rv_fwd.loc[d], v.mul(sc, axis=0).loc[d], m)
        mz = al.mincer_zarnowitz(rv_fwd.loc[d], v.loc[d], m)
        rows.append(dict(model=k, qlike_raw=float(L[k].mean()), qlike_calibrated=float(Lc[k].mean()), mz_r2_log=mz["r2_log"]))
    T = pd.DataFrame(rows).set_index("model")
    for cand in [k for k in models if k.startswith("chronos_rv")]:
        for k in ["ewma", "garch", "har_daily", "har_rv_ceiling", "chronos_ret_uni", "chronos_ret_xl"]:
            if k in L:
                T.loc[cand, f"dm_raw_vs_{k}"] = al.dm_test(L[cand], L[k], NW)["t"]
                T.loc[cand, f"dm_cal_vs_{k}"] = al.dm_test(Lc[cand], Lc[k], NW)["t"]
        al.append_trial(LEDGER, track="B", tag="S3rv", period="ext_dev", signal=cand, book="vol_forecast",
                        exec_lag=0, cost_bps=np.nan, borrow=np.nan, net_sharpe=np.nan, daily_sr=np.nan)
    out = IMP_DIR / "rvtarget"; out.mkdir(parents=True, exist_ok=True)
    T.to_csv(out / "rvtarget_table.csv")
    pd.set_option("display.width", 250)
    print(T.round(3).T.to_string())
    return T


# %% [markdown]
# ## Stage `select` (after Phase C): pick winners by the pre-stated rules, C3 follow-up, step 3 on winners
# Track A winner: highest `fm_t_over_uni` (incremental over the baseline Chronos signal + classic
#   factors) among configs with fm_t_over_uni > 2; none -> baseline `uni`.
# Track B winner: most negative `qlike_sc_dm_t_vs_uni` among comparable configs with t < -2; none -> `uni`.

# %%
def select_winners(T: pd.DataFrame) -> dict:
    a = T[(T.index != "uni") & (T["fm_t_over_uni"] > 2)]
    b = T[(T.index != "uni") & (T["trackB_comparable"].astype(bool)) & (T["qlike_sc_dm_t_vs_uni"] < -2)]
    return dict(track_a=a["fm_t_over_uni"].idxmax() if len(a) else "uni",
                track_b=b["qlike_sc_dm_t_vs_uni"].idxmin() if len(b) else "uni")


def stage_select(run_followups=True):
    T = pd.read_csv(VAR_DIR / "configs_map.csv", index_col=0)
    W = select_winners(T)
    print("winners (pre-stated rules):", W, flush=True)
    followups = []
    for track, cfg in W.items():
        if cfg == "uni" or not run_followups:
            continue
        for ctx in (128, 512):                     # C3 follow-up on the winning config
            nm = f"{cfg}_ctx{ctx}"
            if nm not in CONFIGS:
                CONFIGS[nm] = ("C3b", {**CONFIGS[cfg][1], "ctx": ctx})
            followups.append(nm)
    if followups:
        T = stage_configs(sorted(set(followups)))  # forecasts the new ones, re-evaluates the full map
        W = select_winners(T)
        print("winners after C3 follow-up:", W, flush=True)
    (VAR_DIR / "winners.json").write_text(json.dumps(W, indent=1))
    for cfg in sorted(set(W.values())):
        print(f"=== step 3 on {cfg} ===", flush=True)
        stage_improve(cfg)
    return W


# %%
if __name__ == "__main__" and len(sys.argv) > 1:
    stage = sys.argv[1]
    if stage == "data":
        stage_data()
    elif stage == "data_holdout":   # data preparation + QA only; no forecasts, no evaluation on 2025+
        cfg_h = yaml.safe_load(open(HERE / "configs/alpha_forecast_holdout.yaml"))
        stage_data(cfg_h, ROOT / "forecasting/runs/alpha_data_holdout", allow_download=False)
    elif stage == "forecast":
        stage_forecast(smoke="--smoke" in sys.argv)
    elif stage == "dev":
        if "--smoke" in sys.argv:   # code-path check on the 3-month smoke forecasts; scratch outputs + ledger
            scratch = Path(sys.argv[sys.argv.index("--smoke") + 1])
            stage_dev(FC_DIR / "preds_smoke.parquet", out_dir=scratch, tag="smoke", ledger=scratch / "ledger_smoke.csv")
        else:
            stage_dev(tag=sys.argv[sys.argv.index("--tag") + 1] + "_dev" if "--tag" in sys.argv else "v1_dev")
    elif stage == "variants":
        stage_variants()
    elif stage == "rvtarget":
        stage_rvtarget()
    elif stage == "select":
        stage_select()
    elif stage == "improve":
        stage_improve(sys.argv[2] if len(sys.argv) > 2 else "uni")
    elif stage == "configs":
        stage_configs(sys.argv[2].split(",") if len(sys.argv) > 2 else None)
    elif stage == "test":
        stage_test(tag=sys.argv[sys.argv.index("--tag") + 1] + "_test" if "--tag" in sys.argv else "v1_test")
    else:
        raise SystemExit(f"unknown stage {stage}")
