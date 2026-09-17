# Current State — MOEX × Chronos-2 Project

Snapshot for the next Claude instance. Picks up after the first successful Stage 0 smoke run (2026-06-12). The single-window prototype is done; the project is now organised around a stage-driven framework backed by YAML configs and a universal runner. **Stage 0 smoke has PASSED end-to-end — the pipeline is validated; Stage 1 is the next run.**

> **Repo reorganized 2026-09-15**: Path A moved from repo root into `path_a/` (mirroring
> `path_b/`); loose root docs consolidated into `docs/`. The "Files in repo" table below and
> the numbered session log after it describe file locations **as they were at the time each
> entry was written** — for current paths see the root [README.md](../README.md) and
> [index.md](index.md). Historical entries are left unedited below (they're a record, not a
> spec); only paths in this note and the table header are current.

## Files in repo (paths current as of the 2026-09-15 reorg)

| File / dir | Status | Purpose |
|------------|--------|---------|
| `README.md` | **NEW** | Root orientation: Path A vs Path B, where to start. |
| `docs/index.md` | Registry | Full descriptions + update rules per file. Read before editing/creating any file in the repo. |
| `docs/wiki.md` | Stable | MVP design decisions (universe, history, covariates, returns, horizons, walk-forward, metrics, ISS source). |
| `docs/devdocs.md` | Stable | Short experiment overview. Superseded operationally by `exp_plan.md`. |
| `docs/exp_plan.md` | Master plan | Statistical framing, Path A + Path B pipelines, stages 0–7 (config / inputs / goals / data sources / success criteria), results-per-stage spec. |
| `docs/project_brief.md` | Reference | Project brief / architecture proposal for a math-strong, non-trading audience. |
| `docs/probes/forts_iss_probes.md` | Historical record | Raw ISS API probe output (merged from former `1B_res.md` + `345_res.md` + `Colab_user_tasks.md`) behind the FORTS chain resolver. |
| `docs/runs_empty_futures.md` | Historical record | Raw log behind the 15m→10m intraday decision (former `runs/empty_futures.md`). |
| `path_a/basic_cells.ipynb` | Code library | Single source of truth for reusable pipeline code (30 cells: config loader, soft prefetcher, FORTS resolver, cache-only loaders incl. AlgoPack adapter, panel + covariates, Chronos input builder, walk-forward driver, metrics, baselines, plots, `run_stage`). |
| `path_a/runner.ipynb` | Universal runner | Mounts Drive → sources `basic_cells.ipynb` → reads one config → `run_stage(cfg_path)`. Switch stages by editing one cell. |
| `path_a/configs/phase_b_{multivariate,univariate}.yaml` | **Written, not run (2026-09-17)** | Phase B gate configs — identical except `group_mode`. See entry 16 below. |
| `path_a/scratchpads/_TEMPLATE.md` | Template | Template for future phase running notes. |
| `path_a/scratchpads/phase_b_scratch_pad.md` | **Pending** | Phase B combined scratchpad (both arms + McNemar result + gate decision). |
| `path_a/archive/` | **NEW (2026-09-17)** | Concluded/superseded material, kept for reference — not read by active code. `legacy_notebooks/` (`moex_chronos2_pipeline.ipynb`, `Chronos2_Roma.ipynb`), `concluded_stages/` (all `stage_0`–`stage_7` configs/scratchpads — run output stays live at `runs/`). See `archive/README.md`. |
| `algo_data/` | **NEW (2026-09-17)** | MOEX AlgoPack extraction pipeline, sibling to `path_a/`/`path_b/`. Feeds `path_a` via `load_from_algopack`. See `algo_data/docs/usage.md`. |
| `path_b/` | Path B | AutoGluon fine-tuning; see `path_b/README.md` and `path_b/current_state.md`. |
| `runs/stage_0_smoke/` | **Populated (2026-06-12)**, concluded | First real run output: config snapshot, metrics{,_aggregate,_baselines}.csv, summary.json, plots/, output_002.md log. Config archived; output stays live here. |
| `runs/stage_2b_60m_ctx600/` | **Populated (2026-09)**, concluded | Stage 2b result — clean negative (DA≈0.485, 0/48 significant), triggered the project pivot. Config archived; output stays live here. |
| `runs/` | Output root | Namespace: `runs/<stage_id>/{config.yaml, preds/, metrics.csv, metrics_aggregate.csv, metrics_baselines.csv, summary.json, plots/}`. |

## What changed this session

