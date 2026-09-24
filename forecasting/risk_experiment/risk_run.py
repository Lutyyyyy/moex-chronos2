"""Risk study driver (plan: tmp/plans/risk_experiment.md, v3).

Stages, run from the repo root as  .venv/bin/python forecasting/risk_experiment/risk_run.py <stage>:
  holdout_qa   data QA of the 2025-26 holdout panel. Market data only: no forecasts, no evaluation.
  regime       fix the real-time stress rule on dev market data; write S_d for all dates.
  sources_dev  new zero-shot Chronos sources on dev anchors (holdout locked): N1 multivariate
               [return, log-RV] daily H=5; N4 the same on non-overlapping 5-day blocks, H=1.
  dev          R4 dev evaluation (2021-2024) of every arm for U1 (1-day VaR/ES), U2 (vol targeting)
               and U3 (minimum-variance portfolio): pooled, calm and stress; ledger rows.
               Fine-tuned (F1/F2) and U4 (hedging) arms are added when their inputs exist.
Later stages (bundle_dev, dev, select, holdout_sources, bundle_holdout, holdout) are added
in R2-R7.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "forecasting" / "alpha_experiment"))
import alpha_lib as al  # noqa: E402
import chronos_sources as cs  # noqa: E402
import risk_arms as ra  # noqa: E402
import risk_lib as rl  # noqa: E402

RUNS = ROOT / "forecasting" / "runs"
DEV_PANEL = RUNS / "alpha_data"                 # 2020-01-03 .. 2024-12-30
FULL_PANEL = RUNS / "alpha_data_holdout"        # same construction, 2020-01-03 .. 2026-09-17
OUT = RUNS / "risk"
DEV = ("2021-01-01", "2024-12-31")
HOLDOUT = ("2025-01-01", "2026-09-17")
INDEX_10M = ROOT / "data_pipeline" / "data" / "processed" / "candles_10m" / "indices.parquet"

# Regime rule (fixed in R1 from dev market data only; see stage_regime)
STRESS_TARGET_FREQ = 0.125     # target share of dev days in stress
STRESS_WINDOW, STRESS_LOOKBACK, STRESS_MIN_PERIODS = 5, 250, 120
MIN_HOLDOUT_STRESS_DAYS = 40   # below this, stress-regime claims are "inconclusive"


def load_panel(path: Path, names=("ret", "rv", "eligible", "close", "value", "stale", "bench")) -> dict:
    D = {n: pd.read_parquet(path / f"{n}.parquet") for n in names}
    if "eligible" in D:
        D["eligible"] = D["eligible"].astype(bool)
    return D


def span(idx: pd.DatetimeIndex, period) -> pd.DatetimeIndex:
    return idx[(idx >= period[0]) & (idx <= period[1])]


# ═══════════════════════════════════════════════════════════════════════════════
# Stage holdout_qa
# ═══════════════════════════════════════════════════════════════════════════════

def stage_holdout_qa(top_n: int = 8) -> dict:
    """Holdout panel QA: overlap identity with the dev panel, calendar, universe size and the largest
    moves with context (persistence, traded value, raw vs main close). No forecasts are touched."""
    A, H = load_panel(DEV_PANEL, ("ret", "rv", "eligible")), load_panel(FULL_PANEL, ("ret", "rv", "eligible", "close", "value"))
    ca, ch = A["ret"].index, H["ret"].index
    ov = ca[ca <= DEV[1]]
    cols = A["ret"].columns.intersection(H["ret"].columns)
    qa = {"dev_calendar": [str(ca.min().date()), str(ca.max().date()), len(ca)],
          "full_calendar": [str(ch.min().date()), str(ch.max().date()), len(ch)],
          "overlap_missing_dates": len(ov.difference(ch)), "overlap_extra_dates": len(ch[ch <= DEV[1]].difference(ca))}
    for n in ("ret", "rv"):
        x = A[n].reindex(index=ov, columns=cols); y = H[n].reindex_like(x)
        qa[f"overlap_{n}_max_abs_diff"] = float(np.nanmax((x - y).abs().to_numpy()))
        qa[f"overlap_{n}_nan_mismatch"] = int((x.isna() != y.isna()).sum().sum())
    e = A["eligible"].reindex(index=ov, columns=cols); f = H["eligible"].reindex_like(e).fillna(False)
    qa["overlap_eligible_mismatch"] = int((e != f).sum().sum())
    qa["new_names_in_full_panel"] = sorted(set(H["ret"].columns) - set(A["ret"].columns))
    hd = span(ch, HOLDOUT)
    qa["holdout_days"] = len(hd)
    qa["holdout_weekend_days"] = [str(d.date()) for d in hd[hd.dayofweek >= 5]]
    n_el = H["eligible"].reindex(hd).sum(axis=1)
    qa["holdout_eligible_per_day"] = {"min": int(n_el.min()), "median": float(n_el.median()), "max": int(n_el.max())}
    # largest holdout moves, with a data-error screen: a bad print reverts, a real move persists
    d1 = pd.read_parquet(ROOT / "data_pipeline/data/processed/candles_1d/shares.parquet", columns=["ticker", "timestamp", "close"])
    d1["d"] = pd.to_datetime(d1["timestamp"]).dt.tz_localize(None).dt.normalize()
    raw = d1.pivot_table(index="d", columns="ticker", values="close", aggfunc="last")
    r = H["ret"].reindex(hd)
    top = r.stack().abs().sort_values(ascending=False).head(top_n)
    moves = []
    for (d, t), _ in top.items():
        i = ch.get_loc(d)
        c = H["close"][t]
        pre, post5 = c.iloc[i - 1], c.iloc[min(i + 5, len(ch) - 1)]
        persist = float(np.log(post5 / pre) / r.loc[d, t])              # ≈1: move kept; ≈0: reverted
        vmed = H["value"][t].iloc[max(0, i - 20):i].median()
        moves.append({"date": str(d.date()), "ticker": t, "log_ret": round(float(r.loc[d, t]), 3),
                      "persistence_5d": round(persist, 2), "value_vs_20d_median": round(float(H["value"].loc[d, t] / vmed), 1),
                      "raw_1d_close_vs_main_close": round(float(raw.loc[d, t] / c.loc[d] - 1), 3) if d in raw.index else None})
    qa["largest_holdout_moves"] = moves
    qa["largest_moves_flagged"] = [m for m in moves if abs(m["persistence_5d"]) < 0.3 or m["value_vs_20d_median"] < 1.5]
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "holdout_qa.json").write_text(json.dumps(qa, indent=1))
    print(json.dumps(qa, indent=1))
    return qa


# ═══════════════════════════════════════════════════════════════════════════════
# Stage regime
# ═══════════════════════════════════════════════════════════════════════════════

def imoex_log_rv(calendar: pd.DatetimeIndex) -> pd.Series:
    """log realized variance of IMOEX (main-session 10m bars, close-to-close incl. overnight), from
    2020, so the stress rule is defined on all of dev (the cross-sectional stock mean needs eligible
    names and starts only in mid-2021)."""
    bars = al.load_long(INDEX_10M, tickers=["IMOEX"], end=calendar.max())
    return np.log(al.realized_variance(bars, calendar, col="close")["IMOEX"].clip(lower=1e-10))


def stage_regime() -> dict:
    """Fix the stress percentile on DEV market data only (target STRESS_TARGET_FREQ), then write S_d for
    the full calendar. The holdout stress-day count is market data only and is disclosed in the
    pre-registration; no forecast or loss enters."""
    H = load_panel(FULL_PANEL, ("ret",))
    cal = H["ret"].index
    m = imoex_log_rv(cal)
    dev, hold = span(cal, DEV), span(cal, HOLDOUT)
    kw = dict(window=STRESS_WINDOW, lookback=STRESS_LOOKBACK, min_periods=STRESS_MIN_PERIODS)
    c = rl.calibrate_stress_pct(m, dev, target=STRESS_TARGET_FREQ, **kw)
    S = rl.stress_indicator(m, c["pct"], **kw)
    rule = {"measure": "IMOEX log realized variance (main-session 10m + overnight)",
            "window": STRESS_WINDOW, "lookback": STRESS_LOOKBACK, "min_periods": STRESS_MIN_PERIODS,
            "pct": c["pct"], "target_freq": STRESS_TARGET_FREQ, "dev_freq": round(c["freq"], 4),
            "first_valid": str(S.first_valid_index().date()),
            "dev_stress_days_by_year": {int(k): int(v) for k, v in S.reindex(dev).groupby(dev.year).sum().items()},
            "feb_apr_2022_share_stress": round(float(S.loc["2022-02-01":"2022-04-30"].mean()), 3),
            "holdout_stress_days": int(S.reindex(hold).sum()), "holdout_days": len(hold),
            "holdout_stress_days_by_year": {int(k): int(v) for k, v in S.reindex(hold).groupby(hold.year).sum().items()},
            "min_holdout_stress_days": MIN_HOLDOUT_STRESS_DAYS}
    rule["stress_claims_possible"] = rule["holdout_stress_days"] >= MIN_HOLDOUT_STRESS_DAYS
    OUT.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"imoex_log_rv": m, "stress": S}).to_csv(OUT / "stress.csv", index_label="date")
    (OUT / "regime_rule.json").write_text(json.dumps(rule, indent=1))
    print(json.dumps(rule, indent=1))
    return rule


# ═══════════════════════════════════════════════════════════════════════════════
# Stage sources_dev (R2)
# ═══════════════════════════════════════════════════════════════════════════════

FIRST_ANCHOR = "2021-01-01"                      # same anchors as the alpha experiment's dev forecasts
SOURCES = {   # name: (block days, stride, context length in rows, horizon)
    "N1": (1, 1, 250, 5),                        # daily [return, log-RV], steps d+1..d+5
    "N4": (5, 5, 100, 1),                        # 5-day blocks (100 blocks = 500 days), next block d+1..d+5
}


def source_path(name: str, period: str = "dev") -> Path:
    return OUT / "sources" / period / name / "preds.parquet"


def stage_sources_dev(threads: int = 4) -> dict:
    import torch
    torch.set_num_threads(threads)
    sys.path.insert(0, str(ROOT / "forecasting" / "alpha_experiment"))
    import alpha_run as R                          # pipeline loader (same model and settings)
    D = load_panel(DEV_PANEL, ("ret", "rv", "eligible"))
    cal = D["ret"].index
    anchors = cal[cal >= pd.Timestamp(FIRST_ANCHOR)]
    pipe, checks = None, {}
    for name, (block, stride, ctx, H) in SOURCES.items():
        f = source_path(name)
        if not f.exists():
            pipe = pipe or R.load_pipeline()
            P = cs.rv_panels(D["ret"], D["rv"], block=block)
            cs.generate_multivariate(pipe, P, D["eligible"], anchors, ctx=ctx, H=H, stride=stride,
                                     cross_learning=True, out_path=f)
            print(f"[{name}] done", flush=True)
        p = pd.read_parquet(f)
        qcols = [c for c in p.columns if c.startswith("q")]
        cross = int((np.diff(p[qcols].to_numpy(), axis=1) < 0).any(axis=1).sum())
        exp = int(D["eligible"].reindex(anchors).sum().sum())
        got = p[["anchor", "ticker"]].drop_duplicates().shape[0]
        checks[name] = {"rows": len(p), "anchors": int(p["anchor"].nunique()), "anchor_ticker_pairs": got,
                        "eligible_pairs": exp, "rows_with_crossing_quantiles": cross,
                        "max_anchor": str(pd.Timestamp(p["anchor"].max()).date())}
    (OUT / "sources" / "dev" / "checks.json").write_text(json.dumps(checks, indent=1))
    print(json.dumps(checks, indent=1))
    return checks

# ═══════════════════════════════════════════════════════════════════════════════
# Stage dev (R4)
# ═══════════════════════════════════════════════════════════════════════════════

NW = 8
LEDGER = HERE / "trial_ledger.csv"
SRC = {"Z1": RUNS / "alpha_forecast_dev_test" / "preds.parquet",        # returns, univariate
       "Z2": RUNS / "alpha_variants" / "xl" / "preds.parquet",           # returns, cross-learning
       "Z3": RUNS / "alpha_variants" / "rv_xl" / "preds.parquet",        # log-RV, cross-learning
       "N1": RUNS / "risk" / "sources" / "dev" / "N1" / "preds.parquet", # [ret, log-RV], cross-learning
       "N4": RUNS / "risk" / "sources" / "dev" / "N4" / "preds.parquet"} # 5-day [ret, log-RV], cross-learning
MIX_PARTNER_U1, MIX_PARTNER_VOL = "fhs_loghar", "loghar_pooled_mkt"     # best classical models known before R4
CLASSICAL_U1 = ["rm", "garch_t", "hs", "fhs_garch", "fhs_loghar"]
CLASSICAL_VOL = ["ewma", "garch", "har_rv", "loghar", "loghar_pooled", "loghar_pooled_mkt"]
VT_TARGET_ANNUAL = 0.10


def _cached(name: str, builder):
    f = OUT / "dev" / "cache" / f"{name}.parquet"
    if f.exists():
        return pd.read_parquet(f)
    df = builder()
    f.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(f)
    return df


def _pairs_to_frame(d: dict) -> pd.DataFrame:
    """{arm: {alpha: (V, E)}} -> one MultiIndex-column frame (arm, alpha, 'V'/'E', ticker)."""
    parts = {(k, str(a), w): x for k, v in d.items() for a, (V, E) in v.items() for w, x in (("V", V), ("E", E))}
    return pd.concat(parts, axis=1)


def _frame_to_pairs(f: pd.DataFrame) -> dict:
    out = {}
    for k in f.columns.levels[0]:
        sub = f[k]
        out[k] = {float(a): (sub[a]["V"], sub[a]["E"]) for a in sub.columns.levels[0] if a in sub.columns.get_level_values(0)}
    return out


def build_u1_arms(D, S, mask1) -> dict:
    ret, rv = D["ret"], D["rv"]
    cal, cols = ret.index, ret.columns
    y1 = ret.shift(-1)
    A = (0.05, 0.01)

    def raw():
        arms = {}
        for nm, var in (("chr_Z1", None), ("chr_Z2", None), ("chr_N1ret", "ret")):
            src = {"chr_Z1": "Z1", "chr_Z2": "Z2", "chr_N1ret": "N1"}[nm]
            arms[nm] = ra.chronos_vares(pd.read_parquet(SRC[src]), A, cal, cols, variate=var, h=1)
        for nm, src, var in (("chrfhs_Z3", "Z3", None), ("chrfhs_N1rv", "N1", "logrv")):
            s = np.sqrt(ra.chronos_rv(pd.read_parquet(SRC[src]), (1,), cal, cols, variate=var))
            arms[nm] = {a: rl.fhs_var_es(y1 / s, s, mask1, a, horizon=1) for a in A}
        s_rm = np.sqrt(al.vol_ewma(ret, 1))
        arms["rm"] = {a: ra.normal_var_es(s_rm, a) for a in A}
        s2, nu, mu = ra.garch_t_1step(ret)
        s_g = np.sqrt(s2)
        arms["garch_t"] = {a: ra.t_var_es(s_g, nu, a, mu) for a in A}
        arms["fhs_garch"] = {a: rl.fhs_var_es(y1 / s_g, s_g, mask1, a, horizon=1) for a in A}
        arms["hs"] = {a: ra.hs_var_es(ret, a) for a in A}
        s_lh = np.sqrt(al.vol_har_log(rv, (1,), mask=D["eligible"], pooled=True, market=True))
        arms["fhs_loghar"] = {a: rl.fhs_var_es(y1 / s_lh, s_lh, mask1, a, horizon=1) for a in A}
        return _pairs_to_frame(arms)

    arms = _frame_to_pairs(_cached("u1_raw", raw))

    def calibrated():
        out = {}
        for k in list(arms):
            out[k + "_cal"] = {}
            for a, (V, E) in arms[k].items():
                c = rl.conformal_quantile_scale(y1, V, mask1, a, horizon=1)
                out[k + "_cal"][a] = (V.mul(c, axis=0), E.mul(c, axis=0))
        return _pairs_to_frame(out)

    arms.update(_frame_to_pairs(_cached("u1_cal", calibrated)))

    def mixtures():
        out = {}
        pV, pE = arms[MIX_PARTNER_U1][0.05]
        for k in [x for x in list(arms) if x.startswith("chr") and not x.endswith("_cal")]:
            V, E = arms[k][0.05]
            out[f"mixeq_{k}"] = {0.05: (rl.vincentize([V, pV], [0.5, 0.5]), rl.vincentize([E, pE], [0.5, 0.5]))}
            (fv, fe), _ = rl.rolling_mixture("vares", {k: (V, E), "p": (pV, pE)}, y1, mask1, horizon=1, alpha=0.05)
            out[f"mixfit_{k}"] = {0.05: (fv, fe)}
            (rv_, re_), _ = rl.rolling_mixture("vares", {k: (V, E), "p": (pV, pE)}, y1, mask1, horizon=1, alpha=0.05, state=S)
            out[f"mixreg_{k}"] = {0.05: (rv_, re_)}
            print(f"  mixture {k} done", flush=True)
        return _pairs_to_frame(out)

    arms.update(_frame_to_pairs(_cached("u1_mix", mixtures)))
    return arms


def build_vol_arms(D, S, mask5) -> dict:
    ret, rv = D["ret"], D["rv"]
    cal, cols = ret.index, ret.columns
    steps = (1, 2, 3, 4, 5)
    rv5 = sum(rv.shift(-h) for h in steps)
    r5sq = sum(ret.shift(-h) for h in steps) ** 2

    def raw():
        V = {"chr_Z2ret": ra.chronos_return_var(pd.read_parquet(SRC["Z2"]), steps, cal, cols),
             "chr_Z3": ra.chronos_rv(pd.read_parquet(SRC["Z3"]), steps, cal, cols),
             "chr_N1rv": ra.chronos_rv(pd.read_parquet(SRC["N1"]), steps, cal, cols, variate="logrv"),
             "chr_N4rv": ra.chronos_rv(pd.read_parquet(SRC["N4"]), (1,), cal, cols, variate="logrv")}
        C = pd.read_parquet(RUNS / "alpha_dev" / "vol_fc_lag0.parquet")
        V.update({"ewma": C["ewma"], "garch": C["garch"], "har_rv": C["har_rv_ceiling"]})
        Hh = pd.read_parquet(RUNS / "alpha_improve" / "rvtarget" / "loghar_cache.parquet")
        V.update({k: Hh[k] for k in ("loghar", "loghar_pooled", "loghar_pooled_mkt")})
        return pd.concat({k: v.reindex(index=cal, columns=cols) for k, v in V.items()}, axis=1)

    f = _cached("vol_raw", raw)
    arms = {k: f[k] for k in f.columns.levels[0]}

    def mixtures():
        out = {}
        P = arms[MIX_PARTNER_VOL]
        for k in ("chr_Z3", "chr_N1rv", "chr_N4rv"):
            out[f"mixeq_{k}"] = rl.geo_mix([arms[k], P], [0.5, 0.5])
            out[f"mixfit_{k}"], _ = rl.rolling_mixture("vol", {k: arms[k], "p": P}, rv5, mask5, horizon=5)
            out[f"mixreg_{k}"], _ = rl.rolling_mixture("vol", {k: arms[k], "p": P}, rv5, mask5, horizon=5, state=S)
            print(f"  vol mixture {k} done", flush=True)
        return pd.concat(out, axis=1)

    fm = _cached("vol_mix", mixtures)
    arms.update({k: fm[k] for k in fm.columns.levels[0]})
    # calibration to the 5-day RETURN variance (what U2/U3 consume), same method for every arm
    for k in list(arms):
        arms[k + "_cal"] = arms[k].mul(al.rolling_vol_scale(arms[k], r5sq, mask5, horizon=5), axis=0)
    return arms


def _ledger(use: str, arm: str, metric: str, value: float, n: int):
    al.append_trial(LEDGER, use=use, tag="R4_dev", period="dev_2021_2024", arm=arm, metric=metric,
                    value=float(value), n=int(n))


def evaluate_u1(arms: dict, D, S, mask1) -> pd.DataFrame:
    y1 = D["ret"].shift(-1)
    rows = {}
    for alpha in (0.05, 0.01):
        names = [k for k, v in arms.items() if alpha in v]
        M = mask1.copy()
        for k in names:
            V, E = arms[k][alpha]
            M &= V.notna() & E.lt(0)
        Ls = {k: rl.fz0_panel(y1, *arms[k][alpha], M, alpha) for k in names}
        dates = Ls[names[0]].index
        s = S.reindex(dates)
        classical = [k for k in names if k.split("_cal")[0] in CLASSICAL_U1]
        best_cl = min(classical, key=lambda k: Ls[k].mean())
        for k in names:
            V, E = arms[k][alpha]
            hits = (y1 < V).where(M)
            h_pool = hits.stack().dropna()
            r = {"alpha": alpha, "fz0": Ls[k].mean(), "fz0_calm": Ls[k][s == 0].mean(), "fz0_stress": Ls[k][s == 1].mean(),
                 "hit_rate": float(h_pool.mean()), "kupiec_p": rl.kupiec(h_pool.to_numpy(), alpha)["p"],
                 "christoffersen_reject_share": float(np.mean([rl.christoffersen(hits[t].dropna().to_numpy(), alpha)["p_ind"] < 0.05
                                                               for t in hits.columns if hits[t].notna().sum() > 250])),
                 "z2": rl.acerbi_szekely_z2(y1.where(M).to_numpy().ravel(), V.where(M).to_numpy().ravel(), E.where(M).to_numpy().ravel(), alpha),
                 "n_dates": len(dates), "n_obs": int(M.sum().sum()), "best_classical": best_cl}
            for ref in ("rm", "garch_t", best_cl):
                if k != ref:
                    r[f"dm_t_vs_{'best_classical' if ref == best_cl else ref}"] = al.dm_test(Ls[k], Ls[ref], NW)["t"]
            if k != best_cl:
                g = rl.giacomini_white(Ls[k], Ls[best_cl], pd.DataFrame({"const": 1.0, "stress": s.fillna(0)}), NW)
                r.update(gw_p=g["p"], gw_calm_coef_t=g["coefs"].loc["const", "t"],
                         gw_stress_coef=g["coefs"].loc["stress", "coef"], gw_stress_t=g["coefs"].loc["stress", "t"])
            if alpha == 0.01:
                bt = [rl.basel_traffic_light(hits[t].dropna())["zone"].dropna() for t in hits.columns if hits[t].notna().sum() > 250]
                z = pd.concat(bt)
                r.update(basel_red_share=float((z == "red").mean()), basel_yellow_share=float((z == "yellow").mean()))
            rows[(k, alpha)] = r
            _ledger("U1", k, f"fz0_a{alpha}", r["fz0"], r["n_obs"])
    return pd.DataFrame(rows).T


def evaluate_vol(arms: dict, D, S, mask5) -> tuple:
    ret = D["ret"]
    steps = (1, 2, 3, 4, 5)
    rv5 = sum(D["rv"].shift(-h) for h in steps)
    R5 = ra.forward_simple_return(ret, steps)
    rf = D["bench"]["rf"].reindex(ret.index)
    rf5 = np.expm1(sum(np.log1p(rf.shift(-h)) for h in steps))
    U = mask5 & R5.notna()
    for v in arms.values():
        U &= v.gt(0)
    dates = U.index[U.sum(axis=1) >= 10]
    ec = al.ewma_corr(ret)                                              # {"cols": Index, "C": {date: ndarray}}
    corr = {d: pd.DataFrame(C, index=ec["cols"], columns=ec["cols"]) for d, C in ec["C"].items() if d in set(dates)}
    target5 = VT_TARGET_ANNUAL * np.sqrt(5 / 252)
    # GMV is invariant to a date-common scale, so calibrated arms share their raw arm's GMV
    raw_names = [k for k in arms if not k.endswith("_cal")]
    paths = ra.portfolio_paths(arms, corr, R5, rf5, U, dates, target5,
                               gmv_share={k: k[:-4] for k in arms if k.endswith("_cal")})
    s = S.reindex(paths[raw_names[0]]["gmv"].index)
    classical = [k for k in arms if k.split("_cal")[0] in CLASSICAL_VOL]
    gmv_loss = {k: paths[k]["gmv"] ** 2 for k in arms}
    best_gmv = min(classical, key=lambda k: gmv_loss[k].mean())
    fees_vs_ewma = {k: rl.fko_performance_fee(paths[k]["vt"], paths["ewma"]["vt"], 5, 252 / 5)["fee_bps_annual"] for k in arms}
    best_vt = max(classical, key=lambda k: fees_vs_ewma[k] if k != "ewma" else -np.inf)
    rows = {}
    for k in arms:
        L = gmv_loss[k]
        vt = paths[k]["vt"]
        ql = al.vol_loss_panel(rv5, arms[k], U)
        r = {"qlike_rv5": ql.mean(),
             "gmv_ann_vol": float(np.sqrt(L.mean() * 252 / 5)), "gmv_ann_vol_calm": float(np.sqrt(L[s == 0].mean() * 252 / 5)),
             "gmv_ann_vol_stress": float(np.sqrt(L[s == 1].mean() * 252 / 5)),
             "vt_ann_vol": float(np.sqrt((vt ** 2).mean() * 252 / 5)), "vt_mean_exposure": float(paths[k]["vt_exposure"].mean()),
             "vt_fee_bps_vs_ewma": fees_vs_ewma[k], "n_dates": len(L), "best_classical_gmv": best_gmv, "best_classical_vt": best_vt}
        for ref, lab in (("ewma", "ewma"), ("garch", "garch"), (best_gmv, "best_classical")):
            if k != ref:
                r[f"gmv_dm_t_vs_{lab}"] = al.dm_test(L, gmv_loss[ref], NW)["t"]
        for ref, lab in (("garch", "garch"), (best_vt, "best_classical")):
            if k != ref:
                fb = rl.fko_fee_bootstrap(vt, paths[ref]["vt"], 5, 252 / 5, n_boot=500)
                r[f"vt_fee_bps_vs_{lab}"], r[f"vt_fee_p_vs_{lab}"] = fb["fee_bps_annual"], fb["p_one_sided"]
        if k != "ewma":
            r["vt_fee_p_vs_ewma"] = rl.fko_fee_bootstrap(vt, paths["ewma"]["vt"], 5, 252 / 5, n_boot=500)["p_one_sided"]
        if k != best_gmv:
            g = rl.giacomini_white(L, gmv_loss[best_gmv], pd.DataFrame({"const": 1.0, "stress": s.fillna(0)}), NW)
            r.update(gmv_gw_p=g["p"], gmv_gw_stress_t=g["coefs"].loc["stress", "t"])
        rows[k] = r
        _ledger("U3", k, "gmv_realized_var", L.mean(), len(L))
        _ledger("U2", k, "vt_fee_bps_vs_ewma", fees_vs_ewma[k], len(vt))
    return pd.DataFrame(rows).T, paths


def stage_dev() -> dict:
    D = load_panel(DEV_PANEL, ("ret", "rv", "eligible", "bench"))
    cal = D["ret"].index
    S = pd.read_csv(OUT / "stress.csv", index_col=0, parse_dates=True)["stress"].reindex(cal)
    dev = span(cal, DEV)
    in_dev = pd.DataFrame(np.repeat(cal.isin(dev)[:, None], D["ret"].shape[1], 1), cal, D["ret"].columns)
    mask1 = D["eligible"] & in_dev & D["ret"].shift(-1).notna()
    mask5 = D["eligible"] & in_dev
    print("building U1 arms", flush=True)
    u1 = build_u1_arms(D, S, mask1)
    print("building vol arms", flush=True)
    va = build_vol_arms(D, S, mask5)
    (OUT / "dev").mkdir(parents=True, exist_ok=True)
    print("evaluating U1", flush=True)
    t1 = evaluate_u1(u1, D, S, mask1)
    t1.to_csv(OUT / "dev" / "U1_table.csv")
    print("evaluating U2/U3", flush=True)
    t23, paths = evaluate_vol(va, D, S, mask5)
    t23.to_csv(OUT / "dev" / "U23_table.csv")
    pd.concat({k: pd.DataFrame(v) for k, v in paths.items()}, axis=1).to_parquet(OUT / "dev" / "portfolio_paths.parquet")
    pd.set_option("display.width", 250); pd.set_option("display.max_columns", 40)
    c1 = ["fz0", "fz0_calm", "fz0_stress", "hit_rate", "kupiec_p", "z2", "dm_t_vs_rm", "dm_t_vs_garch_t", "dm_t_vs_best_classical", "gw_p", "gw_stress_t"]
    print(t1[t1["alpha"] == 0.05][[c for c in c1 if c in t1.columns]].astype(float).sort_values("fz0").round(4).to_string())
    c2 = ["qlike_rv5", "gmv_ann_vol", "gmv_ann_vol_calm", "gmv_ann_vol_stress", "gmv_dm_t_vs_ewma", "gmv_dm_t_vs_best_classical",
          "vt_ann_vol", "vt_fee_bps_vs_ewma", "vt_fee_bps_vs_best_classical", "vt_fee_p_vs_best_classical"]
    print(t23[[c for c in c2 if c in t23.columns]].astype(float).sort_values("gmv_ann_vol").round(4).to_string())
    return {"U1": t1, "U23": t23}


if __name__ == "__main__" and len(sys.argv) > 1:
    {"holdout_qa": stage_holdout_qa, "regime": stage_regime, "sources_dev": stage_sources_dev,
     "dev": stage_dev}[sys.argv[1]]()
