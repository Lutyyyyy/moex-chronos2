# data_pipeline: MOEX AlgoPack extraction

Pulls MOEX market data through the [AlgoPack](https://data.moex.com/products/algopack) API into clean, long-format
Parquet files (`ticker, timestamp, features...`) that feed the three studies in [`../forecasting/`](../forecasting/).
No data is committed: AlgoPack data can't be redistributed.

**What it produces**
- Candles for shares, indexes, currencies and futures at 1m / 10m / 1h / 1d.
- AlgoPack analytical datasets (Super Candles: tradestats, orderstats, obstats; HI2; Alerts; FUTOI).
- Continuous futures series with explicit roll handling, so returns never span two contracts.
- A dividend/split-adjusted close (`close_adj`) next to the untouched raw close.
- A reproducible, liquidity-ranked equity universe.

**How to run**
1. Put your AlgoPack key in `data_pipeline/.env` as `ALGOPACK_API_KEY=<token>` (never committed).
2. Set tickers, intervals, datasets and the period in [`config.md`](config.md). Its first YAML block is the
   pipeline config.
3. Run locally, or in Colab with [`notebooks/algopack_pipeline.ipynb`](notebooks/algopack_pipeline.ipynb):
   ```
   python -c "import sys; sys.path.insert(0,'src'); import algopack_pipeline as ap; print(ap.run('config.md'))"
   ```
   Runs are resumable. The full config reference, output layout and error table are in
   [`docs/usage.md`](docs/usage.md); the accessible universe is in [`docs/universe.md`](docs/universe.md).

**Layout**
- [`src/algopack_pipeline.py`](src/algopack_pipeline.py) is the single source of the pipeline. The Colab notebook
  is generated from it by [`tools/build_notebook.py`](tools/build_notebook.py) and never hand-edited.
- [`tests/`](tests/): an offline suite against a fake ISS server (`pytest`), plus `pytest -m live` against the
  real API.
- [`algopack_notes.md`](algopack_notes.md): verified facts about the API (auth, endpoints, fields, paging,
  free-tier behaviour). The official docs are JS-rendered and drift between client versions.
- [`certs/russian_trusted_ca.pem`](certs/): the **public** Russian Trusted Root and Sub CA certificates.
  `apim.moex.com` serves a TLS certificate issued by this CA, which is not in the standard trust stores (certifi,
  macOS, Linux), so every request would fail verification without it. It is not a secret. The Sub CA expires
  2027-03-06; refresh it from `https://gu-st.ru/content/Other/doc/`.
