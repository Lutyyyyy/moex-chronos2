"""Pre-registration aid (wrap-up W0.3): precision of 'Chronos minus best classical' per use on dev, scaled
to the holdout length, and the power of a non-inferiority test under candidate margins.
Dev data only; no holdout data is read. Not a new trial: no arm is selected here.

  .venv/bin/python forecasting/risk_experiment/diagnostics/prereg_power.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import risk_run as rr  # noqa: E402

al, rl, ra = rr.al, rr.rl, rr.ra
N_HOLD = 434 - 5                                    # holdout forecast dates with a realized 5-day window
Z = stats.norm.ppf(0.95)

# dev-best arms (pooled primary loss); fine-tuned arms are added once the Colab outputs exist
# re-selected after the plan-H universe correction (dev-best Chronos-containing arm, dev-best classical arm)
PAIRS = {"U1": ("mixeq_chr_N1ret", "fhs_loghar"), "U2": ("fac_chr", "port_loghar"),
         "U3": ("mixeq_chr_N4rv", "ewma"), "U4": ("mixeq_chr_Z3_cal", "ols_beta")}


def dev_setup():
    D = rr.load_panel(rr.DEV_PANEL, ("ret", "rv", "eligible", "bench"))
    cal = D["ret"].index
    S = pd.read_csv(rr.OUT / "stress.csv", index_col=0, parse_dates=True)["stress"].reindex(cal)
    in_dev = pd.DataFrame(np.repeat(cal.isin(rr.span(cal, rr.DEV))[:, None], D["ret"].shape[1], 1), cal, D["ret"].columns)
    return D, S, D["eligible"] & in_dev & D["ret"].shift(-1).notna(), D["eligible"] & in_dev


def u1_losses(D, S, mask1):
    arms = rr.build_u1_arms(D, S, mask1)
    y1 = D["ret"].shift(-1)
    M = mask1.copy()
    for k, v in arms.items():
        if 0.05 in v and rr.gates(k):
            V, E = v[0.05]
            M &= V.lt(0) & E.lt(V)
    return {k: rl.fz0_panel(y1, *arms[k][0.05], M, 0.05) for k in ("mixeq_chr_N1ret", "fhs_loghar", "rm", "garch_t")}


def u23_paths():
    Pc = pd.read_parquet(rr.OUT / "dev" / "cache" / "portfolio_paths.parquet")
    Pn = pd.read_parquet(rr.OUT / "dev" / "cache" / "n5_paths.parquet")
    return pd.concat([Pc.loc[Pn.index], Pn], axis=1)


def u4_losses(D, S, mask5):
    """Same construction as risk_run.evaluate_u4, for the arms needed here."""
    ret, cal, steps = D["ret"], D["ret"].index, (1, 2, 3, 4, 5)
    va = rr.build_vol_arms(D, S, mask5)
    r_f = al.futures_main_returns(al.load_long(rr.FUT_10M, tickers=["MX"], end=cal.max()), cal)["MX"]
    R5s, R5f = ra.forward_simple_return(ret, steps), ra.forward_simple_return(r_f.to_frame(), steps).iloc[:, 0]
    rho = ra.ewma_corr_with(ret, r_f)
    Hh = ra.hedge_ratios(va, rho, al.vol_ewma(r_f.to_frame(), 5).iloc[:, 0])
    Hh["ols_beta"] = al.trailing_betas(ret, r_f, 250, 120)
    U = (mask5 & R5s.notna()).mul(R5f.notna(), axis=0).astype(bool)
    for k, h in Hh.items():
        if rr.gates(k):
            U &= np.isfinite(h)
    dates = U.index[U.sum(axis=1) >= 10]
    U = U.loc[dates]
    return {k: (ra.hedged_returns(Hh[k], R5s, R5f).loc[dates] ** 2).where(U).mean(axis=1)
            for k in ("mixeq_chr_Z3_cal", "ols_beta", "ewma", "garch")}


def power(delta, se_h, true_diff=0.0):
    """P(one-sided 95% upper bound of the mean difference < delta) if the true difference is true_diff."""
    return float(stats.norm.cdf((delta - true_diff) / se_h - Z))


def comparisons(S, losses: dict, P) -> pd.DataFrame:
    """Loss difference of each arm vs a reference, in % of the reference's mean loss, with a 95% Newey-West
    interval, pooled / calm / stress. Negative = the arm is better. For U2, the FKO fee (bps/yr) vs EWMA
    with a bootstrap interval (positive = better). Saved for figures and the write-up."""
    rows = []
    for use, (L, ewma, garch) in losses.items():
        c, b = PAIRS[use]
        for arm, ref in dict.fromkeys(((c, b), (c, ewma), (c, garch), (b, ewma), (b, garch))):
            if arm == ref:
                continue
            for regime, sel in (("pooled", None), ("calm", 0), ("stress", 1)):
                d = (L[arm] - L[ref]).dropna()
                base = L[ref].reindex(d.index)
                if sel is not None:
                    keep = S.reindex(d.index).eq(sel).to_numpy()
                    d, base = d[keep], base[keep]
                nw = al.nw_tstat(d, rr.NW)
                scale = 100 / abs(base.mean())
                rows.append({"use": use, "arm": arm, "ref": ref, "regime": regime, "n": nw["n"], "t": nw["t"],
                             "diff_pct": nw["mean"] * scale, "lo_pct": (nw["mean"] - 1.96 * nw["se"]) * scale,
                             "hi_pct": (nw["mean"] + 1.96 * nw["se"]) * scale})
    c, b = PAIRS["U2"]
    for arm in (c, b):
        fb = rl.fko_fee_bootstrap(P[(arm, "vt")], P[("ewma", "vt")], 5, 252 / 5, n_boot=1000)
        k = 252 / 5 * 1e4
        rows.append({"use": "U2", "arm": arm, "ref": "ewma", "regime": "pooled", "n": fb["n"], "t": np.nan,
                     "diff_pct": np.nan, "fee_bps": fb["fee_bps_annual"], "fee_lo_bps": fb["ci_lo"] * k, "fee_hi_bps": fb["ci_hi"] * k})
    C = pd.DataFrame(rows)
    C.to_csv(rr.OUT / "dev" / "comparisons.csv", index=False)
    return C


def main():
    D, S, mask1, mask5 = dev_setup()
    rows = []
    L1 = u1_losses(D, S, mask1)
    P = u23_paths()
    L3 = {k: P[(k, "gmv")] ** 2 for k in ("mixeq_chr_N4rv", "ewma", "garch")}
    L4 = u4_losses(D, S, mask5)
    to_vol = lambda L: np.sqrt(L * 252 / 5)                               # noqa: E731  loss (mean r5²) -> annual vol
    for use, L, ref in (("U1", L1, "rm"), ("U3", L3, "ewma"), ("U4", L4, "ewma")):
        c, b = PAIRS[use]
        d = (L[c] - L[b]).dropna()                                        # > 0: Chronos worse
        nw = al.nw_tstat(d, rr.NW)
        se_h = nw["se"] * np.sqrt(nw["n"] / N_HOLD)
        gap = float(L[ref].reindex(d.index).mean() - L[b].reindex(d.index).mean())
        r = {"use": use, "chronos_arm": c, "classical_arm": b, "n_dev": nw["n"], "dev_mean_diff": nw["mean"], "dev_t": nw["t"],
             "holdout_se": se_h, "gap_ref_minus_best": gap, "ref": ref}
        margins = {"25pct_gap": 0.25 * gap, "50pct_gap": 0.5 * gap}
        if use in ("U3", "U4"):                                           # economic: +0.25 / +0.5 pp annual vol
            v = float(to_vol(L[b].reindex(d.index).mean()))
            for pp in (0.0025, 0.005):
                margins[f"{pp * 100:g}pp_vol"] = ((v + pp) ** 2 - v ** 2) * 5 / 252
        for nm, m in margins.items():
            r[f"delta_{nm}"] = m
            r[f"power0_{nm}"] = power(m, se_h)
            r[f"powerdev_{nm}"] = power(m, se_h, nw["mean"])
        rows.append(r)
    # U2: FKO fee (bps/yr) of Chronos vs best classical; > 0 favours Chronos
    c, b = PAIRS["U2"]
    fb = rl.fko_fee_bootstrap(P[(c, "vt")], P[(b, "vt")], 5, 252 / 5, n_boot=1000)
    se_dev = (fb["ci_hi"] - fb["ci_lo"]) / (2 * 1.96) * 252 / 5 * 1e4
    se_h = se_dev * np.sqrt(len(P) / N_HOLD)
    r = {"use": "U2", "chronos_arm": c, "classical_arm": b, "n_dev": len(P), "dev_mean_diff": -fb["fee_bps_annual"],
         "holdout_se": se_h}
    for bps in (50, 100, 200):
        r[f"delta_{bps}bps"] = bps
        r[f"power0_{bps}bps"] = power(bps, se_h)
        r[f"powerdev_{bps}bps"] = power(bps, se_h, -fb["fee_bps_annual"])
    rows.append(r)
    comparisons(S, {"U1": (L1, "rm", "garch_t"), "U3": (L3, "ewma", "garch"), "U4": (L4, "ewma", "garch")}, P)
    T = pd.DataFrame(rows).set_index("use")
    out = rr.OUT / "dev" / "prereg_power.csv"
    T.to_csv(out)
    pd.set_option("display.width", 250); pd.set_option("display.max_columns", 60)
    print(T.T.to_string())
    print(f"\nsaved {out}")


if __name__ == "__main__":
    main()
