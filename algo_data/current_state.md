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

## Next steps
1. Run the pipeline with the widened `[1d, 1h]` interval scope to produce
   `processed/candles_1h/shares.parquet` alongside the existing daily one. Existing 1d raw
   month-chunk cache and processed output are untouched (interval-scoped, not overwritten);
   only 1h chunks are new fetches.
2. Check the 1h pull's actual ticker coverage before trusting it — same caveat as the daily
   pull (some of the 80 may have insufficient/gappy 1h history even where daily history was
   fine, since intraday listings/halts can differ from daily coverage).
3. Hand off to `path_a/basic_cells.ipynb` for the 1h discovery/confirmation run (new configs,
   not yet written as of this entry).
4. Answer the 🟡 items in `needed.md`: Super Candles resampling, futures price adjustment, merged table for moex-hack.
