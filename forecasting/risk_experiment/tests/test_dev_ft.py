"""Plan I: splicing of the fine-tuned sources and the checks on the Colab records (no Chronos, no data)."""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import risk_run as rr  # noqa: E402

Q = [f"q{u:g}" for u in (0.1, 0.5, 0.9)]


def _preds(anchors, tickers, variates=None, h=(1, 2), offset=0.0):
    rows = []
    for a in anchors:
        for t in tickers:
            for v in (variates or [None]):
                for s in h:
                    r = {"anchor": a, "ticker": t, "h": s, **{q: offset + i for i, q in enumerate(Q)}}
                    if v is not None:
                        r["variate"] = v
                    rows.append(r)
    df = pd.DataFrame(rows)
    df["anchor"] = pd.to_datetime(df["anchor"])
    if variates:
        df = df[["anchor", "ticker", "variate", "h", *Q]]
    return df


@pytest.fixture
def setup(tmp_path, monkeypatch):
    anchors = pd.bdate_range("2021-12-28", "2024-12-31")
    twin = _preds(anchors, ["AAA", "BBB"])                               # Z3-like: no variate column
    f = tmp_path / "z3.parquet"
    twin.to_parquet(f)
    monkeypatch.setitem(rr.SRC, "Z3", f)
    ft = tmp_path / "ft"
    for y in rr.F_YEARS:
        d = ft / "F1" / str(y)
        d.mkdir(parents=True)
        _preds(anchors[anchors.year == y], ["AAA", "BBB"], ["logrv"], offset=100.0).to_parquet(d / "preds.parquet")
        runs = [{"lr": lr, "best_eval_loss": l, "best_step": 100, "eval_log": [[100, l + 0.01], [200, l]], "fit_seconds": 1.0}
                for lr, l in ((1e-5, 2.73), (3e-5, 2.72), (1e-4, 2.71))]
        (d / "record.json").write_text(json.dumps({"target": "F1", "year": y, "cutoff": f"{y - 1}-12-31", "n_train_series": 5,
                                                   "n_val_series": 9, "n_pred_rows": 1, "adapter_saved": True,
                                                   "chosen_lr": 1e-4, "runs": runs}))
    return ft, anchors


def test_splice_uses_twin_before_2022_and_ft_after(setup):
    ft, anchors = setup
    P = rr.load_f_source("F1", ft)
    assert list(P.columns[:4]) == ["anchor", "ticker", "variate", "h"] and (P["variate"] == "logrv").all()
    before, after = P[P["anchor"] < rr.F_START], P[P["anchor"] >= rr.F_START]
    assert (before["q0.1"] == 0.0).all() and len(before) == 4 * 2 * 2      # 4 anchors in late 2021 x 2 names x 2 steps
    assert (after["q0.1"] == 100.0).all() and len(after) == (anchors >= rr.F_START).sum() * 4
    assert not P.duplicated(["anchor", "ticker", "variate", "h"]).any()


def test_splice_refuses_missing_rows(setup):
    ft, _ = setup
    f = ft / "F1" / "2023" / "preds.parquet"
    p = pd.read_parquet(f)
    p.iloc[1:].to_parquet(f)
    with pytest.raises(ValueError, match="missing 1"):
        rr.load_f_source("F1", ft)


def test_records_checks(setup):
    ft, _ = setup
    rec = rr.ft_records(ft, ("F1",))
    assert list(rec["year"]) == list(rr.F_YEARS) and (rec["chosen_lr"] == 1e-4).all()
    assert np.allclose(rec["first_eval_lr0.0001"], 2.72)
    f = ft / "F1" / "2024" / "record.json"
    r = json.loads(f.read_text())
    r["chosen_lr"] = 1e-5
    f.write_text(json.dumps(r))
    with pytest.raises(ValueError, match="not the validation argmin"):
        rr.ft_records(ft, ("F1",))
    (ft / "F1" / "2022" / "record.json").unlink()
    with pytest.raises(FileNotFoundError):
        rr.ft_records(ft, ("F1",))


def test_twin_names():
    assert rr.f_twin_name("mixeq_chr_F1_cal") == "mixeq_chr_Z3_cal"
    assert rr.f_twin_name("mixeq_chr_F2ret") == "mixeq_chr_N1ret"
    assert rr.f_twin_name("chrfhs_F2rv_cal") == "chrfhs_N1rv_cal"


def test_holdout_coverage_check(monkeypatch):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "colab"))
    import holdout_run as hr
    monkeypatch.setattr(rr, "HOLDOUT", ("2025-01-01", "2025-01-10"))
    cal = pd.bdate_range("2024-12-20", "2025-01-10")
    elig = pd.DataFrame(True, index=cal, columns=["AAA", "BBB"])
    elig.loc["2025-01-06", "BBB"] = False
    anchors = [a for a in cal if a >= pd.Timestamp("2025-01-01")]
    ft = _preds(anchors, ["AAA", "BBB"], ["ret", "logrv"], h=(1, 2, 3, 4, 5))
    ft = ft[~((ft["anchor"] == "2025-01-06") & (ft["ticker"] == "BBB"))]
    hr.check_f_holdout("F2", ft, elig)                                   # exact coverage passes
    with pytest.raises(ValueError, match="missing 1"):
        hr.check_f_holdout("F2", ft.iloc[1:], elig)
    with pytest.raises(ValueError, match="duplicated 1"):
        hr.check_f_holdout("F2", pd.concat([ft, ft.iloc[:1]]), elig)
