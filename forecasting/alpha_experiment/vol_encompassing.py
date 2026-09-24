"""Vol encompassing test (pre-registered in prereg_vol_encompassing.md): is Chronos-RV encompassed
by the best classical vol model (pooled log-HAR with market term)?

Run: .venv/bin/python forecasting/alpha_experiment/vol_encompassing.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import alpha_lib as al  # noqa: E402


def ols_driscoll_kraay(y: pd.Series, X: pd.DataFrame, lags: int) -> pd.DataFrame:
    """Pooled panel OLS with constant; Driscoll-Kraay covariance (per-date score sums, Bartlett
    kernel). `y`/`X` are indexed by (date, ticker); returns coef, se, t per regressor."""
    df = pd.concat([y.rename("y"), X], axis=1).dropna()
    A = np.column_stack([np.ones(len(df)), df[X.columns].to_numpy(float)])
    b, *_ = np.linalg.lstsq(A, df["y"].to_numpy(float), rcond=None)
    e = df["y"].to_numpy(float) - A @ b
    g = pd.DataFrame(A * e[:, None], index=df.index).groupby(level=0).sum().to_numpy()
    T = len(g)
    S = g.T @ g
    for L in range(1, min(lags, T - 1) + 1):
        G = g[L:].T @ g[:-L]
        S += (1 - L / (lags + 1)) * (G + G.T)
    inv = np.linalg.inv(A.T @ A)
    se = np.sqrt(np.diag(inv @ S @ inv))
    names = ["const"] + list(X.columns)
    return pd.DataFrame({"coef": b, "se": se, "t": b / se}, index=names)


def encompassing(y_log, fc: dict, mask, dates, lags):
    """y_log, fc values: wide (date x ticker) log panels. Regress y on all forecasts in `fc`."""
    ok = mask.loc[dates]
    y = y_log.loc[dates][ok].stack()
    X = pd.DataFrame({k: v.loc[dates][ok].stack() for k, v in fc.items()})
    return ols_driscoll_kraay(y, X, lags)


def main():
    import alpha_run as R
    D = R.load_data()
    base = R.build_inputs(R.load_preds(), D)
    mask = base["mask"]
    steps = R.STEPS[0]
    rv_fwd = sum(D["rv"].shift(-h) for h in steps)
    H = pd.read_parquet(R.IMP_DIR / "rvtarget" / "loghar_cache.parquet")
    logs = {k: H.xs(k, axis=1, level=0) for k in H.columns.levels[0]}
    V = R.vol_inputs(base, R.DEV_DIR)[0]
    models = {"ewma": V["ewma"], "garch": V["garch"], "har_rv": V["har_rv_ceiling"], **logs}
    for nm in ["uni", "xl"]:
        models[f"chronos_rv_{nm}"] = R.rv_var_forecast(pd.read_parquet(R.rv_forecast_path(nm)), D["ret"].index, D["ret"].columns)
    d = R.ic_dates(base, "ext_dev", steps)
    m = mask.loc[d].copy()                     # identical to stage_volattr's mask
    for v in models.values():
        m &= v.loc[d].notna()
    m &= rv_fwd.loc[d].gt(0)
    y = np.log(rv_fwd)
    C, L, Ln = np.log(models["chronos_rv_xl"]), np.log(models["loghar_pooled_mkt"]), np.log(models["loghar"])

    e1 = encompassing(y, {"chronos_rv_xl": C, "loghar_pooled_mkt": L}, m, d, R.NW)
    combo = np.exp((C + L) / 2)
    lc = al.vol_loss_panel(rv_fwd.loc[d], combo.loc[d], m)
    ll = al.vol_loss_panel(rv_fwd.loc[d], models["loghar_pooled_mkt"].loc[d], m)
    lx = al.vol_loss_panel(rv_fwd.loc[d], models["chronos_rv_xl"].loc[d], m)
    e2 = al.dm_test(lc, ll, R.NW)
    e2x = al.dm_test(lc, lx, R.NW)

    rows = []
    splits = [(str(yr), d[d.year == yr]) for yr in sorted(set(d.year))]
    splits.append(("ex_2022_shock", d[(d < "2022-02-01") | (d > "2022-04-30")]))
    for lab, dd in splits:
        r = encompassing(y, {"chronos_rv_xl": C, "loghar_pooled_mkt": L}, m, dd, R.NW)
        rows.append(dict(split=lab, n_dates=len(dd), b_chronos=r.loc["chronos_rv_xl", "coef"], t_chronos=r.loc["chronos_rv_xl", "t"],
                         b_loghar=r.loc["loghar_pooled_mkt", "coef"], t_loghar=r.loc["loghar_pooled_mkt", "t"]))
    rn = encompassing(y, {"chronos_rv_xl": C, "loghar": Ln}, m, d, R.NW)
    S = pd.DataFrame(rows).set_index("split")

    pass1 = bool(e1.loc["chronos_rv_xl", "coef"] > 0 and e1.loc["chronos_rv_xl", "t"] > 2)
    pass2 = bool(e2["t"] < -2)
    verdict = ("E1+E2 pass: Chronos adds vol information and helps -> holdout candidate" if pass1 and pass2 else
               "E1 pass, E2 fail: statistically distinct but practically negligible; no holdout" if pass1 else
               "E1 fail: Chronos-RV encompassed by log-HAR; vol track closed")
    pd.set_option("display.width", 200)
    print(f"obs: {int(m.sum().sum())} over {len(d)} dates")
    print("\nE1 encompassing (y = log 5d RV):"); print(e1.round(4).to_string())
    print(f"\nE2 QLIKE: combo {lc.mean():.4f} | loghar_pooled_mkt {ll.mean():.4f} | chronos_rv_xl {lx.mean():.4f}")
    print(f"   DM combo vs loghar_pooled_mkt t = {e2['t']:.3f} (negative = combo better); vs chronos_rv_xl t = {e2x['t']:.3f}")
    print("\nReported: encompassing vs per-name loghar:"); print(rn.round(4).to_string())
    print("\nReported: by split:"); print(S.round(4).to_string())
    print(f"\nVERDICT: {verdict}")
    out = R.IMP_DIR / "rvtarget"
    e1.to_csv(out / "volenc_e1.csv"); S.to_csv(out / "volenc_splits.csv"); rn.to_csv(out / "volenc_vs_loghar_pername.csv")
    pd.Series(dict(qlike_combo=lc.mean(), qlike_loghar_pooled_mkt=ll.mean(), qlike_chronos_rv_xl=lx.mean(),
                   dm_t_combo_vs_loghar_pooled_mkt=e2["t"], dm_t_combo_vs_chronos_rv_xl=e2x["t"],
                   e1_pass=pass1, e2_pass=pass2, verdict=verdict)).to_csv(out / "volenc_summary.csv")
    for sig in ["E1_encompassing_chronos_rv_xl_vs_loghar_pooled_mkt", "E2_combo_eqw_geo_vs_loghar_pooled_mkt"]:
        al.append_trial(R.LEDGER, track="B", tag="S3volenc", period="ext_dev", signal=sig, book="vol_forecast",
                        exec_lag=0, cost_bps=np.nan, borrow=np.nan, net_sharpe=np.nan, daily_sr=np.nan)


if __name__ == "__main__":
    main()
