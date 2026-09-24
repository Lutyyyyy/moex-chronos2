"""Forecast arms for the risk study (plan v3, R4): turns Chronos sources and classical models into
1-day VaR/ES panels (U1) and 5-day variance panels (U2-U4), plus the portfolio constructions.
All panels are indexed by forecast date d (information up to the close of d).
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Sequence

import numpy as np
import pandas as pd
from scipy import stats as sstats

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parents[0] / "alpha_experiment"))
import alpha_lib as al  # noqa: E402
import risk_lib as rl  # noqa: E402

U = np.asarray(al.NATIVE_QUANTILES)
QCOLS = [f"q{q:g}" for q in al.NATIVE_QUANTILES]
RV_EPS = 1e-7


# ═══════════════════════════════════════════════════════════════════════════════
# Chronos sources → panels
# ═══════════════════════════════════════════════════════════════════════════════

def _select(preds: pd.DataFrame, h, variate: str | None) -> pd.DataFrame:
    p = preds
    if variate is not None and "variate" in p.columns:
        p = p[p["variate"] == variate]
    hs = [h] if np.isscalar(h) else list(h)
    return p[p["h"].isin(hs)]


def chronos_vares(preds: pd.DataFrame, alphas: Sequence[float], cal: pd.DatetimeIndex, cols, variate: str | None = None,
                  h: int = 1) -> dict:
    """{alpha: (VaR panel, ES panel)} from the step-h return quantiles (rows sorted: monotone rearrangement)."""
    p = _select(preds, h, variate)
    Q = np.sort(p[QCOLS].to_numpy(dtype=float), axis=1)
    idx = pd.MultiIndex.from_arrays([pd.DatetimeIndex(p["anchor"]), p["ticker"]])
    out = {}
    for a in alphas:
        v, e = rl.es_from_quantiles(Q, U, a, tail="linear")
        out[a] = tuple(pd.Series(x, index=idx).unstack().reindex(index=cal, columns=cols) for x in (v, e))
    return out


def chronos_rv(preds: pd.DataFrame, steps: Sequence[int], cal: pd.DatetimeIndex, cols, variate: str | None = None) -> pd.DataFrame:
    """Σ_{h in steps} E[RV_{d+h}] from log-RV quantiles (E[exp] per step, minus the floor)."""
    p = _select(preds, steps, variate)
    Q = np.sort(p[QCOLS].to_numpy(dtype=float), axis=1)
    e = np.maximum(al.mean_exp_quantiles(Q) - RV_EPS, 1e-10)
    s = pd.Series(e, index=pd.MultiIndex.from_arrays([pd.DatetimeIndex(p["anchor"]), p["ticker"]]))
    return s.groupby(level=[0, 1]).sum().unstack().reindex(index=cal, columns=cols)


def chronos_return_var(preds: pd.DataFrame, steps: Sequence[int], cal: pd.DatetimeIndex, cols, variate: str | None = None) -> pd.DataFrame:
    """Σ_{h in steps} Var_h from the return quantile function (exact piecewise-linear moments)."""
    p = _select(preds, steps, variate)
    Q = np.sort(p[QCOLS].to_numpy(dtype=float), axis=1)
    _, var = al.quantile_moments(Q, al.NATIVE_QUANTILES)
    s = pd.Series(var, index=pd.MultiIndex.from_arrays([pd.DatetimeIndex(p["anchor"]), p["ticker"]]))
    return s.groupby(level=[0, 1]).sum().unstack().reindex(index=cal, columns=cols)


# ═══════════════════════════════════════════════════════════════════════════════
# Classical VaR/ES models (1-day)
# ═══════════════════════════════════════════════════════════════════════════════

def normal_var_es(sigma: pd.DataFrame, alpha: float, mu=0.0) -> tuple:
    z = sstats.norm.ppf(alpha)
    return mu + sigma * z, mu - sigma * sstats.norm.pdf(z) / alpha


def t_var_es(sigma: pd.DataFrame, nu: pd.DataFrame, alpha: float, mu=0.0) -> tuple:
    """Unit-variance Student-t scaled by σ: VaR = μ + σ·q_ν(α)·√((ν−2)/ν), ES from the t tail formula."""
    nu = nu.clip(lower=2.05)
    q = pd.DataFrame(sstats.t.ppf(alpha, nu), nu.index, nu.columns)
    s = np.sqrt((nu - 2) / nu)
    es_std = -(pd.DataFrame(sstats.t.pdf(q, nu), nu.index, nu.columns) / alpha) * (nu + q ** 2) / (nu - 1)
    return mu + sigma * q * s, mu + sigma * es_std * s


def hs_var_es(ret: pd.DataFrame, alpha: float, window: int = 250, min_obs: int = 200) -> tuple:
    """Historical simulation per name on the last `window` returns up to d (for r_{d+1})."""
    v = ret.rolling(window, min_periods=min_obs).quantile(alpha)
    def tail_mean(x):
        x = x[np.isfinite(x)]
        q = np.quantile(x, alpha)
        return x[x <= q].mean()
    e = ret.rolling(window, min_periods=min_obs).apply(tail_mean, raw=True)
    return v, e


def garch_t_1step(ret: pd.DataFrame, refit_every: int = 21, min_obs: int = 250, max_obs: int = 1000) -> tuple:
    """GARCH(1,1) with Student-t innovations, constant mean, refit every `refit_every` rows on data <= d
    (last `max_obs` obs), σ² updated causally between refits. Returns (σ² for r_{d+1}, ν, μ) panels in
    log-return units."""
    from arch import arch_model
    s2o = pd.DataFrame(np.nan, index=ret.index, columns=ret.columns)
    nuo, muo = s2o.copy(), s2o.copy()
    for t in ret.columns:
        x = (ret[t] * 100).to_numpy()
        obs = np.cumsum(np.isfinite(x))
        params, s2_next = None, None
        j = ret.columns.get_loc(t)
        for i in range(len(x)):
            if not np.isfinite(x[i]) or obs[i] < min_obs:
                continue
            if params is None or i % refit_every == 0:
                hist = x[:i + 1][np.isfinite(x[:i + 1])][-max_obs:]
                try:
                    r = arch_model(hist, mean="Constant", vol="GARCH", p=1, q=1, dist="t", rescale=False).fit(disp="off", show_warning=False)
                    params = (r.params["mu"], r.params["omega"], r.params["alpha[1]"], r.params["beta[1]"], r.params["nu"])
                except Exception:                                       # noqa: BLE001
                    if params is None:
                        continue
                mu, om, a1, b1, nu = params
                path = al._garch_filter(hist, mu, om, a1, b1, float(np.var(hist)))
                s2_next = om + a1 * (hist[-1] - mu) ** 2 + b1 * path[-1]
            else:
                mu, om, a1, b1, nu = params
                s2_next = om + a1 * (x[i] - mu) ** 2 + b1 * s2_next
            s2o.iat[i, j] = s2_next / 1e4
            nuo.iat[i, j] = nu
            muo.iat[i, j] = mu / 100
    return s2o, nuo, muo


# ═══════════════════════════════════════════════════════════════════════════════
# Portfolio constructions (U2 vol targeting, U3 GMV)
# ═══════════════════════════════════════════════════════════════════════════════

def forward_simple_return(ret: pd.DataFrame, steps: Sequence[int]) -> pd.DataFrame:
    """Simple return over d+min(steps)..d+max(steps) (NaN if any day is missing)."""
    s = sum(ret.shift(-h) for h in steps)
    return np.expm1(s)


def portfolio_paths(var_arms: dict, corr: dict, R5: pd.DataFrame, rf5: pd.Series, universe: pd.DataFrame,
                    dates: pd.DatetimeIndex, target5: float, cap: float = 2.0, gmv_share: dict | None = None) -> dict:
    """For every date and arm: GMV (long-only) 5-day return and vol-targeted equal-weight 5-day return, using
    Σ = D·R·D with D from the arm's 5-day variance forecasts and R the shared EWMA correlation.
    `universe` (bool panel) must already require every arm's forecast and R5 to be finite, so all arms
    use the same names on each date. `gmv_share` = {arm: other_arm}: GMV weights are invariant to a
    date-common scale, so e.g. a calibrated arm reuses its raw arm's GMV path instead of re-solving."""
    gmv_share = gmv_share or {}
    out = {k: {"gmv": [], "vt": [], "vt_exposure": []} for k in var_arms}
    kept = []
    for d in dates:
        names = universe.columns[universe.loc[d].to_numpy(dtype=bool)]
        if len(names) < 10 or d not in corr:
            continue
        C = corr[d].loc[names, names].to_numpy()
        r5 = R5.loc[d, names].to_numpy()
        kept.append(d)
        w_ew = np.full(len(names), 1 / len(names))
        for k, V in var_arms.items():
            cov = rl.drd_cov(V.loc[d, names].to_numpy(), C)
            if k not in gmv_share:
                out[k]["gmv"].append(float(rl.gmv_weights(cov) @ r5))
            sp = float(np.sqrt(w_ew @ cov @ w_ew))
            e = min(target5 / sp, cap)
            out[k]["vt"].append(float(e * (w_ew @ r5) + (1 - e) * rf5.loc[d]))
            out[k]["vt_exposure"].append(e)
    if not kept:
        raise ValueError("portfolio_paths: no usable dates (check the universe and the correlation dict keys)")
    for k, src in gmv_share.items():
        out[k]["gmv"] = out[src]["gmv"]
    idx = pd.DatetimeIndex(kept)
    return {k: {m: pd.Series(v, index=idx) for m, v in d_.items()} for k, d_ in out.items()}