1. **Framework**: introduced single-source-of-truth split — `basic_cells.ipynb` (code) + `runner.ipynb` (driver) + `configs/*.yaml` (parameters) + `scratchpads/*.md` (notes) + `exp_plan.md` (plan). Rules written into `CLAUDE.md`.
2. **Statistical framing**: every stage reports DA + binomial p + Wilson 95% CI + BH-corrected q across (ticker × horizon) cells, Pearson/Spearman, amplitude calibration |pred|/|true|, q10–q90 coverage. Baselines (B0 zero / B1 last / B2 mom5 / B3 AR(1)) computed on the same windows.
3. **Primary horizons**: h ∈ {2, 3, 5} (per user). h=1 logged as companion only.
4. **Soft prefetcher**: rate-limited (≥0.25 s/req), exp-backoff retry on 429/5xx, idempotent (skips cached files), multi-stage manifest (union across all 8 stage configs). Cache target: Drive (`MyDrive/moex_cache/`).
5. **Cache-only experiments**: `load_cached(...)` raises `CacheMiss` unless `allow_api_fallback=True`. Flip on for live forecasting only.
6. **Universal runner**: one notebook drives every stage. Two Colab sessions can run different stages in parallel — cache is shared, outputs namespaced by `stage_id`.
7. **Walk-forward driver**: looping `predict_df`, checkpoints `preds_partial.parquet` every 25 windows.
8. **CLAUDE.md slimmed (2026-05-16)**: verbose per-file descriptions moved to `index.md`; CLAUDE.md INDEX is now one-liners. Hard rule added: read `index.md` before editing/creating any repo file.
9. **Price-level covariates queued (2026-05-16)**: design question recorded — Brent and USD/RUB *levels* (not just returns) carry regime info Chronos cannot recover from short-context returns. Recorded in wiki §3 (open extension) and added as Stage 5 sub-run **`5e: full + price_levels`** in `exp_plan.md` (encoding: `log(price)` and/or `*_z252` rolling-z, never raw price). Depends on FORTS resolver landing first.
10. **FORTS resolver scoped (2026-05-16)**: deferred to a dedicated session. Concrete 7-step plan written into `exp_plan.md` §5 (contract code generator, active-range from `MATDATE`, per-contract pulls, inside-contract returns, validation rule). No implementation yet — would risk silently corrupting the panel without live ISS validation.
11. **FORTS resolver landed (2026-05-19)**: ISS probes confirmed (a) `ASSETCODE` carries the root, (b) guess-and-probe over `{root}{letter}{year_digit}` finds every contract in 2021–2026 (120/120 hit), (c) candles endpoint has no `OPENPOSITION` (volume used for front-month selection), (d) 60m caps at 500 rows/page (paginated in existing `_iss_candles`), (e) ~~15m FORTS unavailable — resolver fetches 60m and ffills onto 15m grid~~ **[corrected 2026-06-10: ISS has no 15m candle for *any* market — the whole intraday stage moved to 10m, which FORTS serves natively; no 60m fallback. See session entry 12.]** Section 4b added to `basic_cells.ipynb` (`FORTS_LETTER_MAP`, `_enumerate_contracts`, `_resolve_futures_chain`). `build_prefetch_manifest` / `load_stage_inputs` / `build_covariate_panel` patched. All 8 stage configs flipped to `futures_proxies: [BR, Si, GD]`. ISS validation evidence in `1B_res.md` and `345_res.md`; per-task probe spec in `Colab_user_tasks.md`.
12. **Intraday stage moved 15m → 10m (2026-06-10)**: the first bulk prefetch returned *all* shares + indexes empty at interval=15 (`runs/empty_futures.md` lines 162–177). Root cause: **ISS has no 15-minute candle** — valid candle codes are `1, 10, 60, 24, 7, 31, 4` (verified against the global ISS `durations` table and per-market `candleborders` for shares/index/FORTS). Not a free-tier limit; AlgoPack (paid) uses the same set + fixed 5-min SuperCandles, no 15m either. Resolution: replaced the whole 15m intraday stage with **10m** (finest native bar, served for shares/indexes/FORTS back to 2011). Edits: `basic_cells.ipynb` — `load_config` assert now `(10, 60, 24)`; dropped the `60 if interval==15` FORTS fallback in `build_prefetch_manifest` + `_resolve_futures_chain` (FORTS serves 10m natively); updated §4b notes. `configs/stage_3_15m.yaml` → `configs/stage_3_10m.yaml` (`stage_id` `stage_3b_10m_ctx1000`, `interval: 10`). Docs synced: `wiki.md`, `exp_plan.md`, `devdocs.md`, `index.md`. Bar-based knobs (ctx grid, horizons, shift) unchanged. **Stale 10m FORTS cache from before this fix may not exist yet** — next prefetch will fill it. Historical chat/log files (`chat.md`, `gp.md`, `answers.md`, `pr*.md`, `Colab_user_tasks.md`, `runs/empty_futures.md`) left as-is (records, not specs).

13. **Stage 0 smoke PASSED + pipeline hardening (2026-06-12)**: first real `run_stage` execution.
    - **Bug found & fixed (run 001 → 002)**: `context_len: 250` exceeded the 2024-H1 daily panel (only 127 business days) → `walk_forward_anchors` produced 0 windows → `per_cell_metrics` crashed on an empty preds frame (`KeyError: 'id'`). Fix: `configs/stage_0_smoke.yaml` `context_len 250→60` (→ 40 windows). Hardened `per_cell_metrics` to return an empty frame when preds is empty/column-less (graceful 0-window exit instead of crash).
    - **Negative cache for ISS empties** (`basic_cells.ipynb` §4): the FORTS manifest enumerates every candidate contract (`_enumerate_contracts` → BR×12 letters × ~8 years, etc.); most don't overlap the window and ISS returns empty. Old `prefetch_one` printed `EMPTY` but wrote nothing → ~50 dead contracts re-queried every run. Now genuine empties are written as a zero-row parquet (negative-cache marker) so each empty key hits ISS at most once. To avoid poisoning the cache on a transient outage, `_iss_candles` now **raises** on transport failure / exhausted retries (also fixed a latent fall-through that called `.json()` on a 5xx response); only true 200-empties get cached.
    - **Source-transparent prefetch logging**: `prefetch_one` prints exactly one aligned line per key — `CACHE` / `CACHE-NEG` / `ISS` / `ISS-EMPTY` / `FAIL` — with the full parquet path + row count, so a run log shows whether ISS was touched and where data came from.
    - **Warning cleanup**: guarded Pearson/Spearman against constant input (`np.std==0`) — the `zero` baseline's all-zero vector was spamming `RuntimeWarning: invalid value encountered in divide` + `ConstantInputWarning`. Result unchanged (NaN), just no log noise.
    - **Results** (`runs/stage_0_smoke/summary.json`, primary h∈{2,3,5}): 40 windows, `mean_da 0.478`, `median_da 0.475`, `mean_pearson 0.042`, `coverage 0.764`, **0/48 cells significant** at BH-0.05. Amplitude ratio ~0.20–0.30 (forecasts shrink toward zero). All within the [0.40,0.60] sanity band — exactly a coin-flip, which is correct for a 127-day daily smoke with no statistical claim. **Pipeline validated; no edge expected or found at this scale.**
    - Committed `2b1523a`, pushed to `origin/main`.

