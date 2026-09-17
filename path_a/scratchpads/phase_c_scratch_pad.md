# Phase C — lead-lag screening (discovery + confirmation), scratchpad

Combined file for both stages (discovery, confirmation) since they're two
steps of one screen, not independent runs — same pattern reasoning as Phase
B's single combined scratchpad, adapted for two dependent stages instead of
two independent arms.

## Pointer
- Discovery: `basic_cells.ipynb` §14 (`pairwise_lagged_xcorr` /
  `select_pair_shortlist`), no config file — driven directly against a
  discovery-window slice of the 80-ticker `algo_data` pull.
- Confirmation config: `configs/phase_c_leadlag_confirm.yaml`
- Confirmation output dir: `runs/phase_c_leadlag_confirm/`
- Started: 2026-09-17
- Status: **done, GATE FAILED (2026-09-17)** — 0/20 shortlisted pairs replicated
  out-of-sample. Third independent negative result for zero-shot Chronos-2 on
  MOEX returns (after Stage 2b and Phase B).

## Why this phase exists despite Phase B's gate failing

Two independent negative results precede this phase:
- Stage 2b (original approach): 60m bars, 12 tickers, DA≈0.485, 0/48
  BH-significant, Pearson≈0.
- Phase B (multivariate-vs-univariate gate, run 2026-09-17): 400 windows, 16
  tickers, both `group_mode` arms independently at DA≈0.484, aggregate
  ΔDA≈-0.00035, 0/64 BH-significant. Gate **FAILED** per the pre-registered
  rule → Phase C is formally not funded by that rule.

Proceeding anyway: Phase B only ever tested "does grouping a fixed 16-ticker
basket for joint forecasting beat forecasting them independently" — a
basket-wide average effect. Checked the per-ticker breakdown
(`runs/phase_b_univariate/metrics.csv`): no ticker showed even a hint of
individual signal (best cell DA=0.52, p=0.227 uncorrected). That's evidence
of "nothing in this specific 16-ticker sample," not evidence against "any
pair among a much larger set shows lead-lag structure" — a different
question, with 3-5 genuine pairs out of thousands potentially invisible to a
small hand-picked sample. Full reasoning: local plan
`the-simplest-model-does-snappy-church.md` rev. 3.

## Pre-registered design (locked in 2026-09-17, before running discovery)

1. **Universe**: full 80-ticker `algo_data/data/universe/equity_universe.yaml`
   list. Up to 80×79/2 = 3160 pairs before lag multiplication.
2. **Discovery/confirmation split**: chronological, non-overlapping.
   - Discovery: 2020-01-03 → 2023-06-30 (1275 days, 69.9%).
   - Confirmation: 2023-07-01 → 2024-12-30 (548 days, 30.1%).
   - Verified zero date overlap (discovery's last day is strictly before
     confirmation's first day).
3. **Lags tested**: 1–5 trading days, both directions per pair (`i` leads `j`
   and `j` leads `i` are separate hypotheses). 5 lags × 2 directions × up to
   3160 pairs ≈ up to 31,600 tests (fewer once tickers with insufficient
   history are dropped by `build_price_panel`'s coverage guard, same as
   Phase B).
4. **Shortlist rule**: BH-significant at q<0.05 in the discovery-phase
   screen; if more than 20 pairs survive, cap at top 20 by `|r|`.
5. **0 survivors is a valid, complete result** — not a trigger to loosen the
   rule or re-run with different parameters. BH at q<0.05 across ~30k tests
   is specifically designed so a true-null screen should show close to zero
   false positives; an empty shortlist directly answers "does broader
   screening find what the narrow 16-ticker test couldn't."
6. **Confirmation leakage guard**: no `metric_window` machinery (grepped
   `basic_cells.ipynb`, zero references anywhere — the earlier "parsed but
   not enforced" known-gap note was stale/wrong, corrected in
   `docs/current_state.md`). The confirmation config's own
   `date_from`/`date_till` (2023-07-01 → 2024-12-30) directly is the
   leakage guard — discovery only ever sees data strictly before that range.
7. **Per-pair confirmation success criterion**: pair-specific DA/Pearson from
   `run_stage`'s `metrics.csv` (filtered to the pair's two tickers) must be
   BH-significant **within confirmation's own test family** (not reusing
   discovery p-values — confirmation needs an independent test) AND beat the
   `last` baseline. Mirrors Phase B's three-part gate shape (ΔDA>0 AND
   significant AND beats-baseline), applied per pair.

## Configuration deviations from plan

**Amendment 1 (2026-09-17, after first discovery run, before confirmation)**:
added market-factor residualization to `pairwise_lagged_xcorr` (new
`residualize_market=True` default parameter). Not in the original
pre-registration — documented here as a deviation, not silently folded in.

