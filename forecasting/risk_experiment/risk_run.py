"""Risk study driver (plan: tmp/plans/risk_experiment.md, v3).

Stages, run from the repo root as  .venv/bin/python forecasting/risk_experiment/risk_run.py <stage>:
  holdout_qa   data QA of the 2025-26 holdout panel. Market data only: no forecasts, no evaluation.
  regime       fix the real-time stress rule on dev market data; write S_d for all dates.
  sources_dev  new zero-shot Chronos sources on dev anchors (holdout locked): N1 multivariate
               [return, log-RV] daily H=5; N4 the same on non-overlapping 5-day blocks, H=1.
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


if __name__ == "__main__" and len(sys.argv) > 1:
    {"holdout_qa": stage_holdout_qa, "regime": stage_regime, "sources_dev": stage_sources_dev}[sys.argv[1]]()
