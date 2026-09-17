# Current state

_Last updated: 2026-09-17 (equity universe selection added; adopted by ../moex-hack Path A)._

## Done
- Access checks: auth, TLS CA, free and paid limits, endpoints, paging quirks. Details in `algopack_notes.md`.
- User decisions recorded in `needed.md` (✅ section).
- **Pipeline v1:**
  - `src/algopack_pipeline.py` is the source of truth. `notebooks/algopack_pipeline.ipynb` is generated from it by `tools/build_notebook.py`.
  - Config comes from the first yaml block of `config.md`: plan free/paid, paths, period, datasets, candle intervals 1m/10m/1h/1d, tickers by group, continuous futures roll.
  - Datasets: candles, tradestats, orderstats, obstats, hi2, alerts, futoi.
  - Output is Parquet, tz-aware MSK: `processed/<dataset>[_<interval>]/<group>.parquet`, plus a raw month-chunk cache so runs resume.
  - Futures: contract discovery (cached), expiry-based roll, `contract`/`roll` columns.
  - `universe_report()` writes a listing snapshot.
- **Equity universe selection (2026-09-17, for `../moex-hack`'s Path A pivot):**
  - `rank_equity_universe(tables, client, top_n, min_history_days, max_missing_frac)` — filters
    TQBR `shares` to real equities (`INSTRID == "EQIN"`, excludes ETFs/funds), checks each
    candidate's daily-candle history for length/missingness, ranks survivors by `VALTODAY`.
    Returns every candidate with a `status` (selected / excluded + reason) — full audit trail.
  - `save_equity_universe(ranked, out_dir, meta)` writes `equity_universe_candidates.csv` (audit
    trail) + `equity_universe.yaml` (selected tickers + selection metadata, paste-ready for
    `config.md`).
  - **Run 2026-09-17**: 506 TQBR candidates → 243 excluded (non-equity/ETF), 13 excluded
    (short history / too much missing data), 170 excluded (below top-80 cutoff by turnover),
    **80 selected**. 527 requests, ~94s. Output at `data/universe/equity_universe.yaml` (gitignored,
    under `data/`) — regenerate via the snippet in `docs/usage.md` §6 if a fresh universe is needed.
- Tests: `pytest` gives 45 offline tests passing (40 original + 5 new for `rank_equity_universe`/
  `save_equity_universe`); `pytest -m live` gives 4 live tests passing (SBER/IMOEX/CNYRUB_TOM/Si,
  2024-03-14..19, all datasets, roll check, zero-request re-run).
- Docs: `docs/usage.md` (now includes §6 equity universe selection), `docs/universe.md`, `docs/universe_snapshot.md`.
- Local env: installed `pyarrow`, `pyyaml`, `pytest`.

## Session update (2026-09-17): `config.md` scoped to the Phase B gate

- `tickers.shares` expanded from the original 10-ticker panel to a **24-ticker stratified
  subsample** of `equity_universe.yaml`'s 80: GAZP, SMLT, SBER, ROSN, MTSS, LKOH, T, OZON,
  PLZL, VTBR, YDEX, VKCO, GMKN, MAGN, X5, AFKS, MGNT, PHOR, AFLT, IRAO, FEES, MDMG, RAGR, LENT.
  Picked as top-liquidity ticker(s) within each of 12 hand-classified sectors (oil_gas, metals,
  financials, tech, telecom, retail, transport, utilities, chemicals, healthcare, agriculture,
  realestate, holding) — not a flat top-24 by turnover, to avoid testing the gate only on a
  liquidity-correlated cluster. Sector map is a manual classification, not from MOEX metadata
  (no sector field in `universe_report()`'s output) — noted as best-effort, not verified against
  an authoritative source.
- `datasets` scoped from all 7 down to `[candles]`; `candles.intervals` from all 4 down to
  `[1d]` — matches what Phase B (and Phase C's lead-lag screening) actually need for their first
  pass; widen later if a phase needs richer covariates or finer intervals.
- Offline test suite re-run after the config edit: 47/47 passing (config-only change, no code
  touched).
- Old 10-ticker/7-dataset/4-interval config kept as documented history in `config.md`'s
  "Panel rationale" section, not deleted.

## Session update (2026-09-17): `config.md` expanded to the full 80-ticker universe for Phase C

- Phase B ran to completion (22-ticker panel, both `group_mode` arms) — **gate FAILED**
  (chance-level DA in both arms, 0/64 BH-significant cells; see `../moex-hack`'s
  `docs/current_state.md` session entry 17). Per the project's pivot plan, this formally
  means Phase C isn't funded — but the user decided to proceed to it anyway on the grounds
  that Phase C asks a genuinely different question (pairwise lead-lag structure across many
  tickers) that Phase B's fixed 16-ticker basket-average test never actually tested. Full
  reasoning in `../moex-hack`'s local pivot plan (rev. 3) and `path_a/scratchpads/
  phase_c_scratch_pad.md`.
- `tickers.shares` expanded from the 22-ticker Phase B stratified subsample to the **full
  80-ticker `equity_universe.yaml` list** — Phase C's discovery step needs the widest
  reasonable universe (up to 3160 pairs) rather than a curated subsample.
  `datasets`/`candles.intervals` unchanged (`[candles]`/`[1d]`).
- X5 and RAGR (both known from the Phase B pull to have zero 2020-2024 history — recent MOEX
  redomiciliations) are still in the 80-ticker list, left untrimmed per the established
  pattern (pipeline's own missing-ticker reporting is the audit trail). Other tickers among
  the 80 may also turn out to have short/gappy history — not yet checked; will show up in the
  pull's own coverage reporting.
- Offline test suite not re-run yet for this specific change (config-only edit, same shape as
  the Phase B config change which needed no code touch) — re-confirm before relying on it if
  anything else changes alongside.

## Session update (2026-09-17): `config.md` widened to `candles/1d + 1h` for the post-Phase-C 1h follow-on

- Phase C (daily lead-lag screen, full pipeline) concluded — **gate FAILED**: 20
  discovery-shortlisted pairs, 0/20 replicated out-of-sample confirmation (see
  `../path_a/scratchpads/phase_c_scratch_pad.md`). Third independent negative result for
  zero-shot Chronos-2 on MOEX returns (after Stage 2b and Phase B), each at daily resolution.
- User's original intent was 1h resolution; now proceeding as a genuinely different follow-on
  test (different frequency regime, not a retry of the same lead-lag hypothesis). Sized
  earlier as affordable — AlgoPack's request cost is driven by month-chunks, not bar count,
  so a 1h pull is expected to cost roughly the same order as the 80-ticker daily pull already
  done (~24 min, 6039 requests), not proportionally more with bar count.
- `candles.intervals` widened from `[1d]` to `[1d, 1h]`. `period` (2020-01-01..2024-12-31)
  deliberately **not** narrowed to the ~24-month window the 1h analysis will actually use —
  `period` applies globally across every interval in this pipeline, so narrowing it would
  silently truncate the already-processed, already-cited `candles_1d/shares.parquet` that
  Phase B/C's committed results are built on. The 1h analysis window is restricted on the
  notebook side (`date_from`/`date_till` in the Chronos-side configs) instead.
- Offline test suite re-run after the config edit: 47/47 passing (config-only change).

## Session update (2026-09-17): `config.md` widened to `candles/1d + 1h + 10m` for a 10-minute follow-on

- The 1h follow-on (above) ran to completion — **gate FAILED again** (13 discovery-shortlisted
  pairs, 0/13 replicated; see `../path_a/scratchpads/phase_c_1h_scratch_pad.md`). Phase E
  (event-conditioned burst detection, a genuinely different hypothesis shape) then also ran at
  both daily and 1h and came back null across three parameter sets (see
  `../path_a/scratchpads/phase_e_scratch_pad.md`). A per-window clustering check on Phase B's
  multivariate arm (label-permutation test, p=0.22) ruled out a hidden localized effect the
  aggregate metric might have missed. Five independent negative results total at daily/1h,
  across three hypothesis shapes (aggregate forecasting skill, full-sample pairwise
  correlation, short-window causal bursts).
- User's explicit next step: push to 10-minute bars, the finest interval this pipeline
  supports. `candles.intervals` widened from `[1d, 1h]` to `[1d, 1h, 10m]` — additive, not
  replacing either existing interval. Same 80-ticker universe and full 2020-2024 `period`
  (unchanged, same truncation-avoidance rationale as the 1h widening — `period` applies
  globally across every interval).
- **Real added cost, flagged before pulling**: unlike the 1h widening (which cost roughly the
  same order as the daily pull, since AlgoPack's request cost is driven by month-chunks, not
  bar count, and most 1h months fit in a single ISS page), 10m bars are dense enough that most
  months need **~3 ISS pages** (10m gives ~1113 bars/month vs. the 500-row page limit, vs. 1h's
  ~189 bars/month fitting in one page). This interval alone is estimated at roughly **3x the
  1h pull's request volume — ~2.5 hours, ~29,000 requests** — a real time commitment, not a
  quick add-on. Not yet run as of this entry.
- Offline test suite re-run after the config edit: 47/47 passing (config-only change).

## Session update (2026-09-17): dividend/split price adjustment (`close_adj`)

- Triggered by a data-quality question during the 10m pull follow-on: neither this pipeline
  nor `../moex-hack`'s `path_a` ever adjusted prices for dividends or splits — all prior
  results (Stage 2b, Phase B, Phase C daily+1h, Phase E daily+1h) were computed on raw
  close-to-close returns. Confirmed via direct scan this is real: MTSS shows clean
  dividend-sized drops (e.g. -34.29 on 2023-06-29), BELU shows an unmissable ~8x single-day
  move (2024-05-24) that is a confirmed 8-for-1 split, not a data error.
- **MOEX ISS has no free dividend endpoint** — `securities/{secid}/dividends.json` is
  empty/broken for anonymous access; the only working ISS route
  (`iss/cci/corp-actions/dividends`) is subscriber-only. Neither `apimoex` nor `moexalgo`
  implement dividend fetching. Verified via dedicated research.
- **Data source**: `poptimizer`'s community-maintained dump,
  `https://raw.githubusercontent.com/WLM1ke/poptimizer/master/dump/dividends.json` (142
  tickers, `{uid, df: [{day, dividend}]}`). Cross-checked against independently-verified MTSS
  and GAZP dividend facts — exact match. Covers cash dividends only, not splits; 23/80
  universe tickers have no record (not yet individually verified as "no dividends" vs.
  "absent from this source").
- **Implementation** (`src/algopack_pipeline.py`):
  - `fetch_dividends(cfg, fetcher=None)` downloads and caches the dump at
    `<output_root>/dividends.json` (gitignored under `data/`, same convention as
    `equity_universe.yaml` — regenerable via code, not committed). `fetcher` is injectable so
    offline tests never touch the network.
  - `KNOWN_SPLITS` — a small manually-verified dict (currently just BELU, 2024-05-24, 8-for-1)
    rather than automatic statistical detection; user's explicit choice, given the
    false-positive risk of auto-detecting splits from large-move scans.
  - `compute_close_adj(close, timestamp, ticker, dividends)` — standard backward-multiplicative
    total-return adjustment: prices strictly before each ex-date (dividend's `day` field, taken
    at face value — already validated against ground truth) are scaled by
    `1 - dividend/close_prev`; splits applied the same way with factor `1/ratio`. Multiple
    events compose correctly (order-independent, since each scales only the prefix before its
    own ex-date).
  - Wired into `finalize()`/`build_processed()`: for `dataset == "candles", group == "shares"`,
    adds a new **additive** `close_adj` column. `open/high/low/close/volume/value` are left
    untouched — **all prior results remain exactly as computed**, since nothing previously
    read a `close_adj` column. User's explicit design choice: adjustment lives in `algo_data`
    (this repo), not in `../moex-hack/path_a` — processed parquet files are already adjusted
    before Path A ever sees them.
  - Applied **going forward only** — no retroactive re-run of Stage 2b/Phase B/C/E's already-
    committed results (user's explicit choice).
- Tests: new `tests/test_dividends.py` (5 tests — single dividend, composing multiple
  dividends, ignoring other tickers/implausible dividends, known-split application, fetch
  caching/no-refetch). `test_pipeline_offline.py`'s end-to-end test extended to assert
  `close_adj` appears and is correctly scaled, using an injected fake fetcher (stays offline).
  50/50 offline tests passing (45 prior + 5 new). `tools/build_notebook.py` re-run — notebook
  regenerated and current.
- Docs: `docs/usage.md` §4 documents the new `close_adj` column, its method, and the 23/80
  coverage gap.

## Session update (2026-09-17): real-data verification of the dividend/split adjustment

- Fetched the real poptimizer dump through the actual pipeline function (`fetch_dividends()`,
  not the earlier manually-placed scratch file) — `data/dividends.json` now exists as a real,
  pipeline-managed cache (1180 dividend rows, 142 tickers).
- Spot-checked BELU and MTSS directly against their real raw daily chunks (not synthetic test
  fixtures). **Found and fixed a real bug**: `KNOWN_SPLITS`'s BELU date was wrong
  (2024-05-24 — BELU's price is smooth through that entire week, no discontinuity at all). The
  real ~8x drop is on **2024-08-22** (4680→714, ratio 6.55, consistent with the previously
  confirmed 8-for-1 split). Corrected `KNOWN_SPLITS["BELU"]` and the test that encoded the same
  wrong date; full suite re-verified (50/50 passing), notebook rebuilt.
- Re-verified after the fix: BELU's 2024-08-22 raw return -84.7% now shows as +22.1%
  post-adjustment (a real post-split move, not an artifact). MTSS's two known dividends
  (2023-06-29, 2024-07-16) both correctly smoothed.
- Ran a broader scan across all 80 tickers with raw daily chunks: computed market-relative
  excess return (`ticker's close_adj return − that day's cross-sectional mean`) post-adjustment,
  flagged |excess| > 0.15. **159 (ticker, date) flags across 43 tickers remain.** Inspected the
  top of this list: dominated by well-known genuine market-wide events (2022-02-24 invasion
  crash, 2022-03-28/29/31 post-trading-halt reopening) — not artifacts. BELU's Feb–Mar 2021
  cluster (7 entries in the top 30) looked initially suspicious but on closer inspection is a
  smooth multi-week speculative run-up (1681→6204 over ~3 weeks, gradual, not a single-day
  discontinuity) — inconsistent with a split/dividend, more likely a real low-liquidity
  newly-listed-stock bubble (BELU IPO'd on MOEX in 2021).
- **Decision (discussed with the user): stop here, treat the remaining 159 flags as
  informational, not investigate further.** Rationale: the two known real artifact types
  (BELU's split, dividend-driven single-day drops) are now confirmed fixed via real-data
  checks; the residual list is dominated by identifiable genuine market events, and further
  per-ticker verification would need external news/corporate-action research beyond what's
  available from price data alone — diminishing returns vs. the two bugs actually caught.
  Full flagged list saved to session scratchpad (not part of the repo) for reference if this
  needs revisiting later.
- **State at end of this entry**: `close_adj` code is verified correct against real data for
  the two known cases and the pipeline-managed dividend cache is real. **The actual processed
  parquet files on disk do NOT have `close_adj` yet** — `data/processed/candles_1d/shares.parquet`
  was built before this feature existed and needs a real pipeline run (`ap.run`) to be rebuilt.
  Per the project's execution-mode convention, the user runs this, not this session.

## Session update (2026-09-17): processed files rebuilt with `close_adj` (real run)

- User ran `ap.run("config.md", build_only=True)` — rebuilt all 12 processed files purely from
  the existing raw month-chunk cache (15,840/15,840 chunks cached, 0 fetched, no network
  requests). Completed in ~15s.
- Verified directly against the rebuilt files (not just raw chunks): `close_adj` present with
  **zero nulls** across `candles_1d/1h/10m/shares.parquet` (80,133 / 1,013,140 / 5,502,349 rows,
  76 tickers each — 4 of the 80-ticker universe still have no candle history, same as before).
  BELU's 2024-08-22 split and MTSS's 2023-06-29 dividend both confirmed correctly smoothed in
  the real files, matching the earlier raw-chunk spot-check exactly.
- **`close_adj` is now live and ready to use** in `data/processed/candles_{1d,1h,10m}/shares.parquet`.
  `path_a` still needs to be wired to read `close_adj` instead of raw `close` — not done yet.

## Next steps
1. Run the pipeline with the widened `[1d, 1h, 10m]` interval scope to produce
   `processed/candles_10m/shares.parquet` alongside the existing daily/1h ones. Existing 1d/1h
   raw month-chunk cache and processed output are untouched (interval-scoped, not overwritten);
   only 10m chunks are new fetches. Expect ~2.5 hours given the per-month page-count increase.
   **Now also produces `close_adj` for shares** — first real use of the new adjustment step.
2. Check the 10m pull's actual ticker coverage before trusting it — same caveat as daily/1h
   (some of the 80 may have insufficient/gappy 10m history even where daily/1h history was
   fine).
3. Hand off to `path_a/basic_cells.ipynb`/`runner.ipynb` for the 10m aggregate (Phase B-style
   multivariate-vs-univariate) test — the user's chosen first step, cheaper than a full
   Phase C/E-style screen at 10m's much larger candidate/test-family scale. Should consume
   `close_adj`, not raw `close`, once `path_a` is wired to read it (not yet done as of this
   entry — `load_from_algopack` still only reads the original raw OHLCV columns).
4. Answer the 🟡 items in `needed.md`: Super Candles resampling, futures price adjustment, merged table for moex-hack.
