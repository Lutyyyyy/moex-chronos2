"""A1/A2 diagnostics for cov_fut (no new trials: re-slices existing forecasts).
Run from repo root: .venv/bin/python forecasting/alpha_experiment/diagnostics/covfut_stability.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np, pandas as pd
import alpha_run as R, alpha_lib as al

D = R.load_data(); M = R.market_series(D)
# A1: zero-filled covariate days in ext_dev (fillna(0) in market_series)
raw = {}
fut = al.load_long(R.ROOT / "data_pipeline/data/processed/candles_10m/futures.parquet", tickers=["BR", "Si", "GD"], end=D["ret"].index.max())
fr = al.futures_main_returns(fut, D["ret"].index)
cal = D["ret"].index; dev = cal[(cal >= "2021-01-01") & (cal <= "2024-12-31")]
print("A1 share of ext_dev days zero-filled (NaN before fillna):")
for k in ["BR", "Si", "GD"]:
    print(f"  {k}: {fr[k].reindex(dev).isna().mean():.3f}")

Xb = R.build_inputs(R.load_preds(), D); base_mask, base_sig = Xb["mask"], Xb[f"F{R.LAG}"]["MED_SIG"]
Xc = R.build_inputs(R.load_preds(R.config_preds_path("cov_fut")), D); Xc["mask"] = base_mask & Xc[f"F{R.LAG}"]["MED"].notna()
sig_c = Xc[f"F{R.LAG}"]["MED_SIG"]; C = Xb[f"classic{R.LAG}"]; fwd = Xb[f"fwd{R.LAG}"]
dates = R.ic_dates(Xb, "ext_dev", R.STEPS[R.LAG])

def fm_over(ds):
    fm = al.fama_macbeth(fwd, {"chronos": sig_c, "chronos_uni": base_sig, "mom_12_1": C["mom_12_1"], "rev_5d": C["rev_5d"],
                               "rev_1d": C["rev_1d"], "lowvol_60d": C["lowvol_60d"], "size": C["size"]},
                         Xc["mask"], lags=R.NW, dates=ds)
    return fm.loc["chronos", "t"], fm.loc["chronos", "mean"]
ic_c = al.ic_series(sig_c, fwd, Xc["mask"]).reindex(dates); ic_u = al.ic_series(base_sig, fwd, Xc["mask"]).reindex(dates)
shock = (dates >= "2022-02-01") & (dates <= "2022-04-30")
rows = {}
for lab, ds in [("all", dates), ("ex_2022_shock", dates[~shock])] + [(str(y), dates[dates.year == y]) for y in range(2021, 2025)]:
    t, b = fm_over(ds); d = (ic_c - ic_u).reindex(ds).dropna()
    rows[lab] = dict(n=len(ds), fm_t_over_uni=t, fm_slope=b, ic_cov=ic_c.reindex(ds).mean(), ic_uni=ic_u.reindex(ds).mean(),
                     ic_diff_t=al.nw_tstat(d, R.NW)["t"])
print("\nA2 stability (ext_dev 2021-2024):"); print(pd.DataFrame(rows).T.round(3).to_string())

classic_pnl = {k: R.bt_stats(R.books(C[k], Xb, "LS"), Xb, "ext_dev")[1]["net"] for k in R.BT_CFG["classic"]}
out = []
for nm, X, s in [("uni", dict(Xb, mask=Xc["mask"]), base_sig), ("cov_fut", Xc, sig_c)]:
    W = R.books(s, X, "LS")
    for lag in [0, 1]:
        for cost in [0, 5, 10, 20]:
            st, bt = R.bt_stats(W, X, "ext_dev", lag=lag, cost=cost)
            Xs = pd.DataFrame(classic_pnl); Xs["IMOEX"] = np.expm1(D["bench"]["imoex_ret"]).reindex(bt.index)
            sp = al.ols_nw(bt["net"], Xs.reindex(bt.index), lags=10)
            out.append(dict(cfg=nm, exec_lag=lag, cost_bps=cost, net_sharpe=st.get("sharpe"), span_alpha_ann=sp.loc["const", "coef"] * 252,
                            span_t=sp.loc["const", "t"]))
print("\nA2 cost / exec-lag sweep (LS book; classic spanning books at 5bps, lag 1):")
print(pd.DataFrame(out).round(3).to_string(index=False))