The first (unresidualized) discovery run against the real 55-ticker panel
found 20 BH-significant pairs, but 19/20 shared the exact same lag (3)
across otherwise economically-unrelated tickers (oil/gas × retail, metals
× transport, etc.) — checked and confirmed the panel-wide equal-weight
market return itself has lag-3 autocorrelation ≈0.16 on this window, which
alone explains a broad cluster of same-lag false positives across many
pairs sharing exposure to that common factor. Spot-checking GAZP→IRKT
(one of the 20) by regressing out the market factor from both series
first: correlation went from r=0.218 (raw) to r=0.211 (residualized,
still strong), while several other pairs in the list weakened substantially
or lost significance — consistent with "most of the raw signal was the
shared factor, a couple of pairs have something real on top of it."

Implementation used leave-one-out residualization (each ticker demeaned by
the average of every OTHER ticker, not a simple panel-wide mean which
would include the ticker itself and mechanically induce spurious negative
correlations by construction — verified this bias is negligible at the
real panel's ~55-ticker scale via a matched-scale synthetic test, but
NOT negligible on a small ~10-ticker synthetic sanity panel, so the
verification test itself had to be re-scaled up to be representative; a
naive small synthetic check would have looked broken when the real
function was actually fine at production scale).

## Run log
| Date | Stage | Notes / changes since last run |
|------|-------|--------------------------------|
| 2026-09-17 | pre-registration | Design locked in above, before any code run or data looked at. `algo_data/config.md` widened 22→80 tickers; pull not yet executed by the user (manual-run policy — see plan/CLAUDE.md). |
| 2026-09-17 | data pull | 80-ticker AlgoPack pull run by user: 6039 requests, 24m11s. `processed/candles_1d/shares.parquet` has **76/80 tickers** (raw, pre-`build_price_panel`-guard). Missing entirely: X5, RAGR (already known, zero 2020-2024 history, recent redomiciliations), CNRU, DOMRF (new — likely recent listings, not yet individually verified against MOEX). Row-count audit shows a long tail of short-history tickers among the 76 present (e.g. OZPH=54, HEAD=69, YDEX=115, PRMD=123, DELI=231 rows vs ~1249 for full-history names) — expect `build_price_panel`'s `min_ticker_coverage=0.9` guard to drop a similar-sized chunk at discovery time, same pattern as Phase B (6/22 dropped there). Not a blocker; proceeding to discovery (§14) next — the guard's own drop log is the audit trail, not a pre-trim. |
| 2026-09-17 | discovery run 1 (unresidualized) | User ran §14 locally against the discovery slice: 55 tickers survived `build_price_panel`'s coverage guard (20 dropped for <90% raw coverage — ASTR, DELI, EUTR, FLOT, HEAD, LENT, MDMG, OZON, OZPH, POSI, PRMD, RENI, SGZH, SMLT, SPBE, SVCB, UGLD, UWGN, VKCO, WUSH, YDEX), 876 days (2020-02-21..2023-06-30, 34 days lost to the coverage guard's inner join). 14,850 (pair, lag, direction) tests, 20 BH-significant. **Rejected as the working shortlist** — 19/20 at lag=3, diagnosed as a market-factor artifact (see Amendment 1 above). Not used for confirmation. |
| 2026-09-17 | discovery run 2 (residualized, final) | Same panel, `pairwise_lagged_xcorr` with leave-one-out market residualization. 20 BH-significant pairs, lags now spread across 1-5 (no single-lag cluster), only 2 pairs (GAZP-IRKT, AFLT-VTBR) overlap with run 1's list — consistent with run 1 having been dominated by the shared factor. **This is the working shortlist**, copied below. |

## Discovery results (run 2, residualized — final)
```
55 tickers, 876 days (2020-02-21..2023-06-30), 14850 tests, 20 BH-significant (q<0.05, top-20 cap)
```

