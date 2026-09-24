"""Risk study library: pure numpy/pandas functions for Chronos-2 as a risk model (VaR/ES,
vol targeting, minimum-variance portfolios, hedging). Everything is causal by construction and
testable without Chronos. Plan: tmp/plans/risk_experiment.md (v3).

Conventions
- Returns are log returns; VaR_α and ES_α are *return levels* in the left tail (negative numbers).
- Quantile arrays Q have shape (n_rows, K) on levels u (K,), strictly increasing.
- A forecast made at date d for horizon h is "realized" at d+h: any rolling fit at date t uses only
  forecast dates s <= t-h.
"""
from __future__ import annotations

from typing import Sequence

import numpy as np
import pandas as pd
from scipy import optimize
from scipy import stats as sstats
from scipy.special import xlogy


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Quantile arithmetic: VaR / ES from a quantile grid
# ═══════════════════════════════════════════════════════════════════════════════

def quantile_at(Q: np.ndarray, u: Sequence[float], v, tail: str = "linear") -> np.ndarray:
    """Q(v) of the piecewise-linear quantile function through (u_k, Q[:, k]). `v` is a scalar or a
    per-row array. Outside [u_1, u_K]: 'linear' extends the end segment, 'flat' holds the end value."""
    Q = np.atleast_2d(np.asarray(Q, dtype=float))
    u = np.asarray(u, dtype=float)
    v = np.broadcast_to(np.asarray(v, dtype=float), (Q.shape[0],))
    j = np.clip(np.searchsorted(u, v, side="right") - 1, 0, len(u) - 2)
    rows = np.arange(Q.shape[0])
    lo, hi = Q[rows, j], Q[rows, j + 1]
    t = (v - u[j]) / (u[j + 1] - u[j])
    out = lo + t * (hi - lo)
    if tail == "flat":
        out = np.where(v < u[0], Q[:, 0], out)
        out = np.where(v > u[-1], Q[:, -1], out)
    return out


def es_from_quantiles(Q: np.ndarray, u: Sequence[float], alpha: float, tail: str = "linear") -> tuple[np.ndarray, np.ndarray]:
    """(VaR_α, ES_α) with ES_α = (1/α) ∫_0^α Q(v) dv, exact for the piecewise-linear Q.
    Below u_1 the tail is 'linear' (end-segment extension) or 'flat' (Q(v) = Q(u_1))."""
    Q = np.atleast_2d(np.asarray(Q, dtype=float))
    u = np.asarray(u, dtype=float)
    var = quantile_at(Q, u, alpha, tail)
    slope = (Q[:, 1] - Q[:, 0]) / (u[1] - u[0]) if tail == "linear" else np.zeros(Q.shape[0])
    if alpha <= u[0]:                          # whole integral inside the extrapolated tail
        return var, Q[:, 0] + slope * (alpha / 2 - u[0])
    integral = Q[:, 0] * u[0] - slope * u[0] ** 2 / 2      # ∫_0^{u_1}
    knots = [x for x in u if x < alpha] + [alpha]
    vals = [Q[:, k] for k in range(len(knots) - 1)] + [var]
    for a, b, qa, qb in zip(knots[:-1], knots[1:], vals[:-1], vals[1:]):
        integral = integral + (b - a) * (qa + qb) / 2
    return var, integral / alpha


def sample_from_quantiles(Q: np.ndarray, u: Sequence[float], rng: np.random.Generator, tail: str = "linear") -> np.ndarray:
    """One draw per row from the piecewise-linear quantile distribution (inverse-CDF sampling)."""
    v = rng.uniform(0.0, 1.0, size=np.atleast_2d(Q).shape[0])
    return quantile_at(Q, u, v, tail)


# ═══════════════════════════════════════════════════════════════════════════════
# 2. VaR / ES scoring and backtests
# ═══════════════════════════════════════════════════════════════════════════════

def fz0_loss(y, var, es, alpha: float) -> np.ndarray:
    """FZ0 joint VaR/ES loss (Patton, Ziegel & Chen 2019), left tail, ES < 0. Strictly consistent:
    minimized in expectation by the true (VaR_α, ES_α). NaN where ES >= 0 or inputs are missing."""
    y, var, es = (np.asarray(x, dtype=float) for x in (y, var, es))
    hit = (y <= var).astype(float)
    with np.errstate(divide="ignore", invalid="ignore"):
        L = -hit * (var - y) / (alpha * es) + var / es + np.log(-es) - 1.0
    return np.where(es < 0, L, np.nan)


