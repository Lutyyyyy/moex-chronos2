from datetime import date

import pandas as pd

from conftest import ap, iss

CANDLE_COLS = ["open", "high", "low", "close", "volume", "value", "begin", "end"]


def _shares_table(rows):
    """rows: list of (SECID, INSTRID, VALTODAY) → the `shares` table `universe_report()` would build."""
    return pd.DataFrame(
        {"SECID": [r[0] for r in rows], "SHORTNAME": [r[0] for r in rows],
         "INSTRID": [r[1] for r in rows], "VALTODAY": [r[2] for r in rows]}
    )


def _candle_rows(n, start="2025-05-13"):
    d = pd.bdate_range(start, periods=n)
    return [[1, 1, 1, 1, 100, 100, ts.strftime("%Y-%m-%d 00:00:00"), ts.strftime("%Y-%m-%d 00:00:00")] for ts in d]


def _paged_candles_router(n_rows, page_size=500):
    """Router for a single-SECID candles fetch that actually paginates (matches ISS: 500 rows/page)."""
    rows = _candle_rows(n_rows)

    def router(path, params):
        start = params["start"]
        page = rows[start:start + page_size]
        return iss("candles", CANDLE_COLS, page, cursor=(start, n_rows, page_size))
    return router


def test_non_equity_instruments_excluded_without_a_request(make_client):
    """ETFs/funds (INSTRID != EQIN) never trigger a candles fetch — filtered from the securities table alone."""
    tables = {"shares": _shares_table([("AKMM", "IFTF", 500), ("SBER", "EQIN", 1000)])}
    calls = []

    def router(path, params):
        calls.append(path)
        return _paged_candles_router(300)(path, params)

    client, _ = make_client(router)
    out = ap.rank_equity_universe(tables, client, top_n=10, min_history_days=240,
                                   history_end=date(2026, 6, 1))
    akmm = out[out["SECID"] == "AKMM"].iloc[0]
    assert akmm["status"].startswith("excluded: non-equity")
    assert not any("AKMM" in c for c in calls)


def test_short_history_excluded(make_client):
    client, _ = make_client(_paged_candles_router(50))
    tables = {"shares": _shares_table([("NEWCO", "EQIN", 100)])}
    out = ap.rank_equity_universe(tables, client, top_n=10, min_history_days=240,
                                   history_end=date(2026, 6, 1))
    row = out.iloc[0]
    assert row["status"].startswith("excluded: history_days=")
    assert row["history_days"] == 50


def test_ranked_by_valtoday_and_top_n_cutoff(make_client):
    client, _ = make_client(_paged_candles_router(300))
    tables = {"shares": _shares_table([("A", "EQIN", 100), ("B", "EQIN", 300), ("C", "EQIN", 200)])}
    out = ap.rank_equity_universe(tables, client, top_n=2, min_history_days=240,
                                   history_end=date(2026, 6, 1))
    selected = out[out["status"] == "selected"].sort_values("rank")
    assert selected["SECID"].tolist() == ["B", "C"]
    assert selected["rank"].tolist() == [1, 2]
    excluded_a = out[out["SECID"] == "A"].iloc[0]
    assert excluded_a["status"] == "excluded: below top_n cutoff"


def test_fetch_error_excludes_without_raising(make_client):
    from conftest import FakeResponse
    client, _ = make_client(lambda p, q: FakeResponse(status=500))
    tables = {"shares": _shares_table([("BADCO", "EQIN", 100)])}
    out = ap.rank_equity_universe(tables, client, top_n=10, min_history_days=240,
                                   history_end=date(2026, 6, 1))
    row = out.iloc[0]
    assert row["status"].startswith("excluded: fetch error")


def test_save_equity_universe_writes_audit_and_yaml(make_client, tmp_path):
    client, _ = make_client(_paged_candles_router(300))
    tables = {"shares": _shares_table([("SBER", "EQIN", 1000), ("AKMM", "IFTF", 500)])}
    ranked = ap.rank_equity_universe(tables, client, top_n=10, min_history_days=240,
                                      history_end=date(2026, 6, 1))
    yaml_path = ap.save_equity_universe(ranked, tmp_path, meta={"generated": "2026-06-01"})
    assert yaml_path.exists()
    assert (tmp_path / "equity_universe_candidates.csv").exists()
    import yaml as _yaml
    payload = _yaml.safe_load(yaml_path.read_text())
    assert payload["tickers"] == ["SBER"]
    assert payload["n_selected"] == 1
