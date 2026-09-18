from datetime import date, timedelta
from pathlib import Path

import pytest

from conftest import ROOT, ap

BASE = """
```yaml
plan: paid
paths: {env_file: .env, output_root: data}
period: {start: 2024-01-01, end: 2024-02-15}
datasets: [candles, tradestats, futoi]
candles: {intervals: [1h, 1d]}
tickers:
  shares: [SBER]
  futures: [Si, {code: BR, roll_days: 3}]
futures: {roll_days_before_expiry: 5}
```
"""


def cfg_from(text, base=Path("/cfg")):
    return ap.parse_config(text, base)


def test_repo_config_md_is_valid():
    cfg = ap.load_config(ROOT / "config.md")
    assert cfg.datasets and cfg.intervals and cfg.futures
    assert cfg.output_root.is_absolute() and cfg.env_file.name == ".env"


def test_parse_basic_and_relative_paths(tmp_path):
    cfg = cfg_from(BASE, tmp_path)
    assert cfg.output_root == (tmp_path / "data").resolve()
    assert cfg.start == date(2024, 1, 1) and cfg.end == date(2024, 2, 15)
    assert cfg.tickers["shares"] == ["SBER"] and cfg.tickers["indices"] == []
    assert cfg.futures == [ap.FuturesSpec("Si", None, 5), ap.FuturesSpec("BR", None, 3)]


def test_end_today():
    cfg = cfg_from(BASE.replace("end: 2024-02-15", "end: today"))
    assert cfg.end == ap.today_msk()


@pytest.mark.parametrize("old,new,msg", [
    ("plan: paid", "plan: gold", "plan"),
    ("[1h, 1d]", "[15m]", "candles.intervals"),
    ("[candles, tradestats, futoi]", "[candles, trades]", "datasets"),
    ("futures: [Si,", "futures: [SIX,", "tickers.futures"),
    ("start: 2024-01-01", "start: 2025-01-01", "period"),
    ("shares: [SBER]", "shares: [SBER]\n  bonds: [X]", "unknown group"),
])
def test_validation_errors(old, new, msg):
    with pytest.raises(ap.ConfigError, match=msg):
        cfg_from(BASE.replace(old, new))


def test_missing_yaml_block():
    with pytest.raises(ap.ConfigError, match="yaml block"):
        cfg_from("# no config here")


def test_load_token_env_file(tmp_path, monkeypatch):
    monkeypatch.delenv("ALGOPACK_API_KEY", raising=False)
    env = tmp_path / ".env"
    env.write_text('OTHER=1\nexport ALGOPACK_API_KEY="abc.def"\n')
    assert ap.load_token(env) == "abc.def"


def test_load_token_env_var_fallback_and_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("ALGOPACK_API_KEY", "from-env")
    assert ap.load_token(tmp_path / "missing.env") == "from-env"
    monkeypatch.delenv("ALGOPACK_API_KEY")
    with pytest.raises(ap.ConfigError):
        ap.load_token(tmp_path / "missing.env")


def test_free_plan_skips_paid_datasets_and_clamps_futoi():
    cfg = cfg_from(BASE.replace("plan: paid", "plan: free").replace("end: 2024-02-15", "end: today")
                   .replace("start: 2024-01-01", f"start: {ap.today_msk() - timedelta(days=60)}"))
    tasks = ap.plan_tasks(cfg, windows={})
    assert {t.dataset for t in tasks} == {"candles", "futoi"}
    assert ap.effective_end(cfg, "futoi") == ap.today_msk() - timedelta(days=ap.FREE_PLAN_FUTOI_EMBARGO_DAYS)
    assert ap.effective_end(cfg, "candles") == ap.today_msk()
