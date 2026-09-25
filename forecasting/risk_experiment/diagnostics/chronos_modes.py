"""Chronos-2 input modes head to head on dev (2021-24): univariate vs cross-learning vs multivariate [return, log-RV],
return vs log-RV target, calibrated vs raw. Descriptive, computed after the holdout was opened (FINDINGS section 4).

Not a new trial: every arm compared here is already in the ledger, built from the cached dev forecasts; nothing is
selected and no ledger row is written (RISK_NO_LEDGER). The U1 scoring reuses evaluate_u1 with all arms, so the
FZ0 domain is the committed table's (checked: the means reproduce results/dev/U1_table.csv).

  .venv/bin/python forecasting/risk_experiment/diagnostics/chronos_modes.py

Sources: Z1 returns, univariate; Z2 returns, cross-learning; Z3 log-RV, cross-learning; N1 [return, log-RV] daily,
cross-learning; N4 the same on 5-day blocks. Writes results/dev/chronos_modes.csv (t = DM t of a minus b, Newey-West
lag 8; negative favours a).
"""
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

os.environ["RISK_NO_LEDGER"] = "1"
HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import risk_run as rr  # noqa: E402

al, ra = rr.al, rr.ra

U1_PAIRS = [("chr_N1ret", "chr_Z1"), ("chr_Z2", "chr_Z1"), ("chr_N1ret", "chr_Z2"),
            ("chrfhs_N1rv", "chrfhs_Z3"), ("chrfhs_Z3", "chr_Z1"), ("chrfhs_Z3", "chr_N1ret"),
            ("mixeq_chr_N1ret", "mixeq_chr_Z1"), ("mixeq_chr_Z2", "mixeq_chr_Z1"),
            ("mixeq_chr_N1ret", "mixeq_chrfhs_Z3"), ("mixeq_chrfhs_N1rv", "mixeq_chrfhs_Z3")]
VOL_PAIRS = [("chr_N1rv", "chr_Z3"), ("chr_N4rv", "chr_Z3"), ("chr_Z2ret", "chr_Z3"), ("chr_N4rv", "chr_N1rv"),
             ("mixeq_chr_N1rv", "mixeq_chr_Z3"), ("mixeq_chr_N4rv", "mixeq_chr_Z3")]
U4_PAIRS = [("chr_N1rv", "chr_Z3"), ("chr_N4rv", "chr_Z3"), ("chr_Z2ret", "chr_Z3"),
            ("mixeq_chr_N1rv", "mixeq_chr_Z3"), ("chr_Z3_cal", "chr_Z3"), ("mixeq_chr_Z3_cal", "mixeq_chr_Z3")]


def main():
    D = rr.load_panel(rr.DEV_PANEL, ("ret", "rv", "eligible", "bench"))
    cal = D["ret"].index
    S = pd.read_csv(rr.OUT / "stress.csv", index_col=0, parse_dates=True)["stress"].reindex(cal)
    in_dev = pd.DataFrame(np.repeat(cal.isin(rr.span(cal, rr.DEV))[:, None], D["ret"].shape[1], 1), cal, D["ret"].columns)
    mask1 = D["eligible"] & in_dev & D["ret"].shift(-1).notna()
    mask5 = D["eligible"] & in_dev
    rows = []

    def pair(use, metric, a, b, La, Lb):
        rows.append({"use": use, "metric": metric, "a": a, "b": b, "mean_a": La.mean(), "mean_b": Lb.mean(),
                     "t_a_minus_b": al.dm_test(La, Lb, rr.NW)["t"], "n_dates": len(La)})

    L1 = {}
    rr.evaluate_u1(rr.build_u1_arms(D, S, mask1), D, S, mask1, ledger=False, losses_out=L1)
    L1 = {k: v for (k, a), v in L1.items() if a == 0.05}
    ref = pd.read_csv(HERE / "results" / "dev" / "U1_table.csv", index_col=[0, 1])["fz0"].xs(0.05, level=1)
    gap = max(abs(L1[k].mean() - ref.loc[k]) for x in U1_PAIRS for k in x)
    if gap > 1e-9:
        raise SystemExit(f"U1 losses do not reproduce results/dev/U1_table.csv (max gap {gap})")
    for a, b in U1_PAIRS:
        pair("U1", "fz0", a, b, L1[a], L1[b])

    va = rr.build_vol_arms(D, S, mask5)
    steps = (1, 2, 3, 4, 5)
    rv5 = sum(D["rv"].shift(-h) for h in steps)
    U = mask5 & ra.forward_simple_return(D["ret"], steps).notna()        # the U2/U3 universe of evaluate_vol
    for k, v in va.items():
        if rr.gates(k):
            U &= v.gt(0)
    P = pd.read_parquet(rr.OUT / "dev" / "cache" / "portfolio_paths.parquet")
    dates = P.index
    for a, b in VOL_PAIRS:
        pair("U3", "qlike_rv5", a, b, al.vol_loss_panel(rv5, va[a], U).loc[dates], al.vol_loss_panel(rv5, va[b], U).loc[dates])
        pair("U3", "gmv_var", a, b, P[(a, "gmv")] ** 2, P[(b, "gmv")] ** 2)

    L4 = {}
    rr.evaluate_u4(va, D, S, mask5, losses_out=L4)
    for a, b in U4_PAIRS:
        pair("U4", "hedged_mse", a, b, L4[a], L4[b])

    out = pd.DataFrame(rows)
    f = HERE / "results" / "dev" / "chronos_modes.csv"
    out.to_csv(f, index=False)
    pd.set_option("display.width", 200)
    print(out.round(5).to_string())
    print(f"saved {f}")


if __name__ == "__main__":
    main()
