import pytest

from conftest import FakeResponse, ap, iss

HTML_NO_SUB = b"<html><body>The information is available only to <a>subscribers</a>.</body></html>"


def test_auth_header(make_client):
    client, session = make_client(lambda p, q: {})
    assert session.headers["Authorization"] == "Bearer test-token"


def test_subscription_html_detected(make_client):
    client, _ = make_client(lambda p, q: FakeResponse(ctype="text/html; charset=utf-8", body=HTML_NO_SUB))
    with pytest.raises(ap.SubscriptionError):
        client.get_json("datashop/algopack/eq/tradestats/SBER")


def test_401_is_fatal_without_retry(make_client):
    client, session = make_client(lambda p, q: FakeResponse(status=401, payload={"message": "Unauthorized"}))
    with pytest.raises(ap.AlgopackError, match="401"):
        client.get_json("x")
    assert len(session.calls) == 1


def test_retry_on_503_then_success(make_client):
    responses = iter([FakeResponse(status=503), {"ok": 1}])
    client, session = make_client(lambda p, q: next(responses))
    assert client.get_json("x") == {"ok": 1}
    assert len(session.calls) == 2


def test_retries_exhausted(make_client):
    client, session = make_client(lambda p, q: FakeResponse(status=502))
    with pytest.raises(ap.AlgopackError, match="retries"):
        client.get_json("x")
    assert len(session.calls) == client.max_retries + 1


def test_error_message_block(make_client):
    client, _ = make_client(lambda p, q: iss("futoi", ["ERROR_MESSAGE"], [["Free users can't receive data"]]))
    with pytest.raises(ap.AlgopackError, match="Free users"):
        client.fetch_rows("x", {}, "futoi")


def test_pagination_with_cursor(make_client):
    pages = {0: [[1], [2]], 2: [[3]]}
    client, session = make_client(lambda p, q: iss("data", ["v"], pages[q["start"]], (q["start"], 3, 2)))
    assert [r["v"] for r in client.fetch_rows("x", {}, "data")] == [1, 2, 3]
    assert len(session.calls) == 2


def test_pagination_until_empty_page(make_client):
    pages = {0: [[1], [2]], 2: [[3]], 3: []}
    client, session = make_client(lambda p, q: iss("candles", ["v"], pages[q["start"]]))
    assert [r["v"] for r in client.fetch_rows("x", {}, "candles")] == [1, 2, 3]
    assert [c[1]["start"] for c in session.calls] == [0, 2, 3]


def test_pagination_not_advancing_raises(make_client):
    client, _ = make_client(lambda p, q: iss("data", ["v"], [[1], [2]]))
    with pytest.raises(ap.AlgopackError, match="does not advance"):
        client.fetch_rows("x", {}, "data")


def test_futoi_fetched_day_by_day_and_cap_guard(make_client):
    cols = ["tradedate", "tradetime", "clgroup", *ap.FUTOI_VALUES]
    client, session = make_client(lambda p, q: iss("futoi", cols, [[q["from"], "10:00:00", "FIZ", 1, 2, 3, 4, 5]]))
    df = ap.fetch_futoi(client, "Si", ap.date(2024, 3, 1), ap.date(2024, 3, 3))
    assert len(df) == 3 and [c[1]["from"] for c in session.calls] == ["2024-03-01", "2024-03-02", "2024-03-03"]

    capped, _ = make_client(lambda p, q: iss("futoi", cols, [["2024-03-01", "10:00:00", "FIZ", 1, 2, 3, 4, 5]] * 1000))
    with pytest.raises(ap.AlgopackError, match="cap"):
        ap.fetch_futoi(capped, "Si", ap.date(2024, 3, 1), ap.date(2024, 3, 1))
