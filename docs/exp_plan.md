# Experiment Plan — Chronos-2 on MOEX

Master plan for the full-scale predictability study. **Path A first** (zero-shot weights from the box). Path B (AutoGluon fine-tune) is sketched at the bottom and detailed once Path A has produced a reproducible baseline.

> **Pivoted 2026-09-17**: §3 below (the original numbered-stage sequence) is retired after
> Stage 2b's clean negative result. Current plan is §3b (gated phases A–D). §0–2 (statistical
> framing, universe, pipeline mechanics) still apply to the new plan unchanged.

Companion files:
- `basic_cells.ipynb` — reusable code blocks (cells are not invented per run, they are copied/imported from here).
- `runner.ipynb` — single universal notebook; reads one config YAML and runs it end-to-end.
- `configs/phase_<letter>_<name>.yaml` — per-run knobs (universe, interval, walk-forward, covariates, output paths). Currently empty — written as each phase starts.
- `scratchpads/*.md` — running log per run (what was run, observed deltas, anomalies, next tweak).

---

## 0. Statistical framing

Path A is a **descriptive significance study**. For every (stage, interval, ticker, horizon) cell we need to be able to answer two questions with numbers, not vibes:

1. **Direction.** Is directional winrate (DA) better than 0.5 across enough walk-forward windows that we can reject "fair coin"? Reported as DA + binomial p-value + 95% Wilson CI per (ticker, horizon). Aggregated as bootstrap median DA across tickers per stage.
2. **Amplitude.** Does the predicted return co-move with the realised return in magnitude? Reported as Pearson and Spearman correlation between predicted and realised return, plus |pred|/|true| ratio (calibration of magnitude), plus quantile coverage (q10–q90 hit-rate).

Statistical power floor (rough):
- DA gap of +5pp over 0.5 with binomial p<0.05 needs ≥ 400 forecasts. With 12 tickers × 1 horizon that is ≈ 34 walk-forward windows. With multiple horizons we get more comparisons but inflate the family of tests — Bonferroni / BH correction is applied across (ticker × horizon) cells when reporting overall significance.
- Minimum windows per cell, per wiki §6 and tightened here:
  - **1d**: ≥ 100 windows (shift = 1 bar)
  - **60m**: ≥ 300 windows (shift = 4 bars)
  - **10m**: ≥ 400 windows (shift = 4 bars)

**Evaluation horizons.** User priority: predicted bars 2, 3, 5. We additionally log h=1 (cheapest sanity check) but it is excluded from "primary" tables. So horizons reported:
- `h ∈ {2, 3, 5}` primary
- `h = 1` companion

For each window, Chronos-2 returns `horizon` future log-returns. Per-horizon metrics are computed on the **single point** at that future index (e.g. DA at h=3 is computed on bar 3 of the forecast vs the realised bar 3), not on cumulated returns. A separate "cumulative h=5" view (sum of returns 1..5) is also stored because it's the relevant quantity for entry/exit timing.

**Baselines** (computed inside every stage, on the same windows):
- B0 — zero-return (predict 0 every bar)
- B1 — last-return persistence (predict last realised return for all H bars)
- B2 — naive momentum (mean of last 5 returns)
- B3 — AR(1) per ticker fit on context window

A Chronos-2 result is only "interesting" when it beats B0/B1/B2 on DA *and* either improves correlation or improves quantile coverage. CatBoost / fine-tune comparisons live in Path B.

---

## 1. Universe and data sources

All stages pull from the **MOEX ISS API** via the soft prefetcher in `basic_cells.ipynb` and read **from local Parquet cache only** during the experiment phase. The cache lives on mounted Google Drive (`/content/drive/MyDrive/moex_cache/`) so it survives Colab runtime resets.

Cache key: `{secid}_{engine}_{market}_{interval}_{date_from}_{date_till}.parquet`.

**Tickers used across stages**
- *Core 12* (wiki §1): SBER, GAZP, LKOH, ROSN, NVTK, TATN, GMKN, PLZL, MAGN, NLMK, MOEX, VTBR.
- *Oil/gas subgroup*: GAZP, LKOH, ROSN, NVTK, TATN, SNGS, SNGSP.
- *Metals subgroup*: GMKN, PLZL, MAGN, NLMK, CHMF, ALRS.
- *Financials subgroup*: SBER, VTBR, MOEX, BSPB, CBOM.

**Indexes**: IMOEX, MOEXOG, MOEXMM, MOEXFN, RGBI (skip silently if interval not served).
**Futures proxies**: Brent (BR), USD/RUB (Si), Gold (GD). Contract code is resolved per date sub-range — see prefetcher §3.

