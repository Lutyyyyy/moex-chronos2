# Current State — MOEX × Chronos-2 Project

Snapshot for the next Claude instance. Picks up after the "full-scale experiment framework" session (2026-05-15) and the CLAUDE.md slimming pass (2026-05-16). The single-window prototype is done; the project is now organised around a stage-driven framework backed by YAML configs and a universal runner.

## Files in repo

| File / dir | Status | Purpose |
|------------|--------|---------|
| `.claude/CLAUDE.md` | **Slimmed** | Project rules + compact INDEX (one-liner per file). Always preloaded. Read this first. |
| `index.md` | **NEW** | Full descriptions + update rules per file (the verbose form previously inlined in CLAUDE.md). Read before editing/creating any file in the repo. |
| `wiki.md` | Stable | MVP design decisions (universe, history, covariates, returns, horizons, walk-forward, metrics, ISS source). |
| `answers.md` | Stable | Raw wiki answers. |
| `devdocs.md` | Stable | Short experiment overview. Superseded operationally by `exp_plan.md`. |
| `exp_plan.md` | **NEW — master plan** | Statistical framing, Path A + Path B pipelines, stages 0–7 (config / inputs / goals / data sources / success criteria), results-per-stage spec. |
| `basic_cells.ipynb` | **NEW — code library** | Single source of truth for reusable pipeline code (27 cells: config loader, soft prefetcher, cache-only loaders, panel + covariates, Chronos input builder, walk-forward driver, metrics, baselines, plots, `run_stage`). |
| `runner.ipynb` | **NEW — universal runner** | Mounts Drive → sources `basic_cells.ipynb` → reads one config → `run_stage(cfg_path)`. Switch stages by editing one cell. |
| `configs/stage_{0..7}.yaml` | **NEW** | 8 per-stage configs: smoke, daily, 60m, 10m, sector, covariate ablation, time-stability, hold-out. |
| `scratchpads/_TEMPLATE.md` | **NEW** | Template for per-stage running notes. |
| `scratchpads/stage_0_scratch_pad.md` | **NEW** | Placeholder filled at first run. |
| `runs/` | Empty | Output namespace: `runs/<stage_id>/{config.yaml, preds/, metrics.csv, metrics_aggregate.csv, metrics_baselines.csv, summary.json, plots/}`. |
| `moex_chronos2_pipeline.ipynb` | **Legacy reference** | Original prototype. Don't develop new logic here — fold useful bits into `basic_cells.ipynb`. |
| `Chronos2_Roma.ipynb` | Legacy | Earlier univariate experiments + Kronos comparison. |

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

## Stages (Path A)

| Stage | Interval | Config | What it answers |
|-------|----------|--------|-----------------|
| 0 smoke      | 1d  | `stage_0_smoke.yaml`       | Pipeline + cache + output schema end-to-end. No claim. |
| 1 daily      | 1d  | `stage_1_daily.yaml`       | Full daily study, context grid {64,128,250,500}. |
| 2 60m        | 60m | `stage_2_60m.yaml`         | Intraday signal at 60m, context grid {300,600,1000}. |
| 3 10m        | 10m | `stage_3_10m.yaml`         | High-frequency test, context grid {500,1000,1500}. Validates "first 2-3 bars predictive" effect from prototype. (10m = finest native ISS intraday bar; no 15m exists.) |
| 4 sector     | best | `stage_4_sector.yaml`     | Does intra-sector group attention beat mixed grouping? |
| 5 covariates | best | `stage_5_covariates.yaml` | Ablation: none / calendar_only / market_only / full. |
| 6 stability  | best | `stage_6_stability.yaml`  | Regime sub-windows (2021-H1..2026-YTD). Most important reality check. |
| 7 hold-out   | best | `stage_7_holdout.yaml`    | Headline table. Metric window locked to 2025-11-01..2026-04-30. |

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
- **Stage 7 metric mask**: the YAML carries `metric_window: {from, till}` but `run_stage` does not yet enforce it as a hard mask. Wire this in before running Stage 7. (Minor edit in `run_stage` — filter `preds` by `t_anchor >= metric_window.from` before metric pass.)
- **Path B (AutoGluon fine-tune)** is sketched in `exp_plan.md` §6 and in the legacy `moex_chronos2_pipeline.ipynb` §7 but not yet wired into the runner. Queue: after Stage 7.
- **Batching at 10m × ≥400 windows × 12 series**: not stress-tested. T4 should hold; `preds_partial.parquet` checkpoint every 25 windows is the recovery path.
- **CatBoost baseline** (wiki §7) is not in B0–B3. Optional Path B-era addition.

## Suggested next session

**Stage 0/1 runs (FORTS resolver now live; configs have `futures_proxies: [BR, Si, GD]`)**
1. Move the project folder onto Drive: `MyDrive/moex-hack/`.
2. Open `runner.ipynb` on a Colab T4. Run §0 (mount), §1 (source basic_cells), then uncomment §2 (bulk prefetch all 8 stages) **once** — softer on ISS than per-stage prefetch. The manifest now expands FORTS roots into ~120 SECIDs × 1d-or-60m; budget ~1–2 min of extra prefetch.
3. Run Stage 0 (smoke) with `CONFIG_PATH = configs/stage_0_smoke.yaml`. Verify: outputs in `runs/stage_0_smoke/`, aggregate DA ∈ [0.40, 0.60], all 6 plots render, **no "WARN ... intra-contract bars with |log_return|>0.20" prints** from the resolver (if any appear, the front-month selection picked a thin-day contract — escalate before trusting downstream metrics).
4. If smoke is clean: run Stage 1 sub-variants (edit `context_len` + bump `stage_id` to `stage_1a..d`).
5. Update `scratchpads/stage_0_scratch_pad.md` with the actual numbers + observations. Create `stage_1_scratch_pad.md` from `_TEMPLATE.md`.
6. If anything fails: patch `basic_cells.ipynb` (single source of truth) and re-run.
