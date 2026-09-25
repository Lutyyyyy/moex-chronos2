"""Figures for the PDF report (docs/report/report.tex), drawn only from result tables committed in this repo.

  .venv/bin/python docs/report/make_report_figures.py

Writes docs/report/figures/fig{1..4}_*.pdf. No market data and no forecasting/runs/ files are read.
"""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "figures"
DA = ROOT / "forecasting" / "directional_experiment" / "results"
AL = ROOT / "forecasting" / "alpha_experiment" / "results"
RK = ROOT / "forecasting" / "risk_experiment" / "results"
BREAK_EVEN_DA = 0.536                                  # DA needed to cover a 0.10% round trip at a 1.4% move
CHRONOS, CLASSIC, GREY = "#b03a2e", "#2c3e50", "#7f8c8d"

plt.rcParams.update({"font.family": "serif", "font.size": 8, "axes.titlesize": 8.5, "axes.labelsize": 8,
                     "xtick.labelsize": 7, "ytick.labelsize": 7, "legend.fontsize": 7, "axes.spines.top": False,
                     "axes.spines.right": False, "pdf.fonttype": 42})


def fig1_directional():
    """(a) mean primary-horizon DA, cross-learning vs univariate, per config pair; (b) per-cell DA."""
    pairs, cells = [], []
    for d in sorted(DA.iterdir()):
        if not d.name.startswith(("basket_gate", "sector_basket")):
            continue
        cells.append(pd.read_csv(d / "metrics.csv")["da"])
        if d.name.endswith("_univariate"):
            twin = DA / d.name.replace("_univariate", "_multivariate")
            u = json.loads((d / "summary.json").read_text())["mean_da_primary"]
            m = json.loads((twin / "summary.json").read_text())["mean_da_primary"]
            res = "10-minute" if "_10m_" in d.name else "hourly" if "_1h" in d.name else "daily"
            pairs.append((u, m, res))
    P = pd.DataFrame(pairs, columns=["uni", "xl", "res"])
    C = pd.concat(cells)
    fig, (a, b) = plt.subplots(1, 2, figsize=(6.5, 2.6))
    for res, mk in (("daily", "o"), ("hourly", "s"), ("10-minute", "^")):
        s = P[P["res"] == res]
        a.scatter(s["uni"], s["xl"], marker=mk, s=16, facecolors="none", edgecolors=CLASSIC, lw=0.8, label=f"{res} ({len(s)})")
    lo, hi = 0.45, 0.515
    a.plot([lo, hi], [lo, hi], color=GREY, lw=0.8, ls="--")
    a.set_xlim(lo, hi); a.set_ylim(lo, hi)
    a.set_xlabel("mean DA, univariate")
    a.set_ylabel("mean DA, cross-learning")
    a.set_title(f"(a) {len(P)} paired configurations")
    a.legend(frameon=False, loc="upper left")
    b.hist(C, bins=40, color=CLASSIC, alpha=0.8)
    b.axvline(0.5, color=GREY, lw=0.8, ls="--")
    b.axvline(BREAK_EVEN_DA, color=CHRONOS, lw=1)
    b.text(BREAK_EVEN_DA + 0.003, b.get_ylim()[1] * 0.9, "break-even\n0.536", color=CHRONOS, fontsize=7, va="top")
    b.set_xlabel("DA per (ticker, horizon) cell")
    b.set_ylabel("cells")
    b.set_title(f"(b) {len(C):,} cells, 64 runs")
    fig.tight_layout()
    fig.savefig(OUT / "fig1_directional.pdf", bbox_inches="tight", pad_inches=0.02)
    plt.close(fig)
    return {"pairs": len(P), "cells": len(C), "cells_above_break_even": int((C > BREAK_EVEN_DA).sum()),
            "max_abs_pair_diff": float((P["xl"] - P["uni"]).abs().max())}