**Date range**: `2021-01-01` → `2026-04-30`. Roughly 5 years; covers two regime shifts (2022 dislocation, 2023+ normalisation) which lets stage 6 quantify regime sensitivity.

---

## 2. Data pipelines

### Path A — zero-shot multivariate Chronos-2
1. **Soft prefetch (one-time per interval).** `prefetch_universe(cfg)` walks every (secid, engine, interval) needed for stages 0–7 of this plan and pulls into Drive cache. Rate-limited (≥ 0.2 s/request), retries on 429/5xx with backoff, idempotent (skips files that already exist), logs misses.
2. **Cache-only load.** `load_panel(cfg)` reads Parquet only. If a needed file is missing it errors out with the exact missing key — no silent ISS fall-through during experiments. (Switch to API-fall-through is a single flag for prod forecasting.)
3. **Regularise.** `to_regular_series` (10m/60m → MOEX session grid; 1d → `asfreq("B")`) + ffill. Inner-join across tickers so the panel index is identical for every series — required for group attention.
4. **Targets and covariates.**
   - target: log-return per ticker.
   - past covariates (broadcast across ids): IMOEX/MOEXOG/MOEXMM/MOEXFN/RGBI log-returns, Brent / USD-RUB / Gold log-returns, per-ticker dlog-volume.
   - future covariates (calendar only, leakage-safe): hour, dayofweek, dayofmonth, month, is_session_open.
5. **Walk-forward loop.** For each window `w`:
   - context = `ret_panel.loc[t-context_len : t]`, horizon = `ret_panel.loc[t+1 : t+H]`.
   - build `context_df` (long form, all tickers) and `future_df` (calendar at horizon timestamps).
   - one `Chronos2Pipeline.predict_df(...)` call → quantile forecasts for every ticker.
   - persist `pred_w` to `runs/{stage}/preds/` parquet (one row per (window, id, h_step, quantile)).
6. **Metric pass.** After the loop, compute per (ticker, horizon) DA, Pearson/Spearman corr, |pred|/|true|, q10–q90 coverage, baselines DA/corr. Aggregate to stage-level table + plots.

### Path B — AutoGluon fine-tune (deferred)
Skeleton in `path_a/archive/legacy_notebooks/moex_chronos2_pipeline.ipynb` §7. Reuses Path A's cache and panel build verbatim. Fine-tune cell is parameterised by the same YAML config — adding `path_b.fine_tune.*` knobs is mechanical once Path A produces a clean baseline. Path B is scheduled after stage 7 of Path A.

---

## 3. Path A — stage-by-stage plan (RETIRED 2026-09-17, historical record)

**This whole section describes the old linear numbered-stage plan, retired after Stage 2b's
clean negative result triggered a project pivot.** The project is now organized around gated
phases (A–D) instead — see §3b below for the current plan. Kept here unedited as a record of
what was originally designed and which parts actually ran; all configs referenced below are
archived at `path_a/archive/concluded_stages/` (see that folder's README for per-stage
disposition — concluded vs. superseded-without-running).

Each stage stores results under `runs/{stage_id}/` with: `config.yaml` snapshot, `preds/*.parquet`, `metrics.csv`, `metrics_baselines.csv`, `summary.json` (top-line numbers used in scratchpad), and `plots/*.png`. The scratchpad cites these paths and pastes the summary table.

### Stage 0 — smoke (pipeline + cache validation) ✅ concluded
- **Config**: `archive/concluded_stages/stage_0_smoke.yaml` (concluded 2026-06-12; run output stays live at `runs/stage_0_smoke/`)
- **Interval**: 1d
- **Universe**: core 12
- **Date**: 2024-01-01 → 2024-06-30 (short, fast, dense)
- **Context / horizon**: ctx=250, H=5
- **Walk-forward**: shift=1, target ~30 windows
- **Covariates**: full MVP set
- **Goal**: end-to-end pipeline executes; cache populated; output schema matches downstream readers; sanity-check DA is in [0.40, 0.60] (not 0% or 100% — that means a sign bug).
- **Success criterion**: Stage 1 can read Stage 0's outputs without code changes. No statistical claim is made here.

