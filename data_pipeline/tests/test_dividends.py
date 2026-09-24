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
    dividends = pd.DataFrame([{"ticker": "SBER", "record_date": date(2024, 3, 14), "dividend": 5.0}])

    adj = ap.compute_close_adj(df["close"], df["timestamp"], "SBER", dividends)

    # factor = 1 - 5/100 = 0.95, applied to every close strictly before the ex-date
    assert adj.iloc[:3].tolist() == pytest.approx([95.0, 95.0, 95.0])
    # on/after the ex-date, close is untouched
    assert adj.iloc[3:].tolist() == pytest.approx([95.0, 96.0])


def test_compute_close_adj_composes_multiple_dividends():
    df = _candles("SBER", ["2024-01-10", "2024-03-14", "2024-06-14", "2024-06-15"],
                  [200.0, 190.0, 180.0, 182.0])
    dividends = pd.DataFrame([
        {"ticker": "SBER", "record_date": date(2024, 3, 14), "dividend": 10.0},   # factor vs close on 01-10 = 200
        {"ticker": "SBER", "record_date": date(2024, 6, 14), "dividend": 9.0},    # factor vs close on 03-14 = 190 (unadjusted lookup)
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
        {"ticker": "GAZP", "record_date": date(2024, 3, 14), "dividend": 5.0},     # different ticker: ignored
        {"ticker": "SBER", "record_date": date(2024, 3, 14), "dividend": 150.0},   # dividend > price: skipped, not corrupted
    ])

    adj = ap.compute_close_adj(df["close"], df["timestamp"], "SBER", dividends)

    assert adj.tolist() == pytest.approx([100.0, 95.0])


def test_compute_close_adj_applies_known_split():
    df = _candles("BELU", ["2024-08-19", "2024-08-22", "2024-08-23"], [800.0, 105.0, 108.0])
    dividends = pd.DataFrame(columns=["ticker", "record_date", "dividend"])

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
    assert out1[out1.ticker == "SBER"].to_dict("records") == [{"ticker": "SBER", "record_date": date(2024, 3, 14), "dividend": 5.0}]
    extra = {(t, d["day"]) for t, ds in ap.KNOWN_EXTRA_DIVIDENDS.items() for d in ds}
    assert extra <= set(zip(out1.ticker, out1.record_date))     # verified extras are appended

    out2 = ap.fetch_dividends(cfg, fetcher)
    assert len(calls) == 1                     # cache hit: fetcher not called again
    pd.testing.assert_frame_equal(out1, out2)


# --- register date -> ex-date (T+2 until 2023-07-28 trades, T+1 from 2023-07-31) -------------

def _bdays(lo, hi):
    return [d.date() for d in pd.bdate_range(lo, hi)]


@pytest.mark.parametrize("record, expected", [
    (date(2022, 7, 14), date(2022, 7, 13)),   # T+2, Thursday record -> gap on Wednesday
    (date(2021, 7, 11), date(2021, 7, 8)),    # T+2, Sunday record -> Thursday (Wed trade settles Fri)
    (date(2023, 7, 31), date(2023, 7, 28)),   # last T+2 trade day: Fri 07-28 settles Tue 08-01 > record
    (date(2023, 8, 1), date(2023, 8, 1)),     # T+1: ex-date = record date
    (date(2024, 7, 8), date(2024, 7, 8)),     # T+1 Monday record (SVCB)
    (date(2024, 7, 7), date(2024, 7, 5)),     # T+1, Sunday record -> Friday
])
def test_ex_date_from_record_settlement_regimes(record, expected):
    assert ap.ex_date_from_record(record, _bdays("2021-06-01", "2024-08-31")) == expected


def test_compute_close_adj_t2_gap_lands_on_derived_ex_date():
    # T+2 era: record 2022-07-14 (Thu) -> ex-date 07-13; the 5-RUB gap is between 07-12 and 07-13
    df = _candles("SBER", ["2022-07-11", "2022-07-12", "2022-07-13", "2022-07-14"], [100.0, 100.0, 95.0, 95.0])
    dividends = pd.DataFrame([{"ticker": "SBER", "record_date": date(2022, 7, 14), "dividend": 5.0}])
    adj = ap.compute_close_adj(df["close"], df["timestamp"], "SBER", dividends,
                               trading_days=_bdays("2022-07-01", "2022-07-29"))
    assert adj.tolist() == pytest.approx([95.0, 95.0, 95.0, 95.0])   # no spurious move on 07-13 or 07-14