def fig2_alpha():
    """(a) configuration sweep: rank-IC t vs net spanning-alpha t; (b) vol track QLIKE on log realized variance."""
    S = pd.read_csv(AL / "alpha_variants" / "configs_map.csv")
    V = pd.read_csv(AL / "alpha_improve" / "rvtarget" / "volattr_models.csv").set_index("model")["qlike_raw"]
    fig, (a, b) = plt.subplots(1, 2, figsize=(6.5, 2.7), gridspec_kw={"width_ratios": [1.1, 1]})
    a.scatter(S["MED_SIG_ic_t"], S["span_alpha_t"], s=14, color=CHRONOS)
    for name, dx, dy in (("uni", 0.1, -0.35), ("cov_fut", -0.2, 0.25), ("xl_liq", 0.25, -0.05), ("logprice", 0.15, 0.1)):
        r = S[S["variant"] == name].iloc[0]
        a.annotate(name, (r["MED_SIG_ic_t"], r["span_alpha_t"]), (r["MED_SIG_ic_t"] + dx, r["span_alpha_t"] + dy), fontsize=6.5)
    a.axhline(2, color=GREY, lw=0.8, ls="--")
    a.axvline(2, color=GREY, lw=0.8, ls="--")
    a.axhline(0, color=GREY, lw=0.5)
    a.set_xlim(0, 8); a.set_ylim(-2.5, 2.5)
    a.set_xlabel("rank IC t-statistic (ranking skill)")
    a.set_ylabel("net spanning-alpha t-statistic")
    a.set_title(f"(a) {len(S)} Chronos configurations, 2021–24")
    order = [("ewma", "EWMA"), ("garch", "GARCH(1,1)"), ("har_rv", "HAR-RV"), ("chronos_rv_uni", "Chronos, log-RV"),
             ("chronos_rv_xl", "Chronos, log-RV, cross-learning"), ("loghar", "log-HAR, per name"),
             ("loghar_pooled", "log-HAR, pooled"), ("loghar_pooled_mkt", "log-HAR, pooled + market")]
    y = range(len(order))[::-1]
    b.barh(list(y), [V[k] for k, _ in order], color=[CHRONOS if k.startswith("chronos") else CLASSIC for k, _ in order], height=0.6)
    for yi, (k, _) in zip(y, order):
        b.text(V[k] + 0.01, yi, f"{V[k]:.3f}", va="center", fontsize=6.5)
    b.set_yticks(list(y)); b.set_yticklabels([lab for _, lab in order])
    b.set_xlim(0, 1.0)
    b.set_xlabel("QLIKE vs realized variance (lower = better)")
    b.set_title("(b) volatility forecasts, 2021–24")
    fig.tight_layout()
    fig.savefig(OUT / "fig2_alpha.pdf", bbox_inches="tight", pad_inches=0.02)
    plt.close(fig)
    return {"configs": len(S), "max_span_t": float(S["span_alpha_t"].max()), "ic_t_range": (float(S["MED_SIG_ic_t"].min()), float(S["MED_SIG_ic_t"].max()))}


REF = {"fhs_loghar": "FHS log-HAR", "rm": "RiskMetrics", "garch_t": "GARCH-t", "ewma": "EWMA", "garch": "GARCH",
       "ols_beta": "rolling OLS beta"}
USE = {"U1": "VaR/ES (FZ0)", "U3": "minimum variance", "U4": "hedging"}


def fig3_holdout_effects():
    """Holdout loss difference of the frozen Chronos arm vs each classical arm, % of the reference loss, 95% CI."""
    C = pd.read_csv(RK / "holdout" / "comparisons.csv")
    C = C[(C["regime"] == "pooled") & C["use"].isin(USE)]
    fig, axes = plt.subplots(1, 3, figsize=(6.5, 1.9))
    for ax, (use, title) in zip(axes, USE.items()):
        d = C[C["use"] == use].reset_index(drop=True)
        y = list(range(len(d)))[::-1]
        for yi, (_, r) in zip(y, d.iterrows()):
            ax.errorbar(r["diff_pct"], yi, xerr=[[r["diff_pct"] - r["lo_pct"]], [r["hi_pct"] - r["diff_pct"]]],
                        fmt="o", ms=3.5, color=CHRONOS if yi == y[0] else CLASSIC, capsize=2, lw=0.9)
        ax.axvline(0, color=GREY, lw=0.8, ls="--")
        ax.set_yticks(y); ax.set_yticklabels([f"vs {REF[x]}" for x in d["ref"]])
        ax.set_ylim(-0.6, len(d) - 0.4)
        ax.set_title(title)
        ax.set_xlabel("loss difference, %")
    fig.tight_layout(w_pad=0.8)
    fig.savefig(OUT / "fig3_holdout_effects.pdf", bbox_inches="tight", pad_inches=0.02)
    plt.close(fig)
    return {"rows": len(C)}


