"""Figures for the risk-study write-up, regenerated from the committed comparison tables.

  .venv/bin/python forecasting/risk_experiment/make_figures.py [dev|holdout]

Reads forecasting/risk_experiment/results/<period>/comparisons.csv; writes docs/figures/risk_<period>_*.png.
"""
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
USES = {"U1": "1-day VaR/ES (FZ0 loss)", "U3": "Min-variance portfolio (realized variance)", "U4": "Hedging with MX (hedged variance)"}
LABEL = {"rm": "RiskMetrics", "garch_t": "GARCH-t", "garch": "GARCH", "ewma": "EWMA", "ols_beta": "rolling OLS beta",
         "fhs_loghar_cal": "FHS log-HAR (cal.)", "mixeq_chr_N1ret": "Chronos + FHS log-HAR mix",
         "fac_chr_cal": "Chronos one-factor (cal.)", "fac_loghar_cal": "log-HAR one-factor (cal.)",
         "mixeq_chr_N4rv_cal": "Chronos + log-HAR mix (cal.)", "fac_chr": "Chronos one-factor", "fac_ewma_cal": "EWMA one-factor (cal.)"}


def nice(arm: str, chronos: set | None = None) -> str:
    return LABEL.get(arm, arm)


def forest(C: pd.DataFrame, period: str, out: Path):
    """Loss difference (% of the reference's loss, 95% Newey-West CI) per use, pooled."""
    P = C[(C["regime"] == "pooled") & C["use"].isin(USES)]
    fig, axes = plt.subplots(1, 3, figsize=(13, 3.6), sharey=False)
    for ax, (use, title) in zip(axes, USES.items()):
        d = P[P["use"] == use].reset_index(drop=True)
        chronos = {d["arm"].iloc[0]}
        y = range(len(d))[::-1]
        colors = ["#c0392b" if a in chronos else "#2c3e50" for a in d["arm"]]
        for yi, (_, r), col in zip(y, d.iterrows(), colors):
            ax.errorbar(r["diff_pct"], yi, xerr=[[r["diff_pct"] - r["lo_pct"]], [r["hi_pct"] - r["diff_pct"]]],
                        fmt="o", color=col, capsize=3)
        ax.axvline(0, color="grey", lw=1, ls="--")
        ax.set_yticks(list(y))
        ax.set_yticklabels([f"{nice(a, chronos)}\nvs {nice(r, chronos)}" for a, r in zip(d["arm"], d["ref"])], fontsize=7)
        ax.set_title(title, fontsize=9)
        ax.set_xlabel("loss difference, % (left = first arm better)", fontsize=8)
    fig.suptitle(f"Chronos vs classical risk models, MOEX {period} (95% CI)", fontsize=10)
    fig.tight_layout()
    fig.savefig(out / f"risk_{period}_forest.png", dpi=150)
    plt.close(fig)


def regimes(C: pd.DataFrame, period: str, out: Path):
    """Best Chronos arm vs best classical arm, pooled / calm / stress."""
    first = C[C["use"].isin(USES)].groupby("use").head(1)[["use", "arm", "ref"]]
    fig, ax = plt.subplots(figsize=(7.5, 3.8))
    offs = {"pooled": -0.2, "calm": 0.0, "stress": 0.2}
    cols = {"pooled": "#2c3e50", "calm": "#27ae60", "stress": "#c0392b"}
    for i, (_, r) in enumerate(first.iterrows()):
        for reg, o in offs.items():
            x = C[(C["use"] == r["use"]) & (C["arm"] == r["arm"]) & (C["ref"] == r["ref"]) & (C["regime"] == reg)].iloc[0]
            ax.errorbar(i + o, x["diff_pct"], yerr=[[x["diff_pct"] - x["lo_pct"]], [x["hi_pct"] - x["diff_pct"]]],
                        fmt="o", color=cols[reg], capsize=3, label=reg if i == 0 else None)
    ax.axhline(0, color="grey", lw=1, ls="--")
    ax.set_xticks(range(len(first)))
    ax.set_xticklabels([f"{u}\n{nice(a)}\nvs {nice(b)}" for u, a, b in first.itertuples(index=False)], fontsize=7)
    ax.set_ylabel("loss difference, % (below 0 = Chronos better)", fontsize=8)
    ax.set_title(f"Best Chronos vs best classical by regime, MOEX {period}", fontsize=10)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(out / f"risk_{period}_regimes.png", dpi=150)
    plt.close(fig)


def main(period: str = "dev"):
    C = pd.read_csv(HERE / "results" / period / "comparisons.csv")
    out = ROOT / "docs" / "figures"
    out.mkdir(parents=True, exist_ok=True)
    forest(C, period, out)
    regimes(C, period, out)
    print("written:", sorted(p.name for p in out.glob(f"risk_{period}_*.png")))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "dev")
