from datetime import date

import pandas as pd

from conftest import ap

CFG_TEXT = """
```yaml
period: {start: 2024-03-01, end: 2024-03-31}
tickers: {shares: [SBER]}
```
"""


def cfg():
    return ap.parse_config(CFG_TEXT, ap.Path("/cfg"))


def ts(s):
    return pd.Timestamp(s, tz=ap.TZ)


def test_normalize_candles_tz_and_columns():
    rows = [{"open": 1, "close": 2, "high": 3, "low": 0.5, "value": 10.0, "volume": 5,
             "begin": "2024-03-01 10:00:00", "end": "2024-03-01 10:59:59"}]
    df = ap.normalize_candles(rows)
    assert list(df.columns) == ["timestamp", "open", "high", "low", "close", "volume", "value"]
    assert str(df["timestamp"].dt.tz) == ap.TZ and df["timestamp"].iloc[0] == ts("2024-03-01 10:00")


def test_datashop_bar_timestamp_is_bar_start():
    rows = [{"tradedate": "2024-03-01", "tradetime": "10:05:00", "secid": "SBER", "pr_close": 1.0, "SYSTIME": "x"}]
    df = ap.normalize_datashop(rows, "tradestats")
    assert df["timestamp"].iloc[0] == ts("2024-03-01 10:00") and "systime" not in df


def test_hi2_timestamp_not_shifted():
    rows = [{"tradedate": "2024-03-01", "tradetime": "18:40:00", "secid": "SBER", "metric": "hhi_volume", "value": 5}]
    assert ap.normalize_datashop(rows, "hi2")["timestamp"].iloc[0] == ts("2024-03-01 18:40")


def test_finalize_filters_period_dedupes_and_orders():
    df = pd.DataFrame({"ticker": ["SBER"] * 4,
                       "timestamp": [ts("2024-03-02 10:00"), ts("2024-02-29 10:00"), ts("2024-03-01 10:00"), ts("2024-03-01 10:00")],
                       "secid": "SBER", "close": [3, 0, 1, 2]})
    out = ap.finalize(df, "candles", cfg(), {})
    assert list(out.columns) == ["ticker", "timestamp", "close"]
    assert out["close"].tolist() == [2, 3]


def test_finalize_futoi_pivot():
    base = {"ticker": "Si", "timestamp": ts("2024-03-01 10:00"), "pos_long": 1, "pos_short": -1, "pos_long_num": 2, "pos_short_num": 3}
    df = pd.DataFrame([{**base, "clgroup": "FIZ", "pos": 10}, {**base, "clgroup": "YUR", "pos": -10}])
    out = ap.finalize(df, "futoi", cfg(), {})
    assert len(out) == 1 and out.loc[0, "pos_fiz"] == 10 and out.loc[0, "pos_yur"] == -10
    assert {"pos_long_num_fiz", "pos_short_yur"} <= set(out.columns)


def test_finalize_hi2_pivot_wide():
    df = pd.DataFrame({"ticker": "SBER", "timestamp": ts("2024-03-01 18:40"), "metric": ["hhi_volume", "hhi_buy"],
                       "value": [5, 7], "reference": None})
    out = ap.finalize(df, "hi2", cfg(), {})
    assert out.loc[0, "hhi_volume"] == 5 and out.loc[0, "hhi_buy"] == 7 and "reference" not in out


def test_finalize_alerts_keeps_duplicate_timestamps():
    df = pd.DataFrame({"ticker": "SBER", "timestamp": ts("2024-03-01 10:00"), "alert_type": ["a", "b"], "value": [1, 2]})
    assert len(ap.finalize(df, "alerts", cfg(), {})) == 2


def test_finalize_futures_windows_and_roll_flag():
    c1 = ap.Contract("SiH4", "Si", date(2023, 1, 1), date(2024, 3, 21))
    c2 = ap.Contract("SiM4", "Si", date(2023, 1, 1), date(2024, 6, 20))
    windows = {"Si": [(c1, date(2024, 3, 1), date(2024, 3, 16)), (c2, date(2024, 3, 17), date(2024, 3, 31))]}
    days = ["2024-03-15", "2024-03-18"]
    df = pd.DataFrame([{"ticker": "Si", "contract": c, "timestamp": ts(f"{d} 10:00"), "close": i}
                       for i, (c, d) in enumerate((c, d) for c in ("SiH4", "SiM4") for d in days)])
    out = ap.finalize(df, "candles", cfg(), windows)
    assert out[["contract", "roll"]].values.tolist() == [["SiH4", False], ["SiM4", True]]
    assert list(out.columns[:4]) == ["ticker", "timestamp", "contract", "roll"]