14. **Project pivot + `algo_data/` integration (2026-09-17)**: Stage 2b (60m, 12 hand-picked
    tickers, 500 windows) completed and returned a clean negative result (DA≈0.485, 0/48
    BH-significant cells, Pearson≈0 — see `runs/stage_2b_60m_ctx600/summary.json`). Project
    goals pivoted: (1) gate — does multivariate grouping beat univariate forecasting at all,
    on a large liquid universe; (2) if the gate passes, systematically screen many series for
    lead-lag dependencies (discovery/confirmation split, no leakage) rather than hand-picking
    pairs; (3) stretch — toy backtest, explicitly educational framing. Full plan in
    `tmp/plans/` (local, not committed).
    - **`algo_data/` discovered**: a colleague-built, already-tested MOEX AlgoPack extraction
      pipeline (own `.claude/CLAUDE.md`, 40+ offline tests, live-verified paid API key) — richer
      than plain ISS (candles + tradestats/orderstats/obstats/hi2/futoi). Adopted as a third
      top-level component (`algo_data/`, sibling to `path_a/`/`path_b/`).
    - **Equity universe selection** (`algo_data/src/algopack_pipeline.py`): added
      `rank_equity_universe()`/`save_equity_universe()` — filters TQBR shares to real equities
      (`INSTRID == "EQIN"`, excludes ETFs/funds), checks history length/missingness per
      candidate, ranks survivors by turnover, full audit trail (every candidate + status, not
      just survivors). Run 2026-09-17: 506 candidates → 80 selected
      (`algo_data/data/universe/equity_universe.yaml`, gitignored). 5 new offline tests
      (`algo_data/tests/test_universe.py`); `algo_data/config.md`'s `tickers.shares` **not yet**
      updated to use the new list (still the original 10-ticker panel) — pending.
    - **`path_a` ingestion adapter** (`basic_cells.ipynb` §5, cell 13): `load_from_algopack(processed_path, tickers)`
      reshapes `algo_data`'s long-format Parquet (`ticker, timestamp, ...`, tz-aware MSK) into
      the same `{ticker: df}` shape the existing ISS-cache path produces (`timestamp`→`begin`,
      tz stripped). `load_stage_inputs` branches on `cfg["data_source"] == "algopack"` (new
      optional config key; default unset = unchanged ISS-cache behavior — all 8 existing stage
      configs unaffected, confirmed by regression test). Downstream (`build_price_panel`,
      `assemble_panels`, everything after) needs zero changes — same shape in, same shape out.
    - **Coverage guard** (`basic_cells.ipynb` §6, cell 15): `build_price_panel` gained
      `min_ticker_coverage` (default 0.98, config key `min_ticker_coverage`). Measures each
      ticker's **raw, pre-ffill** bar coverage of the union calendar (coverage must be computed
      before `to_regular_series`'s `.asfreq().ffill()`, which otherwise makes a 70%-complete
      series look 100% complete on its own grid — caught by a synthetic-data test during
      implementation) and drops/logs tickers below threshold before the `dropna(how="any")`
      inner join, plus a shrinkage diagnostic (`union_days` vs `joined_days`). Addresses the
      "one illiquid ticker silently shrinks every other ticker's date range" risk at 50-100
      ticker scale. Verified via a synthetic 3-ticker test (one deliberately gappy) plus a
      regression test confirming the existing ISS-cache path is byte-for-byte unaffected.
    - All changes verified: notebook JSON valid, every code cell's Python syntax checked, both
      new and existing (`assemble_panels`) paths smoke-tested against synthetic data before
      relying on them for real config edits.

15. **Numbered-stage scheme retired (2026-09-17)**: following the pivot (entry 14), the
    remaining `stage_1`/`stage_3`–`stage_7` configs and `stage_1_scratch_pad.md` are archived
    to `path_a/archive/concluded_stages/` — see `archive/README.md` for per-file disposition
    (stage_1 was mid-flight, not concluded normally; stage_3–7 were never run). `path_a/configs/`
    is now empty; `runner.ipynb`'s `CONFIG_PATH` set to `None` with an explanatory comment.
    Going forward, configs are named `phase_<letter>_<name>.yaml` per the Phase A–D structure
    (`phase_b_multivariate.yaml` / `phase_b_univariate.yaml` next, when Phase B starts — not
    written yet). The table below is kept as a **historical record** of the old scheme, not a
    current plan.

