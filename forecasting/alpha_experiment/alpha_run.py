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
def stage_data(cfg=FC_CFG, out_dir=DATA_DIR):
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
    mcftr = al.fetch_iss_index_daily("MCFTR", "2020-01-01", end, CACHE / f"alpha_MCFTR_1d_2020-01-01_{end}.csv")
    kr = al.fetch_key_rate(CACHE / "key_rate.csv")
    for name, df in dict(close=P["close"], ret=P["ret"], stale=P["stale"], value=P["value"], rv=rv, eligible=elig).items():
        df.to_parquet(out_dir / f"{name}.parquet")
    bench = pd.DataFrame({"imoex_close": P["mkt_close"], "imoex_ret": P["mkt_ret"],
                          "mcftr_close": mcftr.reindex(P["calendar"]),
                          "rf": al.rf_daily(kr[kr.index <= pd.Timestamp(end)], P["calendar"])})
    bench["mcftr_ret"] = np.log(bench["mcftr_close"]).diff()
    bench.to_parquet(out_dir / "bench.parquet")
    return data_checks(shares, P, rv, elig, bench)


def data_checks(shares, P, rv, elig, bench) -> dict:
    """Sanity checks listed in the plan's Verification section."""
    cal = P["calendar"]
    # (1) main close differs from the evening 1d close on most post-2021 days
    d1 = al.load_long(ROOT / "data_pipeline/data/processed/candles_1d/shares.parquet",
                      tickers=["SBER", "GAZP", "LKOH"], columns=["ticker", "timestamp", "close"], end=FC_CFG["date_till"])
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
                            ever=int(elig.any().sum())),
        mcftr_missing_on_calendar=int(bench["mcftr_close"]["2021":].isna().sum()),
        rf_last=float(bench["rf"].iloc[-1]),
    )
    print(json.dumps(checks, indent=2, default=str))
    (DATA_DIR / "data_checks.json").write_text(json.dumps(checks, indent=2, default=str))
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


def build_inputs(preds: pd.DataFrame, D: dict) -> dict:
    """Everything derived from data + forecasts (signals, vol forecasts, masks). Causal by construction."""
    cal = D["ret"].index
    ret, value = D["ret"], D["value"]
    X = {"D": D, "cal": cal}
    for lag, steps in STEPS.items():
        F = al.chronos_features(preds, steps)
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


def bt_stats(W, X, period, lag=LAG, cost=COST, borrow=BORROW, excess=False):
    lo, hi = period_bounds(period)
    bt = al.run_backtest(W, X["D"]["R"], exec_lag=lag, n_tranches=BT_CFG["rebalance"]["n_tranches"],
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


def unique_trials(led, track, period):
    """Distinct variants (a re-run of the same variant is not a new trial); last row wins."""
    t = led[(led.track == track) & (led.period == period)]
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
    ta = unique_trials(led, "A", "dev")
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
    led = pd.read_csv(LEDGER); tb = unique_trials(led, "B", "dev")
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


# %%
if __name__ == "__main__" and len(sys.argv) > 1:
    stage = sys.argv[1]
    if stage == "data":
        stage_data()
    elif stage == "forecast":
        stage_forecast(smoke="--smoke" in sys.argv)
    elif stage == "dev":
        if "--smoke" in sys.argv:   # code-path check on the 3-month smoke forecasts; scratch outputs + ledger
            scratch = Path(sys.argv[sys.argv.index("--smoke") + 1])
            stage_dev(FC_DIR / "preds_smoke.parquet", out_dir=scratch, tag="smoke", ledger=scratch / "ledger_smoke.csv")
        else:
            stage_dev()
    elif stage == "test":
        stage_test()
    else:
        raise SystemExit(f"unknown stage {stage}")
