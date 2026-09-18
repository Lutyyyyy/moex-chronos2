from datetime import date

from conftest import ap, iss


def contract(secid, last, first="2020-01-01"):
    return ap.Contract(secid, secid[:2], date.fromisoformat(first), date.fromisoformat(last))


def test_roll_schedule_windows_are_contiguous_and_clipped():
    cs = [contract("SiM4", "2024-06-20"), contract("SiH4", "2024-03-21"), contract("SiU4", "2024-09-19")]
    sched = ap.roll_schedule(cs, 5, date(2024, 3, 1), date(2024, 7, 1))
    assert [(c.secid, lo, hi) for c, lo, hi in sched] == [
        ("SiH4", date(2024, 3, 1), date(2024, 3, 16)),
        ("SiM4", date(2024, 3, 17), date(2024, 6, 15)),
        ("SiU4", date(2024, 6, 16), date(2024, 7, 1)),
    ]


def test_roll_schedule_respects_first_trade_and_drops_out_of_range():
    cs = [contract("BRF4", "2023-12-29"), contract("BRG4", "2024-02-01", first="2024-01-15")]
    sched = ap.roll_schedule(cs, 0, date(2024, 1, 10), date(2024, 1, 31))
    assert [(c.secid, lo, hi) for c, lo, hi in sched] == [("BRG4", date(2024, 1, 15), date(2024, 1, 31))]


def _securities_router(last_trade):
    def route(path, params):
        return {**iss("description", ["name", "value"], [["LSTTRADE", last_trade], ["FRSTTRADE", "2022-01-01"]]),
                **iss("boards", ["boardid"], [["RFUD"]])}
    return route


def test_resolve_contract_ok_and_other_decade_rejected(make_client):
    client, _ = make_client(_securities_router("2024-03-21"))
    c = ap.resolve_contract(client, "SiH4", 2024, 3)
    assert c == ap.Contract("SiH4", "Si", date(2022, 1, 1), date(2024, 3, 21))
    old, _ = make_client(_securities_router("2014-03-17"))
    assert ap.resolve_contract(old, "SiH4", 2024, 3) is None


def test_resolve_contract_not_found(make_client):
    client, _ = make_client(lambda p, q: {**iss("description", ["name", "value"], []), **iss("boards", ["boardid"], [])})
    assert ap.resolve_contract(client, "SiF4", 2024, 1) is None


def test_discover_contracts_months_filter_and_cache(make_client, tmp_path):
    def route(path, params):
        secid = path.rsplit("/", 1)[1]
        month = ap.MONTH_CODES.index(secid[2]) + 1
        year = 2020 + int(secid[3])
        if secid[2] not in "HMUZ":
            return {}
        return {**iss("description", ["name", "value"], [["LSTTRADE", f"{year}-{month:02d}-15"]]), **iss("boards", ["boardid"], [["RFUD"]])}

    client, session = make_client(route)
    spec = ap.FuturesSpec("Si", "HZ", 5)
    found = ap.discover_contracts(client, spec, date(2023, 1, 1), date(2023, 12, 31), tmp_path)
    assert [c.secid for c in found] == ["SiH3", "SiZ3", "SiH4", "SiZ4"]
    n = len(session.calls)
    ap.discover_contracts(client, spec, date(2023, 1, 1), date(2023, 12, 31), tmp_path)
    assert len(session.calls) == n  # past years served from meta/contracts cache


def test_month_starts_and_month_end():
    assert ap.month_starts(date(2023, 11, 20), date(2024, 2, 1)) == [date(2023, 11, 1), date(2023, 12, 1), date(2024, 1, 1), date(2024, 2, 1)]
    t = ap.Task("candles", "shares", "SBER", "SBER", "1d", date(2024, 2, 1))
    assert t.month_end == date(2024, 2, 29)