### Stage 1 — Daily, full study
- **Config**: `archive/concluded_stages/stage_1_daily.yaml` (superseded by pivot 2026-09-17; only 1c ran)
- **Interval**: 1d
- **Universe**: core 12
- **Date**: 2021-01-01 → 2026-04-30
- **Context grid**: {64, 128, 250, 500} (run as 4 sub-runs `stage_1a..d`)
- **Horizon**: H=5, evaluate at h ∈ {1, 2, 3, 5}
- **Walk-forward**: shift=1, ≥ 200 windows per sub-run
- **Covariates**: full MVP set
- **Goals**:
  1. Per (ticker, horizon) DA + binomial p — does any cell clear p<0.05 after BH correction?
  2. Identify context-length sweet spot from the 4-point grid (mean DA, mean corr per ctx).
  3. Quantile calibration: how far is observed q10–q90 hit-rate from 0.8?
- **Success criterion**: at least one (ticker, horizon) cell with DA ≥ 0.56 at p<0.05, AND Chronos beats B1 persistence on aggregate DA across the core 12.

### Stage 2 — 60-minute, full study ✅ concluded
- **Config**: `archive/concluded_stages/stage_2_60m.yaml` (concluded, clean negative result — DA≈0.485, 0/48 BH-significant cells, Pearson≈0; triggered the project pivot, see `current_state.md` session entry 14; run output at `runs/stage_2b_60m_ctx600/`)
- **Interval**: 60m
- **Universe**: core 12
- **Date**: 2023-01-01 → 2026-04-30 (~3 yrs intraday)
- **Context grid**: {300, 600, 1000} (sub-runs `stage_2a..c`)
- **Horizon**: H=5, eval h ∈ {1, 2, 3, 5}
- **Walk-forward**: shift=4, ≥ 300 windows per sub-run
- **Covariates**: full MVP set (calendar `hour` matters here)
- **Goals**: same three as Stage 1, plus check whether intraday DA decays with h faster than 1d does.
- **Success criterion**: aggregate DA at h=2 ≥ 0.53 with bootstrap 95% CI lower bound > 0.50.

### Stage 3 — 10-minute, full study
- **Config**: `archive/concluded_stages/stage_3_10m.yaml` (never run; superseded by pivot 2026-09-17)
- **Interval**: 10m — finest native ISS intraday bar (ISS exposes no 15m candle; confirmed against the ISS `durations` table and per-market `candleborders`). 10m is served for shares, indexes and FORTS.
- **Universe**: core 12 (drop any ticker with > 5% missing 10m bars after ffill — flagged at load)
- **Date**: 2024-05-01 → 2026-04-30 (10m has depth back to 2011-12-08, so the window is a *choice* — kept aligned with the 60m study; widen if more intraday windows are needed. ~53 bars/session at 10m vs ~35 at 15m, so window counts are higher for the same calendar span.)
- **Context grid**: {500, 1000, 1500} (sub-runs `stage_3a..c`)
- **Horizon**: H=5, eval h ∈ {1, 2, 3, 5}
- **Walk-forward**: shift=4, ≥ 400 windows per sub-run
- **Covariates**: full MVP set
- **Goals**: same; plus the user's specific question — does the "first two predicted bars hold" effect from the smoke run persist with proper walk-forward? Reported as DA(h=2) − DA(h=5).
- **Success criterion**: aggregate DA at h ∈ {2, 3} statistically distinguishable from 0.5 (bootstrap CI) on the core 12.

### Stage 4 — Sector groups
- **Config**: `archive/concluded_stages/stage_4_sector.yaml` (never run; superseded by pivot 2026-09-17)
- **Interval**: chosen as the best from stages 1–3
- **Universe**: three sub-runs — oil/gas, metals, financials (groups defined in §1)
- **Goal**: does group attention pay off more when the cross-series correlation is high (intra-sector) than when it is diluted (mixed core-12)? Metric of interest: per-ticker DA in sector group vs the same ticker's DA in the mixed core-12 baseline run.
- **Success criterion**: at least one sector shows mean +1.5pp DA over its corresponding tickers' Stage-{1|2|3} numbers.

### Stage 5 — Covariate ablation
- **Config**: `archive/concluded_stages/stage_5_covariates.yaml` (never run; superseded by pivot 2026-09-17)
- **Interval**: best from stages 1–3
- **Universe**: core 12
- **Sub-runs**:
  - `5a` no covariates (target only)
  - `5b` calendar-only (future-known leakage-safe baseline)
  - `5c` market-only (no calendar)
  - `5d` full MVP (matches best stage 1–3 sub-run)
  - `5e` full MVP + **price levels** — adds `log(USD/RUB)`, `log(Brent)` (and optionally `usdrub_z252`, `brent_z252` rolling z-scores over a 252-bar lookback) as past covariates. Tests whether absolute regime levels add lift beyond returns. See wiki §3 *Open extension*. Depends on FORTS resolver (§5).