16. **Phase A real data pull + Phase B implementation (2026-09-17)**:
    - **AlgoPack pull executed**: `algo_data/config.md` scoped to 22 tickers (sector-stratified
      subsample of `equity_universe.yaml`'s 80, see `algo_data/current_state.md`),
      `datasets: [candles]`, `candles.intervals: [1d]`. Run: 3879 requests, ~11 min, exit 0.
      **X5 and RAGR removed from the config entirely** — both recent MOEX redomiciliations with
      zero candle history anywhere in 2020-2024 (confirmed via 60/60 empty month-chunks each);
      `equity_universe.yaml`'s ranker only checks recent (240+ day) history so it selected them
      without catching this. Final panel: 22 tickers pulled, `build_price_panel`'s coverage
      guard (`min_ticker_coverage`) drops 6 more at load time (LENT, MDMG, OZON, SMLT, VKCO,
      YDEX — same root cause, less extreme; YDEX has only 115 bars) — verified end-to-end
      against the real Parquet output: **16 tickers, 1302-day panel, zero gap loss** at
      threshold 0.9. Accepted as-is (below the plan's ~20-25 ticker target) rather than
      relaxing the threshold or hunting replacements.
    - **`predict_df` batching resolved by reading source, not a live Colab test**: installed
      `chronos-forecasting` locally and read `chronos/chronos2/pipeline.py` directly.
      `predict_df`/`predict` take `cross_learning: bool = False` — this, not `id_column`
      grouping, is the actual joint-vs-independent switch (`cross_learning=True` zeroes each
      task's `group_id` so the batch attends to itself; `False` leaves them independent even
      within one batched call). **Confirmed prior Path A stages (0, 1, 2) never set this
      flag** — Stage 2b's negative result was already run in independent/univariate mode
      despite batching all tickers into one `id_column`-keyed call.
    - **`group_mode` implemented**: `basic_cells.ipynb` cell 5 (`load_config`) validates
      `group_mode ∈ {univariate, multivariate}` (default `univariate`) and
      `algopack_processed_path` presence when `data_source: algopack`; cell 9
      (`build_prefetch_manifest`) skips queuing shares from ISS when `data_source: algopack`
      (previously wasted ISS requests in that mode); cell 19 (`run_walk_forward`) threads
      `group_mode` to `predict_df(..., cross_learning=(group_mode=="multivariate"))`; cell 28
      (`run_stage`) records `group_mode` in `summary.json`. Verified with a mock-`predict_df`
      test (three cases: univariate/multivariate/unset-default) that the kwarg arrives
      correctly — no GPU/Colab needed for this check.
    - **Phase B configs written**: `path_a/configs/phase_b_multivariate.yaml` /
      `phase_b_univariate.yaml` — identical except `group_mode`, 22 tickers configured (~16
      survive), `context_len=250` (matches Stage 1c), `covariates: full`, `data_source:
      algopack`. Combined scratchpad `path_a/scratchpads/phase_b_scratch_pad.md` (paired-arm
      structure, not the per-stage template, since the gate's McNemar test needs both arms
      read together).

17. **Phase B run + GATE FAILED (2026-09-17)**: both arms run to completion, locally, on a
    dedicated Python 3.12 venv (`path_a/.venv` — CPU, no GPU needed; Chronos-2 is a ~150M-param
    T5-base-sized model, genuinely light for zero-shot inference at this scale — real total
    time was ~15 min per arm including a one-time ISS prefetch, not the "must use Colab GPU"
    assumption this session started with). 400 windows, 16 tickers, both arms.
    - **Two real bugs found and fixed along the way** (both would have silently produced wrong
      or crashed results, not just been slow): (1) `build_covariate_panel` was building
      volume-covariate columns from all 22 *configured* tickers instead of the 16 that
      actually survived `build_price_panel`'s coverage guard — one short-history ticker's
      ragged data collapsed the whole covariate panel via `dropna`, silently producing "0
      windows". (2) `run_stage` passed the original 22-ticker config list into
      `run_walk_forward` instead of the survivors, causing a `KeyError` once panels were
      correctly filtered. Both fixed in `basic_cells.ipynb` (`assemble_panels`, `run_stage`);
      see `path_a/scratchpads/phase_b_scratch_pad.md`'s run log for full detail.
    - **Gate test implemented**: `mcnemar_gate_test()`, new `basic_cells.ipynb` §13 — paired
      exact binomial McNemar test per (ticker, horizon) cell (recomputed from `preds.parquet`
      + `ret_panel`, since per-window hit/miss isn't itself persisted), BH-corrected across
      the 64-cell family, matching the existing BH pattern in `per_cell_metrics`.
    - **Result**: aggregate ΔDA (multivariate − univariate) ≈ **-0.00035** (not positive),
      **0/64 cells BH-significant**. Both arms independently landed at chance-level DA
      (~0.484, matching Stage 2b's original 0.485) and are nearly indistinguishable from each
      other on every metric. **Clean fail, not borderline** — per the pre-registered stopping
      rule (decided *before* either run, see scratchpad), this is decisive: no context_len
      sweep, no retry to chase significance.
    - **Gate FAILED → Phase C (lead-lag screening) is NOT funded, per the plan's own gating
      rule.** Phase D (stretch backtest) was gated on B *or* C passing — B failed and C is not
      funded, so Phase D is also not funded. This is the second independent negative result
      (after Stage 2b) at chance-level predictability for MOEX daily returns via zero-shot
      Chronos-2, with or without cross-series attention, at this universe/context_len scope.

18. **Phase C designed and scaffolded (2026-09-17), user explicitly chose to proceed despite
    Phase B's formal gate failing.** Reasoning: Phase B tested one specific question (does a
    fixed 16-ticker basket benefit from joint forecasting) and its per-ticker breakdown
    showed no individual signal anywhere in that sample (best cell DA=0.52, p=0.227
    uncorrected) — evidence against that sample, not against "does any pair among a much
    wider universe show lead-lag structure," which is a genuinely different question Phase C
    was always meant to test. Full design in `path_a/scratchpads/phase_c_scratch_pad.md`
    (pre-registered before any run) and local plan rev. 3.
    - **C1**: `algo_data/config.md` `tickers.shares` widened 22→80 (full
      `equity_universe.yaml`). Offline test suite re-passed (47/47). Pull not yet executed —
      user runs manually (established Phase B pattern: assistant writes code/configs, user
      runs, assistant debugs on report).
    - **C2**: new `basic_cells.ipynb` §14 — `pairwise_lagged_xcorr()` (Pearson r per ticker
      pair × lag 1-5 × direction, `scipy.stats.pearsonr`) + `select_pair_shortlist()` (BH
      q<0.05, top-20 cap by |r|). BH snippet copied verbatim from `mcnemar_gate_test()` (§13)
      rather than reimplemented — verified identical to a manual textbook BH computation on a
      toy p-array, and verified end-to-end on a synthetic pair (`b = a.shift(2) + noise`
      among 8 noise tickers): correctly recovered lag=2, correct leader, and was the sole
      survivor out of 450 tests after BH correction.
    - **C3**: new `configs/phase_c_leadlag_confirm.yaml` — confirmation window
      2023-07-01→2024-12-30 (discovery window 2020-01-03→2023-06-30, verified zero date
      overlap, ~70/30 split as pre-registered). `tickers:` left as an empty-list placeholder
      pending C2's actual shortlist. Reuses `run_stage` unchanged.
    - **Corrected a stale known-gap note**: "`metric_window` parsed but not enforced" was
      simply wrong — grepped `basic_cells.ipynb`, zero references anywhere, the feature
      doesn't exist. Confirmation's own `date_from`/`date_till` serves as the leakage guard
      directly instead; no new mechanism built.
    - **User pushed back usefully on scope** during design discussion: questioned whether one
      run is enough to trust a negative result (answer: yes for the narrow claim Phase B
      actually tested, no for a universe-wide claim — which is exactly why Phase C exists);
      raised DA as a possibly-wrong metric (valid — DA's binary sign threshold can miss real
      quantile/calibration skill that Pearson or pinball loss would catch; queued as a
      near-zero-cost add-on, not yet implemented); pushed for 1h bars specifically (was the
      original intent) — sizing showed this is materially cheaper than first estimated
      (AlgoPack's request count is driven by month-chunks, not bar count, so a 1h pull costs
      roughly the same as the 80-ticker daily pull, not ~9x) and fits a 1-2 day compute
      budget; user separately raised that more lookback history could dilute predictions with
      noise, so `context_len` stays at 250 *bars* (not scaled to preserve calendar-year
      lookback) when 1h work starts. Covariate ablation was discussed and explicitly declined
      for this phase. None of the 1h/metrics work has started yet — sequenced to run after
      Phase C's daily-frequency screen concludes.

19. **Phase C1 pull + C2 discovery run, with a real methodology bug caught and fixed
    (2026-09-17)**: user ran the 80-ticker AlgoPack pull (6039 requests, 24m11s) — 76/80
    tickers have any 2020-2024 data (X5, RAGR already known zero-history; CNRU, DOMRF newly
    found zero-history, not yet individually investigated). User then ran §14's discovery
    screen (`pairwise_lagged_xcorr`/`select_pair_shortlist`) against the discovery-window
    slice: 55/76 tickers survived `build_price_panel`'s 0.9 coverage guard, 876 days,
    14,850 (pair, lag, direction) tests.
    - **First run (unresidualized) found a real problem, not a real result**: 20
      BH-significant pairs, but 19/20 shared the exact same lag (3) across
      economically-unrelated ticker pairs — checked the panel-wide equal-weight market
      return's own autocorrelation and found lag-3 ≈0.16, which alone explains a cluster of
      same-lag false positives across pairs sharing exposure to that common factor. Spot
      residualizing one flagged pair (GAZP→IRKT) by hand confirmed the pattern: some pairs'
      correlation survived removing the market factor, most collapsed or weakened a lot.
    - **Fixed by adding market-factor residualization to `pairwise_lagged_xcorr`** (new
      `residualize_market=True` default): each ticker demeaned by the leave-one-out average
      of every OTHER ticker before lagged correlation is computed. Getting this right took
      two failed attempts worth recording: (a) a simple panel-wide mean (including the
      ticker itself) mechanically induces spurious negative cross-correlation purely from
      shared subtraction — verified exactly r=-1.0 with only 2 series; (b) a leave-two-out
      variant (excluding both tickers of the pair being tested) still leaked signal when the
      excluded pair was itself strongly correlated, on a small ~10-ticker synthetic test.
      Final leave-one-out version verified correct: negligible induced bias (~-0.02) and
      zero spurious BH-significant hits on a synthetic test matched to the REAL panel's
      ~55-ticker scale — the smaller synthetic panics used during earlier iterations were
      themselves misleading (an unrepresentative small-N regime, not a conservative check),
      a useful reminder that a synthetic verification test's scale matters, not just its
      presence.
    - **Re-ran discovery with the fix**: same 20 BH-significant pairs count, but now lags
      spread across 1–5 with no single-lag cluster, and only 2 of the original 20 pairs
      (GAZP-IRKT, AFLT-VTBR) persist — consistent with most of the original list having been
      the market-factor artifact. Full 20-pair table in
      `path_a/scratchpads/phase_c_scratch_pad.md`. Union of 18 tickers filled into
      `configs/phase_c_leadlag_confirm.yaml`'s `tickers:`; all 18 confirmed present with
      382-386/386 days coverage in the confirmation window (2023-07-01→2024-12-30) — no
      further coverage-guard drops expected.
    - **Confirmation (C3) is ready to run, not yet run.** User runs manually next.

20. **Phase C3 confirmation run + GATE FAILED (2026-09-17)**: user ran
    `run_stage("configs/phase_c_leadlag_confirm.yaml")` — 135 windows, 18 tickers.
    Basket-wide: chance-level DA (0.508), 0/72 BH-significant (ticker, horizon) cells, mean
    Pearson ≈ -0.037 — matches Phase B's earlier basket-wide null.
    - **Per-pair test (the actual pre-registered criterion)**: recomputed each of the 20
      discovery-shortlisted pairs' lagged correlation at its discovered lag, on
      confirmation-window returns (2023-07-04..2024-12-30, 390 days), same leave-one-out
      residualization as discovery, BH-corrected within this 20-pair confirmation family
      (not reusing discovery's p-values, per the pre-registered design). **0/20 pairs
      significant at q<0.05.** Best uncorrected p=0.007 (MTSS→UNAC) doesn't survive
      correction (p_bh=0.140). Several pairs' correlation sign flipped entirely out-of-sample
      (e.g. GMKN→MTLRP: discovery r=+0.20 → confirmation r=-0.008; PHOR→RASP: +0.21→-0.003).
      Full per-pair table in `path_a/scratchpads/phase_c_scratch_pad.md`.
    - **Gate FAILED.** The discovery/confirmation split worked exactly as designed: 20
      BH-significant discovery hits (surviving only after a real market-factor confound was
      caught and fixed, see entry 19) produced zero replications out-of-sample — direct
      evidence those hits were false discoveries from the ~15,000-test discovery family, not
      a case of "the search wasn't broad enough." This is the **third independent negative
      result** for zero-shot Chronos-2 on MOEX returns (Stage 2b, Phase B, Phase C), each
      testing a genuinely different hypothesis (single-basket univariate; basket-wide
      grouped-vs-independent; any-pair lead-lag with proper out-of-sample confirmation).
    - Per the pre-registered decision 5, this is treated as a complete, informative result —
      not a trigger to loosen the shortlist threshold or re-run discovery chasing
      significance.

21. **Fine-tuning question answered; pinball-loss backfill + 1h follow-on scaffolded
    (2026-09-17).** User asked how likely fine-tuning (Path B) is to change the negative
    results. Assessment: unlikely to help much — all three negative results converge on
    DA≈0.50/Pearson≈0 at daily resolution, consistent with daily MOEX returns being close to
    a random walk at this timescale, which is a property of the data, not something
    fine-tuning manufactures. Fine-tuning helps most when there's a specific idiosyncratic
    pattern a general model underweights; there's no evidence yet such a pattern exists.
    Recommended sequencing: don't decide on fine-tuning until after the two cheaper,
    already-planned follow-ons (1h frequency, better metrics) are tried — if either finds
    something, that's a much better-informed reason to fine-tune *toward* a located signal;
    if both come back null too, that further narrows the case for fine-tuning being useful
    here. User agreed, chose to proceed with both follow-ons.
    - **Pinball loss added (`basic_cells.ipynb` §15) and backfilled onto Phase B/C's
      already-saved `preds.parquet`** (no re-run needed — all three quantile columns were
      already persisted). Phase B: 0.00509 (multivariate) vs 0.00510 (univariate) — same
      "indistinguishable" pattern as every other metric. Phase C confirmation: 0.00639.
      Coverage (already computed, q10-q90 hit rate) is close to the 0.80 target in all three
      runs (0.79/0.79/0.75) — the quantile intervals are reasonably well-calibrated even
      though the median forecast has no directional skill; a more precise statement than
      "DA≈0.50" alone. Deliberately did NOT add a pinball-loss-vs-baseline comparison:
      `baseline_predictions` gives every baseline the same value across all three quantile
      columns (point forecasts), so that comparison would just be a rescaled MAE, not a
      real calibration test.
    - **1h follow-on scaffolded, not yet run.** `algo_data/config.md` `candles.intervals`
      widened to `[1d, 1h]` (`period` deliberately left at the full 2020-2024 range — it
      applies globally across every interval, so narrowing it would have silently
      truncated the already-processed, already-cited daily parquet). 24-month analysis
      window chosen (2023-01-02→2024-12-30, not the full 5 years) to keep cost down per the
      user's explicit request for a "shorter window" first look; ~70/30 discovery/
      confirmation split (365/156 trading days), verified zero overlap. `runner.ipynb` §2b's
      discovery driver refactored to be parameterized by interval/date range (was
      daily-only) — verified the refactor is a no-op for the daily case (exact same 20-pair
      shortlist reproduced). New confirmation config `configs/phase_c_leadlag_1h_confirm.yaml`
      with `tickers:` left as a placeholder pending the 1h discovery run's shortlist.

22. **Phase E idea captured (2026-09-17), not designed yet — queued for after the 1h
    follow-on concludes.** User's hypothesis: lead-lag dependencies may not be stationary
    across the whole sample (what every test so far assumed) but could occur in short
    bursts — real for a window, then gone — averaging out to "no signal" in a global test
    even if real, detectable structure exists locally. Not ruled out by any of the three
    negative results, since Stage 2b/Phase B/Phase C all used one correlation/DA number
    over the full window.
    - Goal stated explicitly as **detection only, not exploitation** — the user wants to
      show such bursts are catchable early, not build a trading rule. This simplifies the
      eventual design: no need for realistic transaction-cost/execution simulation, just
      rigorous out-of-sample proof that a burst can be flagged from data available at the
      time, not just seen in hindsight.
    - Flagged as materially harder than 1h/metrics, not a cheap add-on: (a) rolling-window
      correlation on short windows (e.g. 20-60 days) has few degrees of freedom and is
      prone to spurious high values by chance — a 20-day window needs |r|≈0.44 just to hit
      p<0.05 uncorrected; (b) testing (pair × lag × window-start-time) multiplies the
      already-large Phase C test family by orders of magnitude, demanding either much
      longer history or a stricter effect-size floor; (c) "detectable" must mean detectable
      causally (using only data up to time t), which needs its OWN discovery/confirmation
      split layered on top of the pair-level one already built for Phase C — proving a
      burst existed in hindsight is easy and not the actual claim; proving a rule could have
      flagged it in real time is the hard, valuable part.
    - Explicitly sequenced: finish the 1h follow-on (and its own discovery/confirmation
      result) before starting Phase E design. If 1h finds something, that's independent
      evidence worth chasing with burst detection; if it's null too, Phase E proceeds
      regardless (user wants it either way) but with one more prior data point about how
      much signal exists at daily/1h resolution in this universe.
    - Detailed research notebook: [`transient_dependency_research.md`](transient_dependency_research.md)
      collects candidate mechanisms, event/rolling/regime experiments, covariates, metrics,
      statistical safeguards, evidence levels, and a proposed Phase E sequence.
23. **Phase C 1h follow-on run + GATE FAILED (2026-09-17)**: user ran the widened
    `algo_data` pull (`[1d, 1h]`, 80 tickers, full 2020-2024 period, ~49min, 9630
    requests) — 76/80 tickers have 1h history (4 recent-IPO names lack it, expected).
    Discovery (`runner.ipynb` §2b, `DISCOVERY_INTERVAL=60`, window
    2023-01-02→2024-05-24): 16-ticker panel, **13 BH-significant (pair, lag, direction)
    tests** (q<0.05), lags spread 2-5 bars with no single-lag cluster — includes two
    same-issuer pairs (SBER↔SBERP, MTLR↔MTLRP) plus 8 cross-issuer pairs. Confirmation
    (`configs/phase_c_leadlag_1h_confirm.yaml`, window 2024-05-27→2024-12-30, same 16
    tickers, all survived the coverage filter): basket-wide chance-level (DA=0.494,
    0/16 BH-significant cells). **Per-pair test (the actual pre-registered criterion)**:
    recomputed each of the 13 hypotheses at its discovered lag on confirmation-window
    returns, same leave-one-out residualization, BH-corrected within this 13-test
    family (script: scratchpad, output copied to
    `path_a/runs/phase_c_leadlag_1h_confirm/per_pair_confirmation.csv`) — **0/13 pairs
    significant at q<0.05.** Largest survivor: SBER→VTBR r=0.059 uncorrected p=0.037,
    p_bh=0.38 (fails). Both same-issuer pairs also failed to replicate (r≈0.001-0.02).
    **Fourth independent negative result** (Stage 2b, Phase B, Phase C daily, now Phase
    C 1h) — two frequencies and two test designs now agree: no detectable structure in
    zero-shot Chronos-2 on this universe. Full tables in
    `path_a/scratchpads/phase_c_1h_scratch_pad.md`. This closes out all currently
    planned Path A work (entry 21's "1 and 2" — writeup + 1h/metrics follow-ons); next
    is designing Phase E (entry 22), which now has a fourth full-sample null as prior
    evidence for why a stationarity assumption is worth questioning.
24. **Univariate-with-covariates companion arm + AutoGluon `feature_importance()` scoped
    and deferred (2026-09-17)**: user asked whether Chronos's covariate channel alone
    (no cross-ticker attention) picks up any of what the lead-lag screen found, and
    separately whether AutoGluon's `feature_importance()` (verified this requires a
    *fitted* AutoGluon `TimeSeriesPredictor` — not available in the zero-shot
    `chronos-forecasting` package used throughout Path A, which has no covariate-ablation
    API of its own) was worth using. Investigated `path_b/` (a substantial pre-existing
    AutoGluon fine-tuning module, last touched 2026-06-14: Colab-GPU-only, daily-validated,
    60m/10m broken on an intraday index bug) and confirmed `feature_importance()` would
    require standing that module back up, not a quick add-on — user chose to defer it and
    stick with tools already in hand.
    - Ran `configs/phase_c_leadlag_1h_confirm_univariate.yaml` (identical to the
      multivariate confirm config except `group_mode: univariate`, same 16 tickers/dates/
      covariates). Result: chance-level, statistically indistinguishable from multivariate
      (DA 0.4918 vs 0.4936, mean Pearson -0.0282 vs -0.0230, 0/16 significant cells in
      both arms). Mean per-cell DA diff across 64 cells: -0.0004. Two cells favoring
      univariate (SBER/SBERP h=1, +0.03-0.04 DA uncorrected) are within the noise scale
      expected from 64 uncorrected comparisons, not evidence of a real effect.
    - Slightly stronger null than Phase B's original univariate result: Phase B's 16
      tickers were a sector-stratified sample chosen for coverage; this arm reused the
      same 16 tickers Phase C's own screen flagged as correlated, so it's a direct test of
      whether covariates capture any fragment of what drove that correlation — they don't.
    - Full writeup in `path_a/scratchpads/phase_c_1h_scratch_pad.md` ("Companion arm —
      univariate with covariates" section).
25. **Phase E designed, implemented, and run — NULL RESULT (2026-09-17)**: after
    reviewing the user's `docs/transient_dependency_research.md` (drafted with another
    reasoning model) together, agreed scope for this pass: E1 (synthetic positive-control
    validation) then E2 (event-conditioned leader/follower MVP), deferring experiments
    E-H (dynamic networks, change-point-first, nonlinear/Hawkes methods, natural
    experiments), 10-minute-or-finer resolution, and most mechanism-specific covariates
    not already in `algo_data`.
    - **Event-count floor derived via binomial power calculation** (not a guessed round
      number): targeting a 65% same-direction follower-response rate vs. the 50%
      no-relationship null (80% power, α=0.05) requires n≥85 qualifying leader-events per
      candidate pair. Checked against real data before locking in: a one-sided 2σ
      threshold on SBER's 1h discovery window gives ~72 expected events — close to but
      under the floor, meaning the design would only be well-powered for liquid tickers.
      In the actual run, 100% of the 11024 candidates cleared the floor, so this was not
      a binding constraint in practice.
    - **Built in `basic_cells.ipynb` §16**: `residualize_market_factor` (extracted from
      §14's `pairwise_lagged_xcorr` for reuse — one implementation, not two),
      `detect_leader_events` (causal, trailing-window-only), `event_conditioned_response`,
      `block_permute_panel`, `scan_pair_family`, `bh_correct`, plus E1's synthetic-panel
      generator/injector and both validation tests. E1's assertions run automatically
      every time the notebook is sourced — E2's functions are structurally unreachable
      without E1 passing first, not just conventionally gated.
    - **E1 (synthetic validation) — both tests pass.** Injected-burst power test (20
      trials, 76-ticker synthetic panels matching real scale): `detection_rate=1.0`,
      `mean_abs_frac_error=0.031`. Null false-alert-rate test (20 trials × 380 pairs, pure
      null): 0/7600 BH-significant hits. One real bug caught and fixed during development:
      an early `inject_burst` used a non-causal event definition that disagreed with what
      the real detector scans for, diluting measured detection rate to ~20% and making a
      working detector look broken — fixed by making injection use the exact same
      causal/residualized event definition as detection.
    - **E2 (event-conditioned MVP) — run on real 1h data, NULL at discovery.**
      `runner.ipynb` §2c/§2d (pandas-only, no Chronos). Same discovery/confirmation date
      split as Phase C's 1h follow-on, but a fresh candidate pool (every ordered pair
      among the 53/76 tickers surviving coverage, not Phase C's shortlist — different
      mechanism). 11024 candidate (leader, follower, lag) tests, **0/11024
      BH-significant at q<0.05**. Confirmation stage not reached (nothing to confirm) —
      itself the complete pre-registered result, not a partial one.
    - **Fifth independent negative result** (Stage 2b, Phase B, Phase C daily, Phase C
      1h, now Phase E) — and the first to test a genuinely different hypothesis shape
      (event-conditioned causal detection vs. full-sample aggregate correlation/DA).
      Full writeup: `path_a/scratchpads/phase_e_scratch_pad.md`.

## Stages (Path A) — retired scheme, historical record only (see entry 15)

| Stage | Interval | Config | What it answers |
|-------|----------|--------|-----------------|
| 0 smoke ✅    | 1d  | `archive/concluded_stages/stage_0_smoke.yaml` | Pipeline + cache + output schema end-to-end. No claim. **PASSED 2026-06-12** (40 windows, DA~0.48, ctx 250→60). |
| 1 daily (superseded) | 1d  | `archive/concluded_stages/stage_1_daily.yaml` | Full daily study, context grid {64,128,250,500}. Only 1c (ctx250) ran before the pivot retired this stage; 1a/1b/1d never run. |
| 2 60m ✅      | 60m | `archive/concluded_stages/stage_2_60m.yaml` | Intraday signal at 60m, context grid {300,600,1000}. **Concluded**: clean negative result (DA≈0.485, 0/48 significant) — triggered the project pivot (session entry 14). |
| 3 10m (never run) | 10m | `archive/concluded_stages/stage_3_10m.yaml` | High-frequency test, context grid {500,1000,1500}. (10m = finest native ISS intraday bar; no 15m exists.) |
| 4 sector (never run) | best | `archive/concluded_stages/stage_4_sector.yaml` | Does intra-sector group attention beat mixed grouping? |
| 5 covariates (never run) | best | `archive/concluded_stages/stage_5_covariates.yaml` | Ablation: none / calendar_only / market_only / full. |
| 6 stability (never run) | best | `archive/concluded_stages/stage_6_stability.yaml` | Regime sub-windows (2021-H1..2026-YTD). |
| 7 hold-out (never run) | best | `archive/concluded_stages/stage_7_holdout.yaml` | Headline table. Metric window locked to 2025-11-01..2026-04-30. |

## Wiki decisions (still authoritative)

- Universe: 12 blue chips (SBER, GAZP, LKOH, ROSN, NVTK, TATN, GMKN, PLZL, MAGN, NLMK, MOEX, VTBR).
- Covariates MVP: IMOEX/MOEXOG/MOEXMM/MOEXFN/RGBI returns, Brent / USD-RUB / Gold returns, per-ticker dlog-volume, calendar (hour/dow/dom/month, +session_open intraday). Leakage rule preserved.
- Target: log-returns, close-to-close.
- Data: MOEX ISS direct.

## Chronos-2 hard limits (asserted in `load_config`)

- Max context: 8192 — every configured `context_len` fits.
- Max horizon: 1024 — H=5 trivially fine.
- Multivariate via `id_column`; past covariates as extra context columns; future covariates via `future_df` (calendar only).
- T4: fp16 (Turing emulates bf16); Ampere+: bf16.

## Known gaps / open items

- **Price-level covariates (Stage 5e)** still queued. Encoding rule already decided (log + optional rolling-z 252; never raw price). The resolver now exposes the stitched `close` series (`{name}_close` regridded), so adding `log(close)` / rolling-z as past covariates is a localised patch in `build_covariate_panel`. Not wired yet — done when Stage 5 sub-runs are scheduled.
- **10m availability**: ISS has no 15m candle at all (root cause of the original Stage 3 all-empty prefetch). Switched to 10m, which is served for shares / indexes / FORTS back to 2011-12-08. Stage 3's 2024-05-01 start is now a deliberate choice (aligned with the 60m study), not a depth limit — widen freely if more windows are wanted.
- ~~`metric_window` not enforced~~ — **corrected 2026-09-17**: this note was stale/wrong.
  Grepped the current `basic_cells.ipynb`: zero references to `metric_window` anywhere; the
  feature was never carried through the Phase A–D rewrite, there's nothing to enforce.
  Phase C's confirmation-window leakage guard uses the confirmation config's own
  `date_from`/`date_till` directly instead (see session entry 18) — no new mechanism needed.
- **Path B (AutoGluon fine-tune)** is sketched in `exp_plan.md` §6 and in the legacy `path_a/archive/legacy_notebooks/moex_chronos2_pipeline.ipynb` §7 but not yet wired into the runner. Queue: after Stage 7.
- **Batching at 10m × ≥400 windows × 12 series**: not stress-tested. T4 should hold; `preds_partial.parquet` checkpoint every 25 windows is the recovery path.
- **CatBoost baseline** (wiki §7) is not in B0–B3. Optional Path B-era addition.
- ~~`algo_data/config.md`'s `tickers.shares` still holds the original 10-ticker panel~~ —
  **resolved 2026-09-17**: expanded to a 22-ticker sector-stratified subsample, real pull
  executed (see session entry 16).
- ~~Full AlgoPack historical run not yet executed~~ — **resolved 2026-09-17**: executed
  locally (22 tickers, candles/1d, 2020-2024). Colab↔`apim.moex.com` reachability is still
  untested, but moot for now — local runs work fine and don't need Colab (session entry 17).

## Suggested next session

**All currently-planned work is concluded — five independent negative results**
(Stage 2b, Phase B, Phase C daily, Phase C 1h follow-on, Phase E; session entries
14/17/18-20/23/25). Phase E specifically tested the user's "bursty, non-stationary
dependency" hypothesis with a validated (E1-checked) causal event-conditioned detector on
real 1h data — 0/11024 candidates significant at discovery, confirmation not reached.

Immediate open decision: **what's next**, now that both the "does structure exist in
aggregate" question (Stage 2b/B/C) and the "does it exist in short causal bursts" question
(Phase E) have been tested and come back null. Options, not yet decided:
- Write up all five negative results as the project's deliverable (entry 21's "1" from "I
  definitely want 1 and 2 to take" — still not started as its own artifact).
- Design a specific, justified Phase E variant with its own fresh pre-registration
  (different `threshold_std`, regime-conditioning, volume-conditioning, or finer
  resolution) — per `phase_e_scratch_pad.md`'s Interpretation section, none of these
  should be tried as an immediate retry of the same test with a loosened knob; each needs
  its own justification, not just "try again."
- Revisit the fine-tuning (Path B) decision — five negative results across two frequencies,
  three test designs (basket gate, pairwise lead-lag, event-conditioned burst), now rule
  out "wrong metric," "wrong frequency," "too narrow a ticker sample," and "wrong
  hypothesis shape (aggregate vs. bursty)" as explanations, which further strengthens the
  case against prioritizing fine-tuning (entry 21's skeptical assessment) but the decision
  itself still hasn't been formally revisited.

**Carryover items** (unchanged, see Known gaps): price-level covariates, Path B fine-tune
wiring.