def factor_cov(beta: np.ndarray, s2m: float, s2e: np.ndarray) -> np.ndarray:
    """One-factor covariance Σ = β β' σ²_m + diag(σ²_ε) (plan F5b)."""
    beta = np.asarray(beta, dtype=float)
    return np.outer(beta, beta) * s2m + np.diag(np.asarray(s2e, dtype=float))


def n5_portfolio_paths(fac_arms: dict, port_arms: dict, beta: pd.DataFrame, R5: pd.DataFrame, rf5: pd.Series,
                       universe: pd.DataFrame, dates: pd.DatetimeIndex, target5: float, cap: float = 2.0) -> dict:
    """N5 arms on given dates/names (the U2/U3 universe, so results compare with the D·R·D arms):
    fac_arms  {arm: (σ²_m Series, σ²_ε DataFrame)} -> GMV on the one-factor Σ and vol targeting of the
              equal-weight book with σ²_p = w'Σw;
    port_arms {arm: σ²_p Series} -> vol targeting with the direct portfolio-variance forecast.
    A date is kept only if every arm is finite for every name in the universe that day.
    No GMV sharing between raw and `_cal` arms here (unlike portfolio_paths): the calibration scales the
    market and residual components by two different factors, so Σ_cal is not a multiple of Σ_raw."""
    out = {**{k: {"gmv": [], "vt": [], "vt_exposure": []} for k in fac_arms},
           **{k: {"vt": [], "vt_exposure": []} for k in port_arms}}
    kept = []
    for d in dates:
        names = universe.columns[universe.loc[d].to_numpy(dtype=bool)]
        b = beta.loc[d, names].to_numpy()
        covs = {k: factor_cov(b, m.loc[d], e.loc[d, names].to_numpy()) for k, (m, e) in fac_arms.items()}
        sp2 = {k: float(v.loc[d]) for k, v in port_arms.items()}
        if len(names) < 10 or not all(np.isfinite(c).all() for c in covs.values()) or not all(np.isfinite(v) and v > 0 for v in sp2.values()):
            continue
        kept.append(d)
        r5 = R5.loc[d, names].to_numpy()
        w_ew = np.full(len(names), 1 / len(names))
        ew5 = float(w_ew @ r5)

        def vt(k, var_p):
            e = min(target5 / np.sqrt(var_p), cap)
            out[k]["vt"].append(float(e * ew5 + (1 - e) * rf5.loc[d])); out[k]["vt_exposure"].append(e)
        for k, cov in covs.items():
            out[k]["gmv"].append(float(rl.gmv_weights(cov) @ r5))
            vt(k, float(w_ew @ cov @ w_ew))
        for k, v in sp2.items():
            vt(k, v)
    if not kept:
        raise ValueError("n5_portfolio_paths: no usable dates")
    idx = pd.DatetimeIndex(kept)
    return {k: {m: pd.Series(v, index=idx) for m, v in d_.items()} for k, d_ in out.items()}


