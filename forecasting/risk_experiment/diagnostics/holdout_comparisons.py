"""Holdout comparison table for the figures, derived from the committed results.json only (nothing recomputed).

  .venv/bin/python forecasting/risk_experiment/diagnostics/holdout_comparisons.py

Within a use, every arm's per-date loss series lives on the same dates, so mean(L_a − L_b) = mean_a − mean_b,
and the Newey-West standard error is that difference over the DM t. C vs B by regime comes from the stored
calm/stress mean and standard error. Percentages are relative to the reference arm's pooled mean loss (the dev
table used regime-specific means; the holdout results do not store them). Writes results/holdout/comparisons.csv.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "colab"))
from holdout_run import FROZEN  # noqa: E402


def main():
    R = json.loads((HERE / "results" / "holdout" / "results.json").read_text())
    rows = []
    for use in ("U1", "U3", "U4"):
        r, f = R[use], FROZEN[use]
        c, b, refs = f["C"], f["B"], f["refs"]
        m = r["mean_loss"]
        pairs = [(b, r["L2_vs_B"]["t"])] + [(x, r[f"L1_vs_{x}"]["t"]) for x in refs if x != b]
        for ref, t in pairs:
            diff = m[c] - m[ref]
            se = abs(diff / t) if t else np.nan
            scale = 100 / abs(m[ref])
            rows.append({"use": use, "arm": c, "ref": ref, "regime": "pooled", "n": r["n_dates"], "t": t,
                         "diff_pct": diff * scale, "lo_pct": (diff - 1.96 * se) * scale, "hi_pct": (diff + 1.96 * se) * scale})
        for reg in ("calm", "stress"):
            d = r[f"diff_vs_B_{reg}"]
            scale = 100 / abs(m[b])
            rows.append({"use": use, "arm": c, "ref": b, "regime": reg, "n": d["n"], "t": d["t"],
                         "diff_pct": d["mean"] * scale, "lo_pct": (d["mean"] - 1.96 * d["se"]) * scale,
                         "hi_pct": (d["mean"] + 1.96 * d["se"]) * scale})
    for ref in ("ewma", "garch", FROZEN["U2"]["B"]):
        x = R["U2"][f"fee_vs_{ref}"]
        rows.append({"use": "U2", "arm": FROZEN["U2"]["C"], "ref": ref, "regime": "pooled", "n": R["U2"]["n_dates"],
                     "fee_bps": x["bps"], "fee_p": x["p"]})
    C = pd.DataFrame(rows)
    out = HERE / "results" / "holdout" / "comparisons.csv"
    C.to_csv(out, index=False)
    print(C.round(3).to_string())
    print(f"saved {out}")


if __name__ == "__main__":
    main()