- **Goal**: isolate which covariate family carries the signal. Reported as Δ DA and Δ corr from 5a baseline.
- **Success criterion**: 5d beats 5a by ≥ 1pp DA on aggregate; identify whether 5b or 5c carries most of the lift; **5e − 5d ≥ +0.5pp DA** to justify promoting price levels into Stage 6/7 default.

### Stage 6 — Time-window stability
- **Config**: `archive/concluded_stages/stage_6_stability.yaml` (never run; superseded by pivot 2026-09-17)
- **Interval**: best from stages 1–3, best ctx + covariates from stage 5
- **Universe**: core 12
- **Sub-windows**: 2021-H1, 2021-H2, 2022 (war regime), 2023, 2024, 2025, 2026-YTD. Each is a separate metric block over the same walk-forward inside that window.
- **Goal**: does DA / corr hold across regimes, or is the signal concentrated in one period? This is the most important sanity check for "real" predictability vs lucky window.
- **Success criterion**: ≥ 4 of 7 sub-windows clear DA > 0.5 with one-sided binomial p<0.10, and the worst sub-window does not collapse below 0.46.

### Stage 7 — Held-out consolidation
- **Config**: `archive/concluded_stages/stage_7_holdout.yaml` (never run; superseded by pivot 2026-09-17)
- **Interval/ctx/covariates**: frozen from stages 1–6 best.
- **Date**: hold-out window = last 6 months (2025-11-01 → 2026-04-30). Earlier data is allowed only as context, **no metric is computed before the hold-out cutoff** — written into the runner as a hard assertion.
- **Goal**: one number per (ticker, horizon) for the final report. This is the headline table.
- **Success criterion**: replicates the stage 1–3 magnitudes on the locked-down window, within the bootstrap CI.

---

## 3b. Path A pivot — current plan (2026-09-17)

Stage 2b's clean negative result (DA≈0.485, 0/48 BH-significant cells, Pearson≈0 — see
`current_state.md` session entry 14) retired §3 above. The project now runs on **gated
phases** instead of a linear stage sequence:

- **Phase A — universe + data.** Expand the ticker universe via `algo_data`'s
  `rank_equity_universe()` (506 TQBR candidates → 80 selected, done 2026-09-17) and ingest
  through `path_a`'s new `load_from_algopack` adapter + `min_ticker_coverage` guard. **Done.**
  Real AlgoPack pull executed 2026-09-17 (22 tickers configured, `build_price_panel` keeps
  ~16 after the coverage guard — 6 dropped as recent listings/redomiciliations with
  insufficient 2020-2024 history; see `algo_data/current_state.md`).
- **Phase B — multivariate-vs-univariate gate. ✅ concluded, GATE FAILED (2026-09-17).**
  Does grouping many series for Chronos-2 to forecast jointly (`cross_learning=True`) beat
  forecasting each independently (`cross_learning=False`)? Both arms run: 400 windows,
  16 tickers, `context_len=250`, identical configs except `group_mode`
  (`configs/phase_b_multivariate.yaml` / `phase_b_univariate.yaml`). Paired McNemar test
  (`mcnemar_gate_test()`, `basic_cells.ipynb` §13), BH-corrected across 64 (ticker × horizon)
  cells: **aggregate ΔDA ≈ -0.00035 (not positive), 0/64 BH-significant cells favoring
  multivariate.** Both arms independently landed at chance-level DA (~0.484), nearly
  indistinguishable from each other on every metric — not a power problem, a genuine null
  result. **Gate FAILED → Phase C is not funded, per the pre-registered rule.** Full
  numbers, per-cell table, and the pre-registration note (this was decided as a single-run
  test, no context_len sweep, before any run) in `path_a/scratchpads/phase_b_scratch_pad.md`.
  `group_mode` in `basic_cells.ipynb` (`run_walk_forward`) is a single boolean threaded
  straight to `predict_df`'s `cross_learning` kwarg — verified against
  `chronos-forecasting`'s installed source that this, not `id_column` grouping alone, is the
  actual joint-attention switch; prior stages (0-2) never set it, so Stage 2b's negative
  result was effectively a univariate baseline already — confirmed by Phase B's univariate
  arm landing at almost the same DA as Stage 2b.