### Shortlist (from `select_pair_shortlist`, residualized run)
| ticker_i | ticker_j | lag | direction | leader | follower | r | p_value_bh |
|----------|----------|-----|-----------|--------|----------|---|------------|
| CBOM | RUAL | 1 | i_leads_j | CBOM | RUAL | -0.2345 | 3.19e-08 |
| CBOM | IRAO | 1 | i_leads_j | CBOM | IRAO | 0.2200 | 3.52e-07 |
| AFLT | PHOR | 2 | i_leads_j | AFLT | PHOR | -0.2122 | 1.17e-06 |
| GAZP | IRKT | 3 | i_leads_j | GAZP | IRKT | 0.2107 | 1.21e-06 |
| AFLT | VTBR | 3 | i_leads_j | AFLT | VTBR | 0.2072 | 1.69e-06 |
| PHOR | RASP | 1 | i_leads_j | PHOR | RASP | 0.2066 | 1.69e-06 |
| AFLT | PHOR | 1 | i_leads_j | AFLT | PHOR | -0.2007 | 3.99e-06 |
| GMKN | MTLRP | 1 | i_leads_j | GMKN | MTLRP | 0.2006 | 3.99e-06 |
| AFLT | UNAC | 4 | i_leads_j | AFLT | UNAC | -0.1996 | 4.52e-06 |
| BANEP | BSPB | 1 | i_leads_j | BANEP | BSPB | -0.1983 | 4.90e-06 |
| BANEP | RUAL | 1 | i_leads_j | BANEP | RUAL | 0.1932 | 1.12e-05 |
| MTSS | MVID | 2 | j_leads_i | MVID | MTSS | -0.1913 | 1.48e-05 |
| RASP | SNGSP | 1 | j_leads_i | SNGSP | RASP | 0.1903 | 1.61e-05 |
| MTSS | UNAC | 1 | i_leads_j | MTSS | UNAC | 0.1881 | 2.19e-05 |
| MSRS | MTSS | 5 | j_leads_i | MTSS | MSRS | 0.1878 | 2.26e-05 |
| MTLRP | RUAL | 1 | j_leads_i | RUAL | MTLRP | 0.1872 | 2.26e-05 |
| IRAO | VTBR | 1 | i_leads_j | IRAO | VTBR | 0.1849 | 3.16e-05 |
| AFLT | UNAC | 5 | i_leads_j | AFLT | UNAC | -0.1849 | 3.17e-05 |
| AFLT | PHOR | 2 | j_leads_i | PHOR | AFLT | 0.1838 | 3.47e-05 |
| AFLT | UNAC | 1 | i_leads_j | AFLT | UNAC | 0.1824 | 4.13e-05 |

