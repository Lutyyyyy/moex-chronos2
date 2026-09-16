"""Live integration test against apim.moex.com (needs a paid ALGOPACK key in .env).
Run: pytest -m live"""
import pandas as pd
import pytest

from conftest import ROOT, ap

pytestmark = pytest.mark.live

CONFIG = f"""
```yaml
plan: paid
paths: {{env_file: "{(ROOT / '.env').as_posix()}", output_root: out}}
period: {{start: 2024-03-14, end: 2024-03-19}}
datasets: [candles, tradestats, orderstats, obstats, hi2, alerts, futoi]
candles: {{intervals: [1h, 1d]}}
tickers:
  shares: [SBER]
  indices: [IMOEX]
  currency: [CNYRUB_TOM]
  futures: [Si]
```
"""


@pytest.fixture(scope="module")
def live_run(tmp_path_factory):
    if not (ROOT / ".env").exists():
        pytest.skip("no .env with ALGOPACK_API_KEY")
    d = tmp_path_factory.mktemp("live")
    (d / "config.md").write_text(CONFIG)
    cfg = ap.load_config(d / "config.md")
    return cfg, ap.run(cfg)


def test_all_datasets_produced(live_run):
    cfg, summary = live_run
    produced = set(zip(summary.dataset, summary.interval.fillna(""), summary.group))
    expected = {("candles", iv, g) for iv in ("1h", "1d") for g in ("shares", "indices", "currency", "futures")}
    expected |= {(ds, "", g) for ds, spec in ap.DATASETS.items() if ds != "candles" for g in spec["markets"]}
    assert expected <= produced, expected - produced
    assert (summary.rows > 0).all()


def test_schema_and_timezone(live_run):
    cfg, summary = live_run
    for f in summary.file:
        df = pd.read_parquet(f)
        assert list(df.columns[:2]) == ["ticker", "timestamp"], f
        assert str(df["timestamp"].dt.tz) == ap.TZ, f
        d = df["timestamp"].dt.date
        assert d.min() >= cfg.start and d.max() <= cfg.end, f


def test_si_roll_between_h4_and_m4(live_run):
    cfg, _ = live_run
    df = pd.read_parquet(cfg.output_root / "processed" / "candles_1h" / "futures.parquet")
    assert df["contract"].unique().tolist() == ["SiH4", "SiM4"]
    assert df.loc[df["roll"], "timestamp"].dt.date.astype(str).tolist() == ["2024-03-18"]


def test_rerun_fetches_nothing(live_run):
    cfg, _ = live_run
    client = ap.Client.from_config(cfg)
    ap.run(cfg, client=client)
    assert client.n_requests == 0
