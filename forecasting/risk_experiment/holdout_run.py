"""Confirmatory evaluation of the FROZEN arms (R6/R7; pre-registration in README between PREREG markers).

  .venv/bin/python forecasting/risk_experiment/holdout_run.py dryrun      dev period, dev sources (validation)
  HOLDOUT_UNLOCK=1 .venv/bin/python forecasting/risk_experiment/holdout_run.py sources    holdout Chronos sources
  HOLDOUT_UNLOCK=1 .venv/bin/python forecasting/risk_experiment/holdout_run.py evaluate   holdout, ONCE

Only the frozen arms, their reference arms and the sources they need are built. Arms are constructed with
the same functions as in R4 (risk_run / risk_arms / risk_lib); calibrations and rolling fits use all past
data, so holdout forecasts in early 2025 are calibrated on late-2024 dev forecasts (causal). The dry run
evaluates the dev period with this code and must reproduce the R4 dev numbers of the frozen arms.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "colab"))
import risk_run as rr  # noqa: E402

al, rl, ra, cs = rr.al, rr.rl, rr.ra, rr.cs
NW, Z = rr.NW, stats.norm.ppf(0.95)

# ── frozen by the pre-registration (dev selection; F rule applied before the PREREG commit) ──────────────
# (re-selected after the plan-H universe correction)
FROZEN = {"U1": {"C": "mixeq_chr_N1ret", "B": "fhs_loghar", "refs": ("rm", "garch_t")},
          "U2": {"C": "fac_chr", "B": "port_loghar", "refs": ("ewma", "garch")},
          "U3": {"C": "mixeq_chr_N4rv", "B": "ewma", "refs": ("ewma", "garch")},
          "U4": {"C": "mixeq_chr_Z3_cal", "B": "ols_beta", "refs": ("ewma", "garch")}}
MARGIN_COLS = {"U1": "delta_50pct_gap", "U4": "delta_0.5pp_vol"}   # non-inferiority δ (U2, U3: not testable)
SOURCES = ("Z3", "N1", "N4", "N5m", "N5e")


def margins() -> dict:
    T = pd.read_csv(HERE / "results" / "dev" / "prereg_power.csv", index_col=0)
    return {u: float(T.loc[u, c]) for u, c in MARGIN_COLS.items()}


def unlocked() -> bool:
    import make_bundle
    return os.environ.get("HOLDOUT_UNLOCK") == "1" and make_bundle.prereg_commit_ok()


def holdout_source_path(name: str) -> Path:
    return rr.OUT / "sources" / "holdout" / name / "preds.parquet"


def load_sources(period: str) -> dict:
    """Dev forecasts; for the holdout, dev + holdout forecasts concatenated (the panels agree on the overlap,
    holdout_qa), so rolling calibrations at the start of 2025 see late-2024 forecasts."""
    dev = {"Z3": rr.SRC["Z3"], "N1": rr.SRC["N1"], "N4": rr.SRC["N4"], "N5m": rr.source_path("N5m"), "N5e": rr.source_path("N5e")}
    P = {k: pd.read_parquet(v) for k, v in dev.items()}
    if period == "holdout":
        for k in SOURCES:
            h = pd.read_parquet(holdout_source_path(k))
            P[k] = pd.concat([P[k][P[k]["anchor"] < pd.Timestamp(rr.HOLDOUT[0])], h], ignore_index=True)
    return P


def setup(period: str):
    panel = rr.DEV_PANEL if period == "dev" else rr.FULL_PANEL
    D = rr.load_panel(panel, ("ret", "rv", "eligible", "bench", "value"))
    cal, cols = D["ret"].index, D["ret"].columns
    S = pd.read_csv(rr.OUT / "stress.csv", index_col=0, parse_dates=True)["stress"].reindex(cal)
    build_span = rr.DEV if period == "dev" else (rr.DEV[0], rr.HOLDOUT[1])      # calibration history
    eval_span = rr.DEV if period == "dev" else rr.HOLDOUT
    inb = pd.DataFrame(np.repeat(cal.isin(rr.span(cal, build_span))[:, None], len(cols), 1), cal, cols)
    ine = pd.DataFrame(np.repeat(cal.isin(rr.span(cal, eval_span))[:, None], len(cols), 1), cal, cols)
    return D, S, inb, ine


def build_arms(period: str, D, inb) -> dict:
    ret, rv, cal, cols = D["ret"], D["rv"], D["ret"].index, D["ret"].columns
    y1, steps = ret.shift(-1), (1, 2, 3, 4, 5)
    mask1 = D["eligible"] & inb & y1.notna()
    mask5 = D["eligible"] & inb
    P = load_sources(period)
    A = {}
    # U1 (as build_u1_arms)
    s_lh = np.sqrt(al.vol_har_log(rv, (1,), mask=D["eligible"], pooled=True, market=True))
    V, E = rl.fhs_var_es(y1 / s_lh, s_lh, mask1, 0.05, horizon=1)
    A["fhs_loghar"] = (V, E)
    Vc, Ec = ra.chronos_vares(P["N1"], (0.05,), cal, cols, variate="ret", h=1)[0.05]
    A["mixeq_chr_N1ret"] = (rl.vincentize([Vc, V], [0.5, 0.5]), rl.vincentize([Ec, E], [0.5, 0.5]))
    A["rm"] = ra.normal_var_es(np.sqrt(al.vol_ewma(ret, 1)), 0.05)
    s2, nu, mu = ra.garch_t_1step(ret)
    A["garch_t"] = ra.t_var_es(np.sqrt(s2), nu, 0.05, mu)
    # 5-day variance arms (as build_vol_arms / classical_vol_panel)
    Vc5 = rr.classical_vol_panel(D)
    r5sq = sum(ret.shift(-h) for h in steps) ** 2
    A["ewma"], A["garch"] = Vc5["ewma"], Vc5["garch"]
    A["mixeq_chr_N4rv"] = rl.geo_mix([ra.chronos_rv(P["N4"], (1,), cal, cols, variate="logrv"), Vc5["loghar_pooled_mkt"]], [0.5, 0.5])
    mz = rl.geo_mix([ra.chronos_rv(P["Z3"], steps, cal, cols), Vc5["loghar_pooled_mkt"]], [0.5, 0.5])
    A["mixeq_chr_Z3_cal"] = mz.mul(al.rolling_vol_scale(mz, r5sq, mask5, horizon=5), axis=0)
    # N5 factor arms (as build_n5_arms)
    S5 = rr.n5_series_from_panel(D) if period == "holdout" else rr.build_n5_series(D)
    lh = None if period == "dev" else al.vol_har_log(S5["resid_rv"], steps, mask=D["eligible"], pooled=True, market=True)
    fac, port = rr.build_n5_arms(D, S5, mask5, preds=(P["N5m"], P["N5e"]), loghar_resid=lh)
    A["fac_chr"], A["port_loghar"] = fac["fac_chr"], port["port_loghar"]
    A["_beta_d"] = al.trailing_betas(ret, D["bench"]["imoex_ret"], 250, 120)
    return A


def one_sided(t: float) -> float:
    return float(stats.norm.cdf(t))                     # H1: arm better (negative loss difference)


def ni_test(d: pd.Series, delta: float) -> dict:
    """Non-inferiority: H0 mean(L_C − L_B) >= δ; reject if the one-sided 95% upper bound < δ."""
    nw = al.nw_tstat(d, NW)
    return {"mean_diff": nw["mean"], "se": nw["se"], "upper95": nw["mean"] + Z * nw["se"], "delta": delta,
            "p": float(stats.norm.cdf((nw["mean"] - delta) / nw["se"])), "n": nw["n"]}


def dm(la, lb) -> dict:
    r = al.dm_test(la, lb, NW)
    return {"t": r["t"], "p": one_sided(r["t"])}


def evaluate(period: str) -> dict:
    D, S, inb, ine = setup(period)
    A = build_arms(period, D, inb)
    ret, cal = D["ret"], D["ret"].index
    steps, delta = (1, 2, 3, 4, 5), margins()
    res = {}
    # U1
    y1 = ret.shift(-1)
    M = D["eligible"] & ine & y1.notna()
    for k in ("mixeq_chr_N1ret", "fhs_loghar", "rm", "garch_t"):
        V, E = A[k]
        M &= V.lt(0) & E.lt(V)
    L = {k: rl.fz0_panel(y1, *A[k], M, 0.05) for k in ("mixeq_chr_N1ret", "fhs_loghar", "rm", "garch_t")}
    res["U1"] = claims("U1", L, delta.get("U1"), S)
    # U2/U3 on one universe: eligible, R5 finite, all inputs finite
    R5 = ra.forward_simple_return(ret, steps)
    rf = D["bench"]["rf"].reindex(cal)
    rf5 = np.expm1(sum(np.log1p(rf.shift(-h)) for h in steps))
    U = D["eligible"] & ine & R5.notna() & A["ewma"].gt(0) & A["garch"].gt(0) & A["mixeq_chr_N4rv"].gt(0) & A["fac_chr"][1].notna()
    U &= pd.DataFrame(np.repeat(A["port_loghar"].gt(0).to_numpy()[:, None], U.shape[1], 1), U.index, U.columns)
    dates = U.index[U.sum(axis=1) >= 10]
    ec = al.ewma_corr(ret)
    corr = {d: pd.DataFrame(C, index=ec["cols"], columns=ec["cols"]) for d, C in ec["C"].items() if d in set(dates)}
    target5 = rr.VT_TARGET_ANNUAL * np.sqrt(5 / 252)
    drd = ra.portfolio_paths({k: A[k] for k in ("ewma", "garch", "mixeq_chr_N4rv")}, corr, R5, rf5, U, dates, target5)
    fac = ra.n5_portfolio_paths({"fac_chr": A["fac_chr"]}, {"port_loghar": A["port_loghar"]},
                                A["_beta_d"], R5, rf5, U, pd.DatetimeIndex(drd["ewma"]["gmv"].index), target5)
    common = fac["fac_chr"]["gmv"].index
    paths = {**{k: {m: s.loc[common] for m, s in v.items()} for k, v in drd.items()}, **fac}
    res["U3"] = claims("U3", {k: paths[k]["gmv"] ** 2 for k in ("mixeq_chr_N4rv", "ewma", "garch")}, delta.get("U3"), S)
    res["U2"] = claims_u2({k: paths[k]["vt"] for k in ("fac_chr", "port_loghar", "ewma", "garch")})
    # U4 (as evaluate_u4, frozen arms only)
    r_f = al.futures_main_returns(al.load_long(rr.FUT_10M, tickers=["MX"], end=cal.max()), cal)["MX"]
    R5s, R5f = R5, ra.forward_simple_return(r_f.to_frame(), steps).iloc[:, 0]
    rho = ra.ewma_corr_with(ret, r_f)
    Hh = ra.hedge_ratios({k: A[k] for k in ("mixeq_chr_Z3_cal", "ewma", "garch")}, rho, al.vol_ewma(r_f.to_frame(), 5).iloc[:, 0])
    Hh["ols_beta"] = al.trailing_betas(ret, r_f, 250, 120)
    U4 = (D["eligible"] & ine & R5s.notna()).mul(R5f.notna(), axis=0).astype(bool)
    for h in Hh.values():
        U4 &= np.isfinite(h)
    d4 = U4.index[U4.sum(axis=1) >= 10]
    L4 = {k: (ra.hedged_returns(h, R5s, R5f).loc[d4] ** 2).where(U4.loc[d4]).mean(axis=1) for k, h in Hh.items()}
    res["U4"] = claims("U4", L4, delta.get("U4"), S)
    res["holm"] = holm(res)
    return res


def claims(use: str, L: dict, delta, S) -> dict:
    f = FROZEN[use]
    c, b, (r1, r2) = f["C"], f["B"], f["refs"]
    out = {"n_dates": int(len(L[c])), "mean_loss": {k: float(v.mean()) for k, v in L.items()},
           "L1_vs_" + r1: dm(L[c], L[r1]), "L1_vs_" + r2: dm(L[c], L[r2]), "L2_vs_B": dm(L[c], L[b])}
    # U3: the best classical arm is EWMA itself, so L2 coincides with the EWMA leg of L1
    out["L1_p"] = max(out["L1_vs_" + r1]["p"], out["L1_vs_" + r2]["p"])          # intersection-union
    if delta is not None:
        out["NI"] = ni_test((L[c] - L[b]).dropna(), delta)
    s = S.reindex(L[c].index).fillna(0)
    g = rl.giacomini_white(L[c], L[b], pd.DataFrame({"const": 1.0, "stress": s}), NW)
    out["GW_vs_B"] = {"p": g["p"], "stress_t": float(g["coefs"].loc["stress", "t"])}
    for reg, v in (("calm", 0), ("stress", 1)):
        d = (L[c] - L[b])[s.eq(v)]
        out[f"diff_vs_B_{reg}"] = al.nw_tstat(d, NW)
    return out


def claims_u2(vt: dict) -> dict:
    f = FROZEN["U2"]
    c, b = f["C"], f["B"]
    out = {"n_dates": int(len(vt[c]))}
    for ref in (*f["refs"], b):
        fb = rl.fko_fee_bootstrap(vt[c], vt[ref], 5, 252 / 5, n_boot=2000)
        out[f"fee_vs_{ref}"] = {"bps": fb["fee_bps_annual"], "p": fb["p_one_sided"]}
    out["L1_p"] = max(out[f"fee_vs_{r}"]["p"] for r in f["refs"])
    out["L2_p"] = out[f"fee_vs_{b}"]["p"]
    return out


def holm(res: dict, alpha: float = 0.05) -> dict:
    """Holm across uses: family A on the L1 p-values, then L2 among the uses that pass L1; family B (NI)."""
    def step(pv: dict) -> dict:
        order = sorted(pv, key=pv.get)
        passed, ok = {}, True
        for i, u in enumerate(order):
            ok = ok and pv[u] <= alpha / (len(order) - i)
            passed[u] = bool(ok)
        return passed
    l1 = step({u: r["L1_p"] for u, r in res.items() if u.startswith("U")})
    l2p = {u: (res[u]["L2_p"] if u == "U2" else res[u]["L2_vs_B"]["p"]) for u, ok in l1.items() if ok}
    ni = step({u: r["NI"]["p"] for u, r in res.items() if u.startswith("U") and "NI" in r})
    return {"L1": l1, "L2": step(l2p) if l2p else {}, "NI": ni}


def stage_sources():
    if not unlocked():
        raise SystemExit("holdout locked: needs HOLDOUT_UNLOCK=1 and a committed pre-registration block")
    import torch
    import alpha_run as R
    torch.set_num_threads(4)
    D = rr.load_panel(rr.FULL_PANEL, ("ret", "rv", "eligible", "bench"))
    cal = D["ret"].index
    anchors = rr.span(cal, rr.HOLDOUT)
    pipe = R.load_pipeline()
    for name, (block, stride, ctx, H) in rr.SOURCES.items():                    # N1, N4
        f = holdout_source_path(name)
        if not f.exists():
            cs.generate_multivariate(pipe, cs.rv_panels(D["ret"], D["rv"], block=block), D["eligible"], anchors,
                                     ctx=ctx, H=H, stride=stride, cross_learning=True, out_path=f, holdout_unlock=True)
    fz = holdout_source_path("Z3")
    if not fz.exists():                                                  # Z3: as alpha_run.stage_rvtarget "xl"
        fz.parent.mkdir(parents=True, exist_ok=True)
        al.generate_forecasts(pipe, np.log(D["rv"].clip(lower=0) + cs.RV_EPS), D["eligible"], anchors, ctx=250, H=5,
                              anchors_per_call=1, cross_learning=True, out_path=fz, holdout_unlock=True)
    S5 = rr.n5_series_from_panel(D)
    for name, (rv, elig) in {"N5m": (S5["mkt_rv"], S5["mkt_rv"].notna()),
                             "N5e": (S5["resid_rv"], D["eligible"] & S5["resid_rv"].notna())}.items():
        f = holdout_source_path(name)
        if not f.exists():
            cs.generate_multivariate(pipe, {"logrv": cs.rv_panels(rv * 0, rv)["logrv"]}, elig, anchors, ctx=250, H=5,
                                     cross_learning=True, out_path=f, holdout_unlock=True)
    print({k: len(pd.read_parquet(holdout_source_path(k))) for k in SOURCES})


def main(mode: str):
    if mode == "sources":
        return stage_sources()
    if mode == "evaluate" and not unlocked():
        raise SystemExit("holdout locked: needs HOLDOUT_UNLOCK=1 and a committed pre-registration block")
    period = "dev" if mode == "dryrun" else "holdout"
    out_dir = rr.OUT / ("dryrun" if period == "dev" else "holdout")
    if period == "holdout" and (out_dir / "results.json").exists():
        raise SystemExit("holdout already evaluated: results.json exists (the holdout is opened once)")
    res = evaluate(period)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "results.json").write_text(json.dumps(res, indent=1, default=float))
    print(json.dumps({u: {k: v for k, v in r.items() if k in ("mean_loss", "L1_p", "L2_vs_B", "NI", "L2_p", "fee_vs_ewma")}
                      for u, r in res.items() if u.startswith("U")}, indent=1, default=float))
    print("holm:", res["holm"])


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "dryrun")