def fz0_panel(y: pd.DataFrame, var: pd.DataFrame, es: pd.DataFrame, mask: pd.DataFrame, alpha: float) -> pd.Series:
    """Per-date cross-sectional mean FZ0 loss over masked names (time series for DM / GW tests)."""
    v, e = var.reindex_like(y), es.reindex_like(y)
    ok = mask.reindex_like(y).fillna(False).astype(bool) & y.notna() & v.notna() & e.lt(0)
    L = pd.DataFrame(fz0_loss(y.to_numpy(), v.to_numpy(), e.to_numpy(), alpha), y.index, y.columns)
    return L.where(ok).mean(axis=1).dropna()


def kupiec(hits, alpha: float) -> dict:
    """Unconditional coverage LR test (χ²₁)."""
    h = np.asarray(pd.Series(hits).dropna(), dtype=float)
    n, x = len(h), h.sum()
    p = x / n if n else np.nan
    ll0 = xlogy(n - x, 1 - alpha) + xlogy(x, alpha)
    ll1 = xlogy(n - x, 1 - p) + xlogy(x, p)
    lr = -2 * (ll0 - ll1)
    return dict(n=int(n), hits=int(x), rate=float(p), lr=float(lr), p=float(sstats.chi2.sf(lr, 1)))


def christoffersen(hits, alpha: float) -> dict:
    """Independence (χ²₁) and conditional-coverage (χ²₂) LR tests on a hit sequence (Markov chain)."""
    h = np.asarray(pd.Series(hits).dropna(), dtype=int)
    a, b = h[:-1], h[1:]
    n00, n01 = int(((a == 0) & (b == 0)).sum()), int(((a == 0) & (b == 1)).sum())
    n10, n11 = int(((a == 1) & (b == 0)).sum()), int(((a == 1) & (b == 1)).sum())
    p01 = n01 / max(n00 + n01, 1)
    p11 = n11 / max(n10 + n11, 1)
    p = (n01 + n11) / max(n00 + n01 + n10 + n11, 1)
    ll_ind = xlogy(n00, 1 - p01) + xlogy(n01, p01) + xlogy(n10, 1 - p11) + xlogy(n11, p11)
    ll_0 = xlogy(n00 + n10, 1 - p) + xlogy(n01 + n11, p)
    lr_ind = -2 * (ll_0 - ll_ind)
    lr_cc = lr_ind + kupiec(h, alpha)["lr"]
    return dict(lr_ind=float(lr_ind), p_ind=float(sstats.chi2.sf(lr_ind, 1)),
                lr_cc=float(lr_cc), p_cc=float(sstats.chi2.sf(lr_cc, 2)), p01=p01, p11=p11)


def acerbi_szekely_z2(y, var, es, alpha: float) -> float:
    """Acerbi-Szekely (2014) Z2 = Σ y·1{y<VaR} / (T·α·(−ES)) + 1. ≈0 under a correct ES forecast;
    negative = realized tail losses larger than forecast (risk underestimated)."""
    y, var, es = (np.asarray(x, dtype=float) for x in (y, var, es))
    ok = np.isfinite(y) & np.isfinite(var) & np.isfinite(es) & (es < 0)
    y, var, es = y[ok], var[ok], es[ok]
    return float(np.sum(y * (y < var) / (alpha * -es)) / len(y) + 1.0)


def acerbi_szekely_pvalue(Q: np.ndarray, u: Sequence[float], var, es, alpha: float, z2_obs: float,
                          n_sim: int = 2000, seed: int = 0, tail: str = "linear") -> float:
    """One-sided p = P(Z2* <= Z2_obs) under the forecast distributions (simulated from each row's
    piecewise-linear quantile function). Small p = ES underestimates risk."""
    rng = np.random.default_rng(seed)
    sims = np.array([acerbi_szekely_z2(sample_from_quantiles(Q, u, rng, tail), var, es, alpha) for _ in range(n_sim)])
    return float((sims <= z2_obs).mean())


