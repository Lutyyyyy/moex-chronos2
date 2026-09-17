import json
from datetime import date

import pandas as pd
import pytest

from conftest import ap


def _candles(ticker, dates, closes):
    return pd.DataFrame({
        "ticker": ticker,
        "timestamp": pd.to_datetime(dates),
        "close": closes,
    })


def test_compute_close_adj_single_dividend_scales_prior_prices_only():
    df = _candles("SBER", ["2024-03-11", "2024-03-12", "2024-03-13", "2024-03-14", "2024-03-15"],
                  [100.0, 100.0, 100.0, 95.0, 96.0])
    dividends = pd.DataFrame([{"ticker": "SBER", "ex_date": date(2024, 3, 14), "dividend": 5.0}])

    adj = ap.compute_close_adj(df["close"], df["timestamp"], "SBER", dividends)

    # factor = 1 - 5/100 = 0.95, applied to every close strictly before the ex-date
    assert adj.iloc[:3].tolist() == pytest.approx([95.0, 95.0, 95.0])
    # on/after the ex-date, close is untouched
    assert adj.iloc[3:].tolist() == pytest.approx([95.0, 96.0])


def test_compute_close_adj_composes_multiple_dividends():
    df = _candles("SBER", ["2024-01-10", "2024-03-14", "2024-06-14", "2024-06-15"],
                  [200.0, 190.0, 180.0, 182.0])
    dividends = pd.DataFrame([
        {"ticker": "SBER", "ex_date": date(2024, 3, 14), "dividend": 10.0},   # factor vs close on 01-10 = 200
        {"ticker": "SBER", "ex_date": date(2024, 6, 14), "dividend": 9.0},    # factor vs close on 03-14 = 190 (unadjusted lookup)
    ])

    adj = ap.compute_close_adj(df["close"], df["timestamp"], "SBER", dividends)

    f1 = 1 - 10.0 / 200.0
    f2 = 1 - 9.0 / 190.0
    assert adj.iloc[0] == pytest.approx(200.0 * f1 * f2)   # before both ex-dates: both factors stack
    assert adj.iloc[1] == pytest.approx(190.0 * f2)        # between the two ex-dates: only the later factor
    assert adj.iloc[2:].tolist() == pytest.approx([180.0, 182.0])  # after both: untouched


def test_compute_close_adj_ignores_other_tickers_and_implausible_dividends():
    df = _candles("SBER", ["2024-03-11", "2024-03-14"], [100.0, 95.0])
    dividends = pd.DataFrame([
        {"ticker": "GAZP", "ex_date": date(2024, 3, 14), "dividend": 5.0},     # different ticker: ignored
        {"ticker": "SBER", "ex_date": date(2024, 3, 14), "dividend": 150.0},   # dividend > price: skipped, not corrupted
    ])

    adj = ap.compute_close_adj(df["close"], df["timestamp"], "SBER", dividends)

    assert adj.tolist() == pytest.approx([100.0, 95.0])


def test_compute_close_adj_applies_known_split():
    df = _candles("BELU", ["2024-08-19", "2024-08-22", "2024-08-23"], [800.0, 105.0, 108.0])
    dividends = pd.DataFrame(columns=["ticker", "ex_date", "dividend"])

    adj = ap.compute_close_adj(df["close"], df["timestamp"], "BELU", dividends)

    # 8-for-1 split effective 2024-08-22 (per KNOWN_SPLITS, verified against real data):
    # prior close scaled by 1/8
    assert adj.iloc[0] == pytest.approx(100.0)
    assert adj.iloc[1:].tolist() == pytest.approx([105.0, 108.0])


def test_fetch_dividends_caches_and_does_not_refetch(tmp_path):
    calls = []

    def fetcher(url):
        calls.append(url)
        return json.dumps([{"uid": "SBER", "df": [{"day": "2024-03-14", "dividend": 5.0}]}]).encode()

    cfg = ap.Config(path=tmp_path / "config.md", plan="paid", env_file=tmp_path / "none.env",
                     output_root=tmp_path, start=date(2024, 1, 1), end=date(2024, 12, 31),
                     datasets=["candles"], intervals=["1d"], tickers={"shares": ["SBER"]},
                     futures=[])

    out1 = ap.fetch_dividends(cfg, fetcher)
    assert len(calls) == 1
    assert out1.to_dict("records") == [{"ticker": "SBER", "ex_date": date(2024, 3, 14), "dividend": 5.0}]

    out2 = ap.fetch_dividends(cfg, fetcher)
    assert len(calls) == 1                     # cache hit: fetcher not called again
    pd.testing.assert_frame_equal(out1, out2)
