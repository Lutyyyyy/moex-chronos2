import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import algopack_pipeline as ap  # noqa: E402


def iss(block: str, columns: list, rows: list, cursor: tuple | None = None) -> dict:
    """ISS-shaped JSON payload; cursor = (INDEX, TOTAL, PAGESIZE)."""
    payload = {block: {"columns": columns, "data": rows}}
    if cursor:
        payload[f"{block}.cursor"] = {"columns": ["INDEX", "TOTAL", "PAGESIZE"], "data": [list(cursor)]}
    return payload


class FakeResponse:
    def __init__(self, status=200, payload=None, ctype="application/json", body=None):
        self.status_code = status
        self.headers = {"content-type": ctype}
        self.content = body if body is not None else json.dumps(payload or {}).encode()
        self.text = self.content.decode(errors="replace")

    def json(self):
        return json.loads(self.content)


class FakeSession:
    """requests.Session stand-in: `router(path, params)` returns FakeResponse | dict payload."""

    def __init__(self, router):
        self.router = router
        self.headers = {}
        self.calls = []

    def get(self, url, params=None, timeout=None):
        path = url.split("/iss/", 1)[1].removesuffix(".json")
        self.calls.append((path, dict(params or {})))
        res = self.router(path, dict(params or {}))
        return res if isinstance(res, FakeResponse) else FakeResponse(payload=res)


@pytest.fixture
def make_client():
    def _make(router):
        session = FakeSession(router)
        return ap.Client("test-token", pause_sec=0, max_retries=2, session=session, backoff_sec=0), session
    return _make