# ═══════════════════════════════════════════════════════════════════════════════
# Hedging (U4): single stocks hedged with the index future
# ═══════════════════════════════════════════════════════════════════════════════

def ewma_corr_with(ret: pd.DataFrame, x: pd.Series, lam: float = 0.97, min_obs: int = 60) -> pd.DataFrame:
    """Per-column EWMA correlation of `ret` with the series `x` using data <= d, with the same update as
    alpha_lib.ewma_corr (zero mean; a missing value enters as 0; NaN until both have `min_obs` obs)."""
    x = x.reindex(ret.index)
    R, X = ret.fillna(0.0), x.fillna(0.0)

    def ew(df):                                                        # S_0 = 0, S_i = λS_{i-1} + (1−λ)z_i
        z = pd.concat([df.iloc[:1] * 0, df])
        return z.ewm(alpha=1 - lam, adjust=False).mean().iloc[1:]
    cov = ew(R.mul(X, axis=0))
    vs, vx = ew(R ** 2), ew(X.to_frame() ** 2).iloc[:, 0]
    rho = cov / np.sqrt(vs.mul(vx, axis=0).clip(lower=1e-16))
    ok = ret.notna().cumsum().ge(min_obs) & pd.DataFrame({c: x.notna().cumsum().ge(min_obs) for c in ret.columns})
    return rho.where(ok)


def hedge_ratios(var_arms: dict, rho: pd.DataFrame, var_f: pd.Series) -> dict:
    """h = ρ̂·σ̂_s/σ̂_f per arm, with a shared correlation and futures variance (plan F1), so arms differ
    only in the stock-variance forecast. `var_arms` and `var_f` are variances over the same horizon."""
    return {k: rl.hedge_ratio(rho, np.sqrt(V), np.sqrt(var_f.reindex(V.index)).to_numpy()[:, None]) for k, V in var_arms.items()}


def hedged_returns(h: pd.DataFrame, R_s: pd.DataFrame, R_f: pd.Series) -> pd.DataFrame:
    """Hedged simple return r_s − h·r_f (a short of h futures per unit of stock)."""
    return R_s - h.mul(R_f.reindex(R_s.index), axis=0)