def fig4_dev_vs_holdout():
    """t-statistics of the same comparisons, computed by the same code on dev (dry run) and on the holdout."""
    dv = json.loads((RK / "dev" / "dryrun_frozen_arms.json").read_text())
    ho = json.loads((RK / "holdout" / "results.json").read_text())
    rows = [("VaR/ES vs FHS log-HAR", "U1", "L2_vs_B"), ("VaR/ES vs FHS log-HAR, calm days (claim R)", "U1", "diff_vs_B_calm"),
            ("VaR/ES vs RiskMetrics", "U1", "L1_vs_rm"), ("VaR/ES vs GARCH-t", "U1", "L1_vs_garch_t"),
            ("min-variance vs EWMA", "U3", "L2_vs_B"), ("min-variance vs EWMA, calm days", "U3", "diff_vs_B_calm"),
            ("hedging vs rolling OLS beta", "U4", "L2_vs_B"), ("hedging vs GARCH", "U4", "L1_vs_garch")]
    T = [(lab, dv[u][k]["t"], ho[u][k]["t"]) for lab, u, k in rows]
    tw_d = pd.read_csv(RK / "dev" / "twins_report_dev.csv").set_index("arm")["dm_t"]
    tw_h = pd.read_csv(RK / "holdout" / "twins_report.csv").set_index("arm")["dm_t"]
    T += [("LoRA vs zero-shot, VaR/ES mix", tw_d["mixeq_chr_F2ret"], tw_h["mixeq_chr_F2ret"]),
          ("LoRA vs zero-shot, min-variance mix", tw_d["mixeq_chr_F2rv"], tw_h["mixeq_chr_F2rv"])]
    fig, ax = plt.subplots(figsize=(6.5, 2.9))
    y = list(range(len(T)))[::-1]
    for yi, (lab, d, h) in zip(y, T):
        ax.annotate("", (h, yi), (d, yi), arrowprops={"arrowstyle": "->", "color": GREY, "lw": 0.8})
        ax.plot(d, yi, "o", mfc="white", mec=CLASSIC, ms=5)
        ax.plot(h, yi, "o", color=CHRONOS, ms=5)
    ax.axvline(0, color=GREY, lw=0.8)
    for v in (-1.96, 1.96):
        ax.axvline(v, color=GREY, lw=0.6, ls=":")
    ax.set_yticks(y); ax.set_yticklabels([t[0] for t in T])
    ax.set_xlabel("Diebold-Mariano t (negative = Chronos, or LoRA, better)")
    ax.plot([], [], "o", mfc="white", mec=CLASSIC, label="dev 2021–24"); ax.plot([], [], "o", color=CHRONOS, label="holdout 2025–26")
    ax.legend(frameon=False, loc="upper right")
    fig.tight_layout()
    fig.savefig(OUT / "fig4_dev_vs_holdout.pdf", bbox_inches="tight", pad_inches=0.02)
    plt.close(fig)
    return {lab: (round(d, 2), round(h, 2)) for lab, d, h in T}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for f in (fig1_directional, fig2_alpha, fig3_holdout_effects, fig4_dev_vs_holdout):
        print(f.__name__, f())
    print("written:", sorted(p.name for p in OUT.glob("fig*.pdf")))


if __name__ == "__main__":
    main()
