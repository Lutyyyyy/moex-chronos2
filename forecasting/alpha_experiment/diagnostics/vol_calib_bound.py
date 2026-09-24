"""Diagnostic only (not a trial): in-sample (oracle) calibration upper bound on ext_dev.
If Chronos cannot beat log-HAR even with hindsight-fitted calibration, causal calibration can't either.
Run from repo root: .venv/bin/python forecasting/alpha_experiment/diagnostics/vol_calib_bound.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np, pandas as pd
import alpha_run as R, alpha_lib as al
D = R.load_data(); base = R.build_inputs(R.load_preds(), D); mask = base["mask"]; steps = R.STEPS[0]
rv = sum(D["rv"].shift(-h) for h in steps)
H = pd.read_parquet(R.IMP_DIR / "rvtarget" / "loghar_cache.parquet"); logs = {k: H.xs(k, axis=1, level=0) for k in H.columns.levels[0]}
V = R.vol_inputs(base, R.DEV_DIR)[0]
models = {"ewma": V["ewma"], "garch": V["garch"], "har_rv": V["har_rv_ceiling"], **logs}
for nm in ["uni", "xl"]:
    models[f"chronos_rv_{nm}"] = R.rv_var_forecast(pd.read_parquet(R.rv_forecast_path(nm)), D["ret"].index, D["ret"].columns)
d = R.ic_dates(base, "ext_dev", steps); m = mask.loc[d].copy()
for v in models.values(): m &= v.loc[d].notna()
m &= rv.loc[d].gt(0)
P = pd.concat({"y": np.log(rv.loc[d])[m].stack(), **{k: np.log(models[k].loc[d])[m].stack() for k in ["chronos_rv_xl", "loghar_pooled_mkt", "loghar"]}}, axis=1)
P = P.replace([np.inf, -np.inf], np.nan).dropna(); print("obs", len(P))
y = P["y"]; lg = {k: P[k] for k in ["chronos_rv_xl", "loghar_pooled_mkt", "loghar"]}
RVS = np.exp(y)
def ql(f):  # per-date mean QLIKE from a stacked level forecast
    x = RVS / f
    return (x - np.log(x) - 1).groupby(level=0).mean()
def fit(cols):  # log-space OLS + smearing retransform (E[exp(resid)])
    A = np.column_stack([np.ones(len(y))] + [lg[c].to_numpy() for c in cols]); b = np.linalg.lstsq(A, y.to_numpy(), rcond=None)[0]
    yh = A @ b; smear = np.mean(np.exp(y.to_numpy() - yh)); return pd.Series(np.exp(yh) * smear, index=y.index), b
L = {}
L["loghar_pooled_mkt raw"] = ql(np.exp(lg["loghar_pooled_mkt"]))
L["chronos_rv_xl raw"] = ql(np.exp(lg["chronos_rv_xl"]))
L["arith avg (no fit)"] = ql((np.exp(lg["chronos_rv_xl"]) + np.exp(lg["loghar_pooled_mkt"])) / 2)
for nm, cols in [("loghar_pooled_mkt oracle-cal", ["loghar_pooled_mkt"]), ("chronos_rv_xl oracle-cal", ["chronos_rv_xl"]),
                 ("combo oracle (C + Lpm)", ["chronos_rv_xl", "loghar_pooled_mkt"]), ("combo oracle (C + Lpm + Lname)", ["chronos_rv_xl", "loghar_pooled_mkt", "loghar"])]:
    f, b = fit(cols); L[nm] = ql(f); print(f"{nm:34s} coefs {np.round(b, 3)}")
ref = L["loghar_pooled_mkt oracle-cal"]
print(f"\n{'model':34s} QLIKE   DM t vs loghar_pooled_mkt raw   DM t vs loghar_pooled_mkt oracle-cal")
for k, v in L.items():
    print(f"{k:34s} {v.mean():.4f}  {al.dm_test(v, L['loghar_pooled_mkt raw'], R.NW)['t']:8.2f}   {al.dm_test(v, ref, R.NW)['t']:8.2f}")

from scipy.optimize import minimize
def qfit(cols, x0):
    Z = np.column_stack([np.ones(len(y))] + [lg[c].to_numpy() for c in cols]); r = RVS.to_numpy()
    def obj(b):
        x = r / np.exp(Z @ b); return np.mean(x - np.log(x) - 1)
    b = minimize(obj, x0, method="Nelder-Mead", options=dict(maxiter=4000, xatol=1e-6, fatol=1e-9)).x
    return pd.Series(np.exp(Z @ b), index=y.index), b
print("\nQLIKE-optimal oracle fits (log f = a + sum b_k log F_k):")
Q = {}
for nm, cols, x0 in [("Lpm qlike-oracle", ["loghar_pooled_mkt"], [0, 1]), ("C qlike-oracle", ["chronos_rv_xl"], [0, 1]),
                     ("C+Lpm qlike-oracle", ["chronos_rv_xl", "loghar_pooled_mkt"], [0, .5, .5])]:
    f, b = qfit(cols, x0); Q[nm] = ql(f); print(f"{nm:22s} coefs {np.round(b,3)}  QLIKE {Q[nm].mean():.4f}")
print(f"DM C+Lpm vs Lpm (both QLIKE-oracle): t = {al.dm_test(Q['C+Lpm qlike-oracle'], Q['Lpm qlike-oracle'], R.NW)['t']:.2f}")
print(f"DM C vs Lpm (both QLIKE-oracle):     t = {al.dm_test(Q['C qlike-oracle'], Q['Lpm qlike-oracle'], R.NW)['t']:.2f}")
for yr in [2021, 2022, 2023, 2024]:
    k = Q['C+Lpm qlike-oracle'].index.year == yr
    print(f"  {yr}: combo {Q['C+Lpm qlike-oracle'][k].mean():.4f} vs Lpm {Q['Lpm qlike-oracle'][k].mean():.4f}  DM t {al.dm_test(Q['C+Lpm qlike-oracle'][k], Q['Lpm qlike-oracle'][k], R.NW)['t']:.2f}")