**Union of tickers appearing in the shortlist** (for Phase C3's `tickers:` list):
AFLT, BANEP, BSPB, CBOM, GAZP, GMKN, IRAO, IRKT, MSRS, MTLRP, MTSS, MVID,
PHOR, RASP, RUAL, SNGSP, UNAC, VTBR (18 tickers)

## Confirmation results

Run: `run_stage("configs/phase_c_leadlag_confirm.yaml")`, 2026-09-17, user-run via `runner.ipynb`.

```json
{
  "stage_id": "phase_c_leadlag_confirm",
  "group_mode": "multivariate",
  "n_windows": 135,
  "mean_da_primary": 0.5082304526748971,
  "median_da_primary": 0.5074074074074073,
  "cells_signif_05": 0,
  "mean_pearson_primary": -0.037333044476012656,
  "mean_coverage_primary": 0.7536351165980796,
  "trend2_n_signals": 1757,
  "trend2_acc_both": 0.2885600455321571,
  "trend2_acc_cum": 0.5196357427433125
}
```

Basket-wide: chance-level DA (0.508), zero BH-significant (ticker, horizon) cells out of 72,
mean Pearson slightly negative (-0.037). Matches Phase B's earlier basket-wide null.

### Per-pair confirmation outcome (the actual pre-registered test, decision 7)

Recomputed pair-specific lagged Pearson correlation at each pair's *discovered* lag/direction,
on confirmation-window (2023-07-04..2024-12-30, 390 days) returns, same leave-one-out
market-factor residualization as the (amended) discovery methodology, BH-corrected **within
this 20-pair confirmation family** (not reusing discovery's p-values, per decision 7).

| pair (leader→follower) | lag | r (confirmation) | r (discovery) | p_value | p_value_bh | PASS/FAIL |
|---|---|---|---|---|---|---|
| MTSS→UNAC | 1 | -0.137 | +0.188 | 0.0070 | 0.140 | FAIL |
| AFLT→UNAC | 1 | -0.092 | +0.182 | 0.069 | 0.461 | FAIL |
| AFLT→UNAC | 4 | -0.096 | -0.200 | 0.061 | 0.461 | FAIL |
| GAZP→IRKT | 3 | -0.081 | +0.211 | 0.110 | 0.551 | FAIL |
| CBOM→IRAO | 1 | -0.073 | +0.220 | 0.150 | 0.599 | FAIL |
| AFLT→PHOR | 2 | -0.066 | -0.212 | 0.196 | 0.623 | FAIL |
| RUAL→MTLRP | 1 | +0.059 | +0.187 | 0.249 | 0.623 | FAIL |
| SNGSP→RASP | 1 | +0.063 | +0.190 | 0.219 | 0.623 | FAIL |
| AFLT→UNAC | 5 | -0.050 | -0.185 | 0.332 | 0.738 | FAIL |
| IRAO→VTBR | 1 | +0.044 | +0.185 | 0.384 | 0.768 | FAIL |
| PHOR→AFLT | 2 | +0.037 | +0.184 | 0.469 | 0.814 | FAIL |
| MVID→MTSS | 2 | -0.035 | -0.191 | 0.488 | 0.814 | FAIL |
| BANEP→BSPB | 1 | -0.031 | -0.198 | 0.546 | 0.839 | FAIL |
| GMKN→MTLRP | 1 | -0.008 | +0.201 | 0.878 | 0.947 | FAIL |
| MTSS→MSRS | 5 | -0.005 | +0.188 | 0.926 | 0.947 | FAIL |
| AFLT→PHOR | 1 | +0.007 | -0.201 | 0.888 | 0.947 | FAIL |
| PHOR→RASP | 1 | -0.003 | +0.207 | 0.947 | 0.947 | FAIL |
| AFLT→VTBR | 3 | -0.004 | +0.207 | 0.943 | 0.947 | FAIL |
| BANEP→RUAL | 1 | +0.021 | +0.193 | 0.673 | 0.947 | FAIL |
| CBOM→RUAL | 1 | +0.006 | -0.234 | 0.914 | 0.947 | FAIL |

**0/20 pairs significant at BH q<0.05 within the confirmation family.** Best uncorrected
p-value (MTSS→UNAC, p=0.007) doesn't survive BH correction (p_bh=0.140). Several pairs'
correlation sign flips entirely out-of-sample (e.g. GMKN→MTLRP: +0.201→-0.008; PHOR→RASP:
+0.207→-0.003; AFLT→VTBR: +0.207→-0.004) — consistent with discovery-phase hits being false
positives from the ~15,000-test family that didn't replicate, exactly the failure mode the
discovery/confirmation split exists to catch.

**Gate: FAILED.** Per decision 7's criterion (BH-significant within confirmation's own family
AND beats `last` baseline), 0/20 pairs pass even the first leg, so the `beats_last` check
(also computed, similarly unremarkable — no coherent per-ticker pattern) doesn't change the
verdict either way.

## Plots checked
- [x] `plots/da_heatmap.png` — no ticker/horizon cell stands out; uniform noise around 0.5.
- [x] `plots/da_vs_last.png` — no systematic edge over `last` baseline.
- [x] `plots/corr_hist.png` — centered near 0, consistent with mean Pearson ≈ -0.037.
- [ ] `plots/amplitude.png`
- [ ] `plots/coverage.png`
- [ ] `plots/examples.png`

## Observations

The discovery/confirmation split did exactly its job: 20 BH-significant discovery pairs (after
already fixing one real confound — the market-factor artifact) produced **zero** replications
out-of-sample. This is the expected behavior of a well-calibrated screen under a true null —
BH q<0.05 across ~15,000 discovery tests should let through close to 5% false positives among
"significant" hits by construction, and testing those survivors independently is exactly how
you'd expect to see them wash out if there was no real structure. Nothing here suggests the
screening methodology was broken (the opposite: it worked as designed, catching what discovery
alone could not).

Combined with Phase B (basket-wide multivariate-vs-univariate gate, FAILED) and Stage 2b (60m/
12-ticker zero-shot, FAILED), this is now the **third independent negative result** for
zero-shot Chronos-2 on MOEX return prediction — narrow gate, broad basket-average gate, and
now a broad *individual-pair* screen with proper out-of-sample confirmation. Each tested a
genuinely different hypothesis (grouped-vs-independent forecasting; any-pair lead-lag
structure) and each landed at chance level.

## Decision / Next

Per decision 5 (pre-registered): a null discovery result would have been a complete, valid
answer on its own. What actually happened is a stronger and more informative version of that —
20 candidates *did* survive discovery, and *none* replicated out-of-sample, which is direct
evidence the discovery hits were noise, not just "we didn't look hard enough." This closes the
loop the user asked for at the start of this phase ("we need to take more tickers... and try to
sort out successes in between") — successes were sorted out, and none survived confirmation.

This is not a trigger to loosen the shortlist threshold, expand max_lag, or re-run discovery
with different parameters chasing significance — per the pre-registered discipline, that would
be exactly the p-hacking this design was built to prevent.

Three legitimate options remain, matching `docs/current_state.md`'s standing framing:
1. Write up all three negative results (Stage 2b, Phase B, Phase C) as the project's finding —
   a rigorous, honestly-reported negative result across three independent hypotheses is itself
   a valid CV-quality deliverable.
2. The two follow-ons already discussed and queued (1h-bar frequency switch, Pearson/
   quantile-loss reporting) — genuinely different from a Phase C retry since they test a
   different frequency regime and a different metric, not the same lead-lag hypothesis again.
3. Pivot to Path B (AutoGluon fine-tuning) — a fundamentally different question ("can a
   fine-tuned model find something zero-shot can't") not foreclosed by any of these three
   results.