def basel_traffic_light(hits: pd.Series, window: int = 250) -> pd.DataFrame:
    """Rolling 250-day exception counts of a 99% VaR and the Basel zone: green ≤4, yellow 5-9, red ≥10."""
    n = hits.astype(float).rolling(window, min_periods=window).sum()
    zone = pd.Series(np.select([n <= 4, n <= 9], ["green", "yellow"], "red"), index=n.index).where(n.notna())
    return pd.DataFrame({"exceptions": n, "zone": zone})


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Regimes and conditional tests
# ═══════════════════════════════════════════════════════════════════════════════

def market_log_rv(rv: pd.DataFrame, mask: pd.DataFrame, eps: float = 1e-10) -> pd.Series:
    """Cross-sectional mean of log realized variance over eligible names (known at close d)."""
    return np.log(rv.where(mask.reindex_like(rv).fillna(False).astype(bool)).clip(lower=eps)).mean(axis=1)


def stress_indicator(mkt: pd.Series, pct: float, window: int = 5, lookback: int = 250, min_periods: int = 120) -> pd.Series:
    """Real-time stress state S_d ∈ {0,1} (NaN in warm-up): the `window`-day mean of market log-RV
    exceeds the `pct` quantile of its own trailing `lookback`-day history up to d-1."""
    s = mkt.rolling(window, min_periods=window).mean()
    thr = s.shift(1).rolling(lookback, min_periods=min_periods).quantile(pct)
    return (s > thr).astype(float).where(thr.notna() & s.notna())


def calibrate_stress_pct(mkt: pd.Series, dates: pd.DatetimeIndex, target: float = 0.125,
                         grid: Sequence[float] = tuple(np.round(np.arange(0.60, 0.991, 0.01), 2)), **kw) -> dict:
    """Pick the percentile whose stress frequency on `dates` is closest to `target` (market data only;
    no forecast or loss enters)."""
    freq = {p: float(stress_indicator(mkt, p, **kw).reindex(dates).mean()) for p in grid}
    best = min(freq, key=lambda p: abs(freq[p] - target))
    return dict(pct=best, freq=freq[best], table=freq)


def giacomini_white(loss_a: pd.Series, loss_b: pd.Series, instruments: pd.DataFrame, lags: int) -> dict:
    """Giacomini-White (2006) conditional predictive ability test of H0: E[d_t | h_t] = 0 with
    d = L_a − L_b and instruments h (known when the forecast is made). Statistic T·Z̄'Ω⁻¹Z̄ ~ χ²_q with
    Newey-West Ω. Also returns the OLS regression of d on h (NW t) for interpretation, e.g.
    d = β0 + β1·S: β0 = advantage in calm, β0+β1 = in stress (negative = a better)."""
    df = pd.concat([(loss_a - loss_b).rename("d"), instruments], axis=1).dropna()
    H = df[instruments.columns].to_numpy(float)
    d = df["d"].to_numpy(float)
    Z = H * d[:, None]
    T, q = Z.shape
    zbar = Z.mean(axis=0)
    S = Z.T @ Z / T
    for L in range(1, min(lags, T - 1) + 1):
        G = Z[L:].T @ Z[:-L] / T
        S += (1 - L / (lags + 1)) * (G + G.T)
    stat = float(T * zbar @ np.linalg.solve(S, zbar))
    b, *_ = np.linalg.lstsq(H, d, rcond=None)
    e = d - H @ b
    g = H * e[:, None]
    Sg = g.T @ g / T
    for L in range(1, min(lags, T - 1) + 1):
        G = g[L:].T @ g[:-L] / T
        Sg += (1 - L / (lags + 1)) * (G + G.T)
    inv = np.linalg.inv(H.T @ H / T)
    se = np.sqrt(np.diag(inv @ Sg @ inv) / T)
    coefs = pd.DataFrame({"coef": b, "se": se, "t": b / se}, index=instruments.columns)
    return dict(stat=stat, df=q, p=float(sstats.chi2.sf(stat, q)), n=T, coefs=coefs)


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Calibration and FHS
# ═══════════════════════════════════════════════════════════════════════════════

def _realized_window(dates: pd.DatetimeIndex, i: int, horizon: int, window: int) -> slice:
    """Positions of forecast dates s with s <= t-h in the trailing window (t = dates[i])."""
    hi = i - horizon + 1
    return slice(max(0, hi - window), max(0, hi))


