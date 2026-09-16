"""End-to-end run() against a fake ISS: fetch → raw chunks → processed files, resume without requests."""
from datetime import date, timedelta

import pandas as pd

from conftest import ap, iss

CONFIG = """
```yaml
plan: paid
paths: {output_root: out, env_file: none.env}
period: {start: 2024-03-11, end: 2024-03-22}
datasets: [candles, tradestats, futoi]
candles: {intervals: [1d]}
tickers:
  shares: [SBER]
  futures: [Si]
futures: {roll_days_before_expiry: 5}
```
"""
EXPIRY = {"H": 3, "M": 6, "U": 9, "Z": 12}


def weekdays(month_first: str, month_last: str):
    days = pd.bdate_range(month_first, month_last)
    return [d.strftime("%Y-%m-%d") for d in days]


def router(path, params):
    if path.startswith("securities/"):
        secid = path.split("/")[1]
        if secid[2] not in EXPIRY:
            return {}
        year = 2020 + int(secid[3])
        return {**iss("description", ["name", "value"], [["LSTTRADE", f"{year}-{EXPIRY[secid[2]]:02d}-21"], ["FRSTTRADE", f"{year - 1}-01-01"]]),
                **iss("boards", ["boardid"], [["RFUD"]])}
    if path.endswith("/candles"):
        if params["start"] > 0:
            return iss("candles", [], [])
        base = 100 if "SBER" in path else (1000 if "SiH4" in path else 2000)
        rows = [[base, base, base, base, 1, 1, f"{d} 00:00:00", f"{d} 23:59:59"] for d in weekdays(params["from"], params["till"])]
        return iss("candles", ["open", "close", "high", "low", "value", "volume", "begin", "end"], rows)
    if "/tradestats/" in path:
        rows = [[d, "10:05:00", "SBER", 1.0, "x"] for d in weekdays(params["from"], params["till"])]
        return iss("data", ["tradedate", "tradetime", "secid", "pr_close", "SYSTIME"], rows, (0, len(rows), 1000))
    if path.startswith("analyticalproducts/futoi"):
        d = params["from"]
        cols = ["tradedate", "tradetime", "clgroup", *ap.FUTOI_VALUES]
        return iss("futoi", cols, [[d, "10:00:00", g, 1, 1, 1, 1, 1] for g in ("FIZ", "YUR")])
    raise AssertionError(f"unexpected path {path}")


def test_run_end_to_end_and_resume(tmp_path, make_client):
    (tmp_path / "config.md").write_text(CONFIG)
    cfg = ap.load_config(tmp_path / "config.md")
    client, session = make_client(router)

    summary = ap.run(cfg, client=client)
    assert set(zip(summary.dataset, summary.group)) == {
        ("candles", "shares"), ("candles", "futures"), ("tradestats", "shares"), ("tradestats", "futures"), ("futoi", "futures")}

    fut = pd.read_parquet(cfg.output_root / "processed" / "candles_1d" / "futures.parquet")
    assert fut["timestamp"].dt.date.min() == date(2024, 3, 11) and fut["timestamp"].dt.date.max() == date(2024, 3, 22)
    assert fut.groupby("contract")["timestamp"].max()["SiH4"].date() == date(2024, 3, 15)   # window ends 03-16 (Sat)
    assert fut.loc[fut["roll"], "timestamp"].dt.date.tolist() == [date(2024, 3, 18)]
    assert set(fut.loc[fut.contract == "SiM4", "close"]) == {2000}

    ts = pd.read_parquet(cfg.output_root / "processed" / "tradestats" / "shares.parquet")
    assert ts["timestamp"].iloc[0] == pd.Timestamp("2024-03-11 10:00", tz=ap.TZ)

    oi = pd.read_parquet(cfg.output_root / "processed" / "futoi" / "futures.parquet")
    assert len(oi) == 12 and {"pos_fiz", "pos_yur"} <= set(oi.columns)   # 12 calendar days, one snapshot each

    session.calls.clear()
    ap.run(cfg, client=client)
    assert session.calls == []                                           # everything cached (past months, past years)


def test_subscription_error_skips_dataset(tmp_path, make_client):
    from conftest import FakeResponse
    (tmp_path / "config.md").write_text(CONFIG.replace("futures: [Si]", "futures: []").replace("[candles, tradestats, futoi]", "[tradestats]"))
    cfg = ap.load_config(tmp_path / "config.md")
    client, session = make_client(lambda p, q: FakeResponse(ctype="text/html", body=b"available only to subscribers"))
    summary = ap.run(cfg, client=client)
    assert summary.empty and len(session.calls) == 1