- **Phase C — lead-lag screening across the full 80-ticker universe. ✅ concluded, GATE
  FAILED (2026-09-17).** Proceeded despite Phase B's gate failing, since
  Phase B only tested one question — does grouping a fixed 16-ticker basket for *joint*
  forecasting beat forecasting them independently (a basket-wide average effect). Per-ticker
  breakdown of Phase B's own output (`runs/phase_b_univariate/metrics.csv`) showed no ticker
  with even a hint of individual signal (best cell DA=0.52, p=0.227 uncorrected) — evidence of
  "nothing in that specific 16-ticker sample," not evidence against "any pair among a much
  larger set shows lead-lag structure," which Phase C was always designed to test. Full
  rationale in `path_a/scratchpads/phase_c_scratch_pad.md`.
  - **C1 (universe + data) — done.** `algo_data/config.md` `tickers.shares` widened 22→80
    (full `equity_universe.yaml`). Real pull executed 2026-09-17 (6039 requests, 24m):
    76/80 tickers have any data (X5, RAGR, CNRU, DOMRF have zero 2020-2024 history), 55 of
    those 76 survive `build_price_panel`'s 0.9 coverage guard on the discovery-window slice.
  - **C2 (discovery) — done.** `basic_cells.ipynb` §14 — `pairwise_lagged_xcorr()` (Pearson
    correlation per ticker pair × lag 1–5 × direction, both `i` and `j` as potential leader,
    on the discovery-window slice 2020-01-03→2023-06-30 only) + `select_pair_shortlist()`
    (BH q<0.05, top-20 cap if oversubscribed by |r|). BH pattern copied verbatim from
    `mcnemar_gate_test()` (§13), not reimplemented.
    **Methodology amendment after the first run**: an initial unresidualized run found 20
    BH-significant pairs, but 19/20 shared the same lag (3) across economically-unrelated
    tickers — traced to the panel-wide market-average return's own lag-3 autocorrelation
    (≈0.16), which alone produces a cluster of same-lag false positives. Added leave-one-out
    market-factor residualization to `pairwise_lagged_xcorr` (each ticker demeaned by every
    OTHER ticker's same-day return before lagged correlation) and re-ran. Verified the
    residualization itself doesn't introduce bias at the real ~55-ticker scale (a naive
    small-N synthetic sanity check looked broken but was actually testing an unrepresentative
    regime — re-verified at matched scale). Final (residualized) discovery run: 55 tickers,
    876 days, 14,850 tests, **20 BH-significant pairs, lags spread 1–5 with no single-lag
    cluster** — union of 18 tickers, full table in the scratchpad.
  - **C3 (confirmation) — done, GATE FAILED.** `configs/phase_c_leadlag_confirm.yaml`,
    `group_mode: multivariate`, confirmation window 2023-07-04→2024-12-30 (135 windows,
    18 tickers, zero date overlap with discovery). Basket-wide: chance-level DA (0.508),
    0/72 BH-significant (ticker, horizon) cells, mean Pearson ≈ -0.037. **Per-pair test (the
    actual pre-registered criterion, decision 7)**: recomputed each of the 20 shortlisted
    pairs' lagged correlation at its discovered lag, on confirmation-window returns, same
    leave-one-out residualization, BH-corrected within this 20-pair confirmation family —
    **0/20 pairs significant at q<0.05.** Best uncorrected p=0.007 (MTSS→UNAC) doesn't
    survive correction (p_bh=0.140). Several pairs' correlation sign flips entirely
    out-of-sample (e.g. GMKN→MTLRP: discovery r=+0.20 → confirmation r=-0.008). Full
    per-pair table in `path_a/scratchpads/phase_c_scratch_pad.md`.
  - **Interpretation**: the discovery/confirmation split worked exactly as designed — 20
    BH-significant discovery hits (after fixing a real market-factor confound, see C2 above)
    produced zero replications out-of-sample, direct evidence those hits were false
    discoveries from the ~15k-test family rather than "insufficient search." This is now the
    **third independent negative result** for zero-shot Chronos-2 on MOEX returns (after
    Stage 2b and Phase B), each testing a genuinely different hypothesis.
  - **Quantile (pinball) loss — added and backfilled 2026-09-17.** `basic_cells.ipynb` §15
    (`pinball_loss`/`per_cell_quantile_loss`), computed retroactively from Phase B's and
    Phase C's already-saved `preds.parquet` (no re-run needed). Result: Phase B's two arms
    have near-identical pinball loss (0.00509 multivariate vs 0.00510 univariate — matches
    every other metric's "indistinguishable" pattern); Phase C confirmation: 0.00639.
    Coverage (q10-q90 hit rate) is close to the 0.80 target in all three runs (0.79, 0.79,
    0.75) — Chronos-2's quantile intervals are reasonably well-calibrated even though the
    median forecast carries no directional skill. No baseline-comparison helper was added:
    `baseline_predictions` gives every baseline (zero/last/momentum5/ar1) the same value
    across all three quantile columns (point forecasts, not distributional), so a
    baseline's own "pinball loss" would just be a rescaled MAE, not a real calibration
    test — interpreted jointly with `coverage` instead.
  - **1h follow-on — ✅ concluded, GATE FAILED (2026-09-17).** Genuinely different frequency
    test (user's original intent), not a Phase C retry. `algo_data/config.md`
    `candles.intervals` widened to `[1d, 1h]` (period kept at the full 2020-2024 range to
    avoid truncating the already-processed daily parquet — see `algo_data/current_state.md`);
    real pull executed (76/80 tickers have 1h history, 6-9558 requests, ~49min). 24-month
    analysis window (2023-01-02→2024-12-30), ~70/30 split (365 discovery / 156 confirmation
    trading days, verified zero overlap). Discovery driver in `runner.ipynb` §2b
    parameterized (`DISCOVERY_INTERVAL=60`) — same leave-one-out residualized
    `pairwise_lagged_xcorr`/`select_pair_shortlist` as the daily run, no methodology changes.
    **Discovery**: 16-ticker panel, 2914-2917 bars, **13 BH-significant (pair, lag,
    direction) tests** (q<0.05, well under the top-20 cap), lags spread 2-5 bars (intraday,
    not the daily run's multi-day story) with no single-lag dominance. Includes two
    same-issuer ordinary/preferred pairs (SBER↔SBERP, MTLR↔MTLRP) alongside 8 cross-issuer
    pairs. Full table in `path_a/scratchpads/phase_c_1h_scratch_pad.md`.
    **Confirmation** (`configs/phase_c_leadlag_1h_confirm.yaml`, 16 tickers,
    2024-05-27→2024-12-30, 1247 bars, all 16 tickers survived coverage filter): basket-wide
    chance-level DA (0.494), 0/16 BH-significant (ticker, horizon) cells, mean Pearson
    ≈ -0.023. **Per-pair test (the pre-registered criterion)**: recomputed each of the 13
    hypotheses at its discovered lag on confirmation-window returns, BH-corrected within
    this 13-test family — **0/13 pairs significant at q<0.05.** Largest surviving
    correlation: SBER→VTBR r=0.059 (p=0.037 uncorrected, p_bh=0.38 — fails). The two
    same-issuer pairs also failed to replicate (r≈0.001-0.02), ruling out even a mechanical
    artifact story for those. **Fourth independent negative result** (after Stage 2b, Phase
    B, Phase C daily) — two frequencies (daily, 1h) and two test designs (basket gate,
    pairwise lead-lag) now agree: no detectable structure in zero-shot Chronos-2 on this
    universe. Full result table and interpretation in
    `path_a/scratchpads/phase_c_1h_scratch_pad.md`.
    **Univariate-with-covariates companion arm (2026-09-17)**: does Chronos extract any
    signal through the covariate panel alone (`group_mode: univariate`, `covariates: full`,
    no cross-ticker attention), on the same 16 tickers the lead-lag screen flagged?
    `configs/phase_c_leadlag_1h_confirm_univariate.yaml`, identical to the multivariate
    confirm config except `group_mode`. Result: chance-level, statistically indistinguishable
    from multivariate (DA 0.4918 vs 0.4936, mean Pearson -0.0282 vs -0.0230, 0/16
    significant cells in both). Mean per-cell DA diff across 64 (ticker, horizon) cells:
    -0.0004 — no consistent benefit either direction; the two largest cells favoring
    univariate (SBER/SBERP at h=1, +0.03-0.04 DA uncorrected) are within the noise scale
    expected from 64 uncorrected comparisons. Stronger than Phase B's original null (which
    used a sector-stratified sample, not tickers chosen for showing correlation): confirms
    covariates aren't rescuing signal even on tickers specifically selected for having shown
    pairwise structure in discovery.
- **Phase D — stretch backtest (gated on B or C). NOT FUNDED — both gating conditions
  failed/not attempted.** Toy, explicitly educational framing. Not
  designed yet.
- **Phase E — event-conditioned burst detection. ✅ concluded, NULL RESULT
  (2026-09-17).** Different hypothesis than Phases B/C: dependencies may occur in
  short bursts a full-sample correlation/DA number averages away, rather than
  holding across the whole sample. Detection-only goal (not exploitation), full
  design rationale and deferred experiment families in
  `docs/transient_dependency_research.md`. Scope for this pass: E1 (synthetic
  positive-control validation) then E2 (event-conditioned leader/follower MVP),
  deferring 10-minute-or-finer resolution and every experiment family beyond
  event-conditioning.
  - **E1 (synthetic validation) — done, both tests pass.** `basic_cells.ipynb` §16:
    injected-burst power test (20 trials, 76-ticker synthetic panels matching real
    scale, known 75%-same-direction relationship) — `detection_rate=1.0`,
    `mean_abs_frac_error=0.031`. Null false-alert-rate test (20 trials × 380 pairs,
    pure-null synthetic panels) — 0/7600 BH-significant hits, well under the
    nominal 5% ceiling. Runs automatically every time `basic_cells.ipynb` is
    sourced; E2's real-data functions are unreachable without E1 passing first.
  - **E2 (event-conditioned MVP, 1h) — done, NULL at discovery.** `runner.ipynb`
    §2c/§2d, pandas-only (no Chronos). Mechanism: leader's residualized return
    exceeds a 2σ trailing (causal) threshold → check follower's residualized
    return same-direction response `lag`∈{1,2,3,4} bars later, binomial test
    against the 50% null. Event-count floor n≥85 per candidate, derived via
    binomial two-proportion power calculation (65% target effect, 80% power,
    α=0.05) — see `basic_cells.ipynb` §16 header for the derivation. Same
    discovery/confirmation split as Phase C's 1h follow-on (2023-01-02→2024-05-24
    discovery, 2024-05-27→2024-12-30 confirmation), reusing the date split but not
    the ticker shortlist (different mechanism). 53/76 tickers survived the
    coverage guard, 2919 discovery bars, 11024 candidate (leader, follower, lag)
    tests, 100% cleared the event floor. **0/11024 BH-significant at q<0.05** —
    confirmation stage not reached (nothing to confirm), which is itself the
    complete pre-registered result.
  - **E2 (event-conditioned MVP, daily) — done, NULL, weaker evidence than 1h.**
    `runner.ipynb` §2e/§2f. Daily bars needed re-derived parameters, not a
    resolution swap on 1h's numbers: a 2σ threshold gives only ~9-16 events per
    ticker over a comparable window (far under any usable floor), so
    `threshold_std` was lowered to **1.25σ** (a "notable move," not a strict
    shock) and the discovery/confirmation split widened to the full 2020-2024
    history (874/375-bar 70/30 split, own zero-overlap check, not copied from
    Phase C's daily dates). Floor **n≥79**, set by the confirmation window's
    smaller achievable event count (the binding constraint at daily resolution,
    unlike 1h where both sides had headroom). 55/76 tickers survived coverage,
    887 discovery bars, 11880 candidate tests, 100% cleared the floor. **3
    BH-significant discovery candidates** (SBER→SFIN, CHMF→ROSN, SBERP→VSMO, all
    lag=2, all showing an unexpected OPPOSITE-direction pattern, `same_dir_frac`
    0.28-0.31 vs. the 0.50 null). **0/3 confirmed — and none were even eligible**
    for a properly powered confirmation test (44-60 confirmation-window events,
    below the n≥79 floor); `same_dir_frac` regressed to ~0.42-0.48 in confirmation
    regardless. Caught and fixed a latent bug during this run:
    `run_e2_confirmation`'s `confirmed` flag wasn't checking `eligible`, so an
    ineligible pair clearing BH by chance would have been wrongly marked
    confirmed (didn't change this run's outcome, fixed before it could).
  - **Fifth independent negative result** (Stage 2b, Phase B, Phase C daily,
    Phase C 1h, now Phase E at both resolutions). Both land at the same practical
    conclusion (no confirmable burst structure), but the daily result is
    structurally weaker evidence than 1h's — daily's ~5-year history can't
    generate enough confirmation-window events for this detector shape, a real
    limitation, not an execution flaw. Full writeup in
    `path_a/scratchpads/phase_e_scratch_pad.md`.

New configs use `phase_<letter>_<name>.yaml` naming (e.g. `phase_b_multivariate.yaml`,
`phase_b_univariate.yaml`). Full phase-by-phase design lives in the local pivot plan
(`tmp/plans/`, not committed); this section is a pointer, not a duplicate.

---

## 4. Results representation (per stage)

Every stage's run emits:

**Tables** (`metrics.csv`, `metrics_baselines.csv`)
- Per (ticker, horizon): N_windows, DA, binomial p, Wilson CI, Pearson r, Spearman ρ, |pred|/|true| median, q-coverage q10–q90, MAE on returns.
- Same for B0/B1/B2/B3 baselines.
- Aggregated rows: mean across tickers, bootstrap 95% CI.

**Plots** (`plots/`)
- `da_heatmap.png` — ticker × horizon DA heatmap (with diverging colormap centred on 0.5).
- `da_vs_baseline.png` — bar chart, Chronos DA − B1 DA per ticker, per horizon.
- `corr_hist.png` — histogram of per-window Pearson(pred, true) across all (ticker, window) pairs at each horizon.
- `amplitude_calibration.png` — scatter of predicted |return| vs realised |return|, per horizon.
- `coverage_bar.png` — observed q10–q90 hit-rate per ticker vs target 0.80.
- `forecast_examples.png` — 6 representative windows (3 good, 3 bad) with realised price overlay and quantile bands.

**Commentary** (`summary.json` + scratchpad)
- One paragraph: did the stage's success criterion fire? On which tickers/horizons specifically? What surprised us? What changes for the next stage?

---

## 5. Open items / decisions parked here

- **FORTS contract roll handling** (BR/Si/GD). **Resolved 2026-05-19.** ISS probes confirmed the design assumptions; resolver landed in `basic_cells.ipynb` section 4b. Notes vs the original 7-step plan:
  1. **Contract codes.** `{root}{month_letter}{year_digit}` works as-is. Roots BR (12 letters), Si/GD (HMUZ). 120/120 candidate SECIDs returned data in the 2021–2026 range (`1B_res.md`).
  2. **Active window.** Replaced expiry-from-`MATDATE` lookup with **per-bar front-month-by-volume selection** — same intent, simpler, and avoids a second endpoint per contract. The candles endpoint has no `OPENPOSITION` column anyway (`345_res.md`), so the alternative (history endpoint) would have meant fetching the full chain twice. Volume vs OI ranked the same contract as front on the spot-check date (BRK4 vs BRM4 on 2024-04-15).
  3. **Per-contract candles.** Cached as `futures_forts_{secid}_{interval}_{from}_{till}.parquet` (matches the equity scheme via `_cache_key`). 60m paginates at PAGESIZE=500 inside `_iss_candles` — already handled. **FORTS served natively at 10m/60m/1d** (BRK6 `candleborders` confirms interval 10): the resolver fetches each contract at the target interval, no cross-interval fallback. (ISS has no 15m candle for *any* market — see Stage 3.)
  4. **Stitch.** Implemented in `build_covariate_panel`: regrid `close` onto target interval, carry `contract_id` via reindex+ffill, compute log-return on the target grid, NaN the return wherever `contract_id != contract_id.shift(1)`. Stage 5e levels are exposed via the regridded `{name}_close` series (step jumps preserved, model sees the truthful regime change).
  5. **Cache key for resolved series.** `{root}_forts_resolved_{interval}_{from}_{till}.parquet`.
  6. **Validation.** Spot-check on BRJ4 / BRK4 / BRM4 (Task 4 / `345_res.md`): boundary jumps +0.61% and −4.81%, well under the `|r| > 0.20` red-flag threshold. The resolver prints a `WARN` line if any intra-contract bar exceeds 20% on load — flag for thin-day misselection.
  7. **Implementation site.** `_resolve_futures_chain(root, interval, date_from, date_till, cache_dir)` in `basic_cells.ipynb` §4b, called from `load_stage_inputs`. `build_prefetch_manifest` expands FORTS roots into the candidate SECID set so `prefetch_all` populates the cache up front.
- **Intraday calendar features (10m/60m).** `hour` ∈ {10..18} is a 9-level categorical — Chronos handles continuous, so we pass it as float; revisit if calibration tables look bucketed.
- **Multi-test correction.** Reporting per-cell binomial p + BH-adjusted q in stage-level table. Bonferroni for the headline aggregate claim only.

---

## 6. Path B sketch (queued)

After Stage 7 closes, we run Path B against the same configs:
- `path_b.enabled: true` flips the runner from `predict_df` (zero-shot) to AutoGluon `TimeSeriesPredictor.fit(...)` with `hyperparameters={"Chronos": {model_path: "amazon/chronos-2", fine_tune: true, ...}}`.
- Walk-forward is unchanged; we re-fit per outer fold (chunked over `N_FOLDS` outer windows to keep T4 time bounded).
- Comparison view: zero-shot DA vs fine-tuned DA per (ticker, horizon). Statistically significant lift = Path B advances.