def conformal_quantile_scale(y: pd.DataFrame, q: pd.DataFrame, mask: pd.DataFrame, alpha: float, horizon: int,
                             window: int = 250, min_obs: int = 500) -> pd.Series:
    """Multiplicative conformal recalibration of a left-tail quantile forecast q < 0 (forecast date d,
    target y realized over the horizon). c_t = −Q_α(y_s/|q_s|) pooled over realized forecast dates
    s <= t−h in the trailing window; the calibrated forecast is c_t·q_t (c = 1 when q is calibrated)."""
    dates = y.index
    ok = mask.reindex_like(y).fillna(False).astype(bool) & y.notna() & q.reindex_like(y).lt(0)
    ratio = (y / q.reindex_like(y).abs()).where(ok).to_numpy()
    out = np.full(len(dates), np.nan)
    for i in range(len(dates)):
        blk = ratio[_realized_window(dates, i, horizon, window)]
        vals = blk[np.isfinite(blk)]
        if vals.size >= min_obs:
            out[i] = -np.quantile(vals, alpha)
    return pd.Series(out, index=dates)


def fhs_var_es(z: pd.DataFrame, sigma_fc: pd.DataFrame, mask: pd.DataFrame, alpha: float, horizon: int,
               window: int = 250, min_obs: int = 500) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Filtered historical simulation: VaR_t = σ_t·q̂_α(z), ES_t = σ_t·mean(z | z <= q̂_α(z)), with z the
    standardized realized returns y_s/σ_s pooled across names over realized forecast dates s <= t−h
    in the trailing window. `z` is indexed by forecast date (as y)."""
    dates = z.index
    zz = z.where(mask.reindex_like(z).fillna(False).astype(bool)).to_numpy()
    qa = np.full(len(dates), np.nan)
    ea = np.full(len(dates), np.nan)
    for i in range(len(dates)):
        blk = zz[_realized_window(dates, i, horizon, window)]
        vals = blk[np.isfinite(blk)]
        if vals.size >= min_obs:
            qa[i] = np.quantile(vals, alpha)
            ea[i] = vals[vals <= qa[i]].mean()
    s = sigma_fc.reindex_like(z)
    return s.mul(qa, axis=0), s.mul(ea, axis=0)


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Mixtures (equal-weight, rolling-fitted, regime)
# ═══════════════════════════════════════════════════════════════════════════════

def geo_mix(forecasts: Sequence[pd.DataFrame], weights: Sequence[float]) -> pd.DataFrame:
    """Weighted geometric mean of variance forecasts, exp(Σ w_k log f_k)."""
    return np.exp(sum(w * np.log(f) for w, f in zip(weights, forecasts)))


def vincentize(forecasts: Sequence[pd.DataFrame], weights: Sequence[float]) -> pd.DataFrame:
    """Weighted average of quantile (VaR/ES) forecasts at the same level (Vincentization)."""
    return sum(w * f for w, f in zip(weights, forecasts))


def _simplex(theta: np.ndarray) -> np.ndarray:
    e = np.exp(theta - theta.max())
    return e / e.sum()


def fit_vol_mix(logF: np.ndarray, y: np.ndarray, scale: bool = True) -> np.ndarray:
    """QLIKE-optimal weights (simplex) and log-scale for f = exp(c + Σ w_k log F_k). Returns
    [w_1..w_K, c]."""
    K = logF.shape[1]
    def obj(p):
        w = _simplex(p[:K]); c = p[K] if scale else 0.0
        x = y / np.exp(c + logF @ w)
        return np.mean(x - np.log(x) - 1)
    p0 = np.zeros(K + 1)
    r = optimize.minimize(obj, p0, method="Nelder-Mead", options=dict(maxiter=4000, xatol=1e-6, fatol=1e-10))
    return np.r_[_simplex(r.x[:K]), r.x[K] if scale else 0.0]


def fit_vares_mix(V: np.ndarray, E: np.ndarray, y: np.ndarray, alpha: float, scale: bool = True) -> np.ndarray:
    """FZ0-optimal weights (simplex) and scale for (VaR, ES) = s·Σ w_k (V_k, E_k). Returns [w_1..w_K, log s]."""
    K = V.shape[1]
    def obj(p):
        w = _simplex(p[:K]); s = np.exp(p[K]) if scale else 1.0
        return np.nanmean(fz0_loss(y, s * (V @ w), s * (E @ w), alpha))
    r = optimize.minimize(obj, np.zeros(K + 1), method="Nelder-Mead", options=dict(maxiter=4000, xatol=1e-6, fatol=1e-10))
    return np.r_[_simplex(r.x[:K]), r.x[K] if scale else 0.0]


def rolling_mixture(kind: str, comps: dict, y: pd.DataFrame, mask: pd.DataFrame, horizon: int, window: int = 500,
                    refit_every: int = 21, min_obs: int = 2000, state: pd.Series | None = None,
                    alpha: float | None = None) -> tuple:
    """Causal rolling mixture. kind='vol': comps = {name: variance panel}, fit QLIKE on y (realized
    variance). kind='vares': comps = {name: (VaR panel, ES panel)}, fit FZ0 on y (returns).
    Weights are refit every `refit_every` dates on realized forecast dates s <= t−h in the trailing
    window, and held until the next refit. With `state` (0/1 series), weights are fitted separately
    on each state's rows and applied by the state of the forecast date (regime mixture).
    Returns (combined forecast(s), weights DataFrame indexed by refit date [and state])."""
    names = list(comps)
    dates = y.index
    ok = mask.reindex_like(y).fillna(False).astype(bool) & y.notna()
    if kind == "vol":
        L = np.stack([np.log(comps[k].reindex_like(y).to_numpy()) for k in names], axis=-1)
        ok &= pd.DataFrame(np.isfinite(L).all(-1), y.index, y.columns) & y.gt(0)
    else:
        Vs = np.stack([comps[k][0].reindex_like(y).to_numpy() for k in names], axis=-1)
        Es = np.stack([comps[k][1].reindex_like(y).to_numpy() for k in names], axis=-1)
        ok &= pd.DataFrame(np.isfinite(Vs).all(-1) & np.isfinite(Es).all(-1) & (Es < 0).all(-1), y.index, y.columns)
    okv, yv = ok.to_numpy(), y.to_numpy()
    st = (state.reindex(dates).to_numpy() if state is not None else np.zeros(len(dates)))
    states = [0.0, 1.0] if state is not None else [0.0]
    W = {s: None for s in states}
    rows = []
    out_a = np.full(y.shape, np.nan)
    out_b = np.full(y.shape, np.nan) if kind != "vol" else None
    for i in range(len(dates)):
        if i % refit_every == 0:
            sl = _realized_window(dates, i, horizon, window)
            for s in states:
                sel = okv[sl] & (st[sl] == s)[:, None] if state is not None else okv[sl]
                if sel.sum() < min_obs:
                    continue
                if kind == "vol":
                    W[s] = fit_vol_mix(L[sl][sel], yv[sl][sel])
                else:
                    W[s] = fit_vares_mix(Vs[sl][sel], Es[sl][sel], yv[sl][sel], alpha)
                rows.append(dict(date=dates[i], state=s, **{k: W[s][j] for j, k in enumerate(names)}, scale=W[s][-1]))
        s_i = st[i] if state is not None else 0.0
        w = W.get(s_i) if np.isfinite(s_i) else None
        if w is None:
            continue
        K = len(names)
        if kind == "vol":
            out_a[i] = np.exp(w[K] + L[i] @ w[:K])
        else:
            sc = np.exp(w[K])
            out_a[i], out_b[i] = sc * (Vs[i] @ w[:K]), sc * (Es[i] @ w[:K])
    wt = pd.DataFrame(rows)
    fa = pd.DataFrame(out_a, y.index, y.columns)
    if kind == "vol":
        return fa, wt
    return (fa, pd.DataFrame(out_b, y.index, y.columns)), wt


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Portfolio uses: covariance, GMV, vol targeting, performance fee, hedging
# ═══════════════════════════════════════════════════════════════════════════════

def drd_cov(var_fc: np.ndarray, corr: np.ndarray) -> np.ndarray:
    """Σ = D·R·D with D = diag(√var_fc)."""
    d = np.sqrt(np.asarray(var_fc, dtype=float))
    return corr * np.outer(d, d)


def gmv_weights(cov: np.ndarray, long_only: bool = True) -> np.ndarray:
    """Global minimum-variance weights (sum 1); long-only via SLSQP, else closed form Σ⁻¹1/(1'Σ⁻¹1)."""
    n = cov.shape[0]
    ones = np.ones(n)
    w_cf = np.linalg.solve(cov, ones)
    w_cf /= w_cf.sum()
    if not long_only or (w_cf >= 0).all():
        return w_cf
    r = optimize.minimize(lambda w: w @ cov @ w, np.full(n, 1 / n), jac=lambda w: 2 * cov @ w, method="SLSQP",
                          bounds=[(0, 1)] * n, constraints=[{"type": "eq", "fun": lambda w: w.sum() - 1}],
                          options=dict(maxiter=500, ftol=1e-12))
    w = np.clip(r.x, 0, None)
    return w / w.sum()


def vol_target_leverage(sigma_fc: pd.Series, target: float, cap: float = 2.0) -> pd.Series:
    """Exposure to the risky portfolio: min(target/σ̂, cap) (σ̂ and target on the same horizon)."""
    return (target / sigma_fc).clip(upper=cap)


def fko_performance_fee(ra: pd.Series, rb: pd.Series, gamma: float, periods_per_year: float) -> dict:
    """Fleming-Kirby-Ostdiek (2001) fee Δ (per period) that equates the mean quadratic utility of
    strategy a (after paying Δ) and strategy b: E[U(1+r_a−Δ)] = E[U(1+r_b)], U(W) = W − γ/(2(1+γ))·W².
    Δ > 0: a mean-variance investor would pay Δ to switch from b to a. Also returns annual bps."""
    df = pd.concat([ra.rename("a"), rb.rename("b")], axis=1).dropna()
    k = gamma / (2 * (1 + gamma))
    A, B = 1 + df["a"].to_numpy(), 1 + df["b"].to_numpy()
    ub = np.mean(B - k * B ** 2)
    # -kΔ² + (2kĀ − 1)Δ + (Ā − k·mean(A²) − U_b) = 0 ; take the root closest to 0
    roots = np.roots([-k, 2 * k * A.mean() - 1, A.mean() - k * np.mean(A ** 2) - ub])
    roots = roots[np.isreal(roots)].real
    delta = float(roots[np.argmin(np.abs(roots))]) if roots.size else np.nan
    return dict(delta=delta, fee_bps_annual=delta * periods_per_year * 1e4, n=len(df))


def fko_fee_bootstrap(ra: pd.Series, rb: pd.Series, gamma: float, periods_per_year: float, n_boot: int = 2000,
                      block: int = 10, seed: int = 0) -> dict:
    """Stationary block bootstrap of the FKO fee. p_one_sided is null-centered (H0: Δ = 0), as in
    alpha_lib.sharpe_diff_bootstrap: P*(Δ* − mean Δ* >= Δ_obs) (small => a better)."""
    from arch.bootstrap import StationaryBootstrap
    df = pd.concat([ra.rename("a"), rb.rename("b")], axis=1).dropna()
    obs = fko_performance_fee(df["a"], df["b"], gamma, periods_per_year)
    bs = StationaryBootstrap(block, df.to_numpy(), seed=seed)
    fees = np.array([fko_performance_fee(pd.Series(x[0][:, 0]), pd.Series(x[0][:, 1]), gamma, periods_per_year)["delta"]
                     for x, _ in bs.bootstrap(n_boot)])
    centered = fees - fees.mean()
    return dict(**obs, ci_lo=float(np.quantile(fees, 0.025)), ci_hi=float(np.quantile(fees, 0.975)),
                p_one_sided=float((centered >= obs["delta"]).mean()))


def hedge_ratio(rho, sigma_s, sigma_f):
    """Minimum-variance hedge ratio h = ρ·σ_s/σ_f."""
    return rho * sigma_s / sigma_f


def hedge_effectiveness(unhedged, hedged) -> float:
    """1 − Var(hedged)/Var(unhedged)."""
    u = np.asarray(unhedged, dtype=float); h = np.asarray(hedged, dtype=float)
    ok = np.isfinite(u) & np.isfinite(h)
    return float(1 - np.var(h[ok]) / np.var(u[ok]))
