# Phase C — 1h follow-on (discovery + confirmation), scratchpad

Combined file for both stages, same pattern as `phase_c_scratch_pad.md` (the
daily run). This is a genuinely different test (1h bars, not a retry of the
daily screen that GATE FAILED) — see that file and
`path_a/configs/phase_c_leadlag_1h_confirm.yaml`'s header for the rationale.

## Pointer
- Discovery: `runner.ipynb` §2b (`DISCOVERY_INTERVAL=60`), no config file —
  driven directly against a discovery-window slice of the 76-ticker 1h
  `algo_data` pull (`candles_1h/shares.parquet`).
- Confirmation config: `configs/phase_c_leadlag_1h_confirm.yaml`
- Confirmation output dir: `runs/phase_c_leadlag_1h_confirm/`
- Started: 2026-09-17
- Status: **done, GATE FAILED (2026-09-17)** — 0/13 shortlisted (pair, lag,
  direction) hypotheses replicated out-of-sample. Fourth independent
  negative result (after Stage 2b, Phase B, Phase C daily).

## Pre-registered design (locked in earlier, before running 1h discovery)

Carried over unchanged from the daily run (same file, same functions,
same BH pattern, same leave-one-out market-factor residualization):

1. **Universe**: 76-ticker 1h pull (`algo_data` widened to `[1d, 1h]`
   2026-09-17; 76/80 configured tickers have 1h history — 4 recent-IPO
   names, e.g. OZPH/HEAD/PRMD/YDEX, dropped by insufficient bar coverage
   going back to 2020, expected and not investigated further).
2. **Discovery/confirmation split**: chronological, non-overlapping, 24-month
   total range.
   - Discovery: 2023-01-02 → 2024-05-24 (365 trading days, ~70%).
   - Confirmation: 2024-05-27 → 2024-12-30 (156 trading days, ~30%).
   - Verified zero date overlap (3-day gap: 2024-05-25..26, a weekend +
     holiday, not a leakage buffer added on purpose — just where the weekly
     calendar landed).
3. **Lags tested**: 1–5 bars (bars, not trading days, at 1h resolution — so
   up to ~5 hours / same trading day, not the same "same-week" economic
   story as the daily run's 1-5 day lags; noted as a scope difference, not
   an error, since the discovery function is lag-unit-agnostic).
4. **Shortlist rule**: BH-significant at q<0.05, top-20 cap if oversubscribed
   — same as daily.
5. **0 survivors is a valid, complete result** — same as daily (decision 5
   in `phase_c_scratch_pad.md`).
6. **Market-factor residualization**: leave-one-out, same verified-correct
   implementation as the daily run (no changes needed — the bug and fix were
   both interval-agnostic).
7. **Per-pair confirmation criterion**: BH-significant within the
   confirmation run's own test family (not reusing discovery p-values) AND
   beats the `last` baseline — same three-part gate shape as daily,
   applied per pair.

## Discovery result (2026-09-17)

Ran `runner.ipynb` §2b with `DISCOVERY_INTERVAL=60`,
`DISCOVERY_FROM/TILL = "2023-01-02", "2024-05-24"`.

**13 BH-significant (pair, lag, direction) tests** (q<0.05), well under the
top-20 cap so no effect-size truncation applied. Full table:

| leader | follower | lag | r | p_value | p_value_bh | n |
|---|---|---|---|---|---|---|
| BANEP | SNGSP | 5 | -0.1753 | 1.57e-21 | 2.16e-17 | 2914 |
| SNGSP | MTSS | 3 | -0.1395 | 3.86e-14 | 2.66e-10 | 2916 |
| SBERP | VTBR | 4 | 0.1057 | 1.08e-08 | 4.94e-05 | 2915 |
| SBERP | SBER | 4 | 0.0994 | 7.45e-08 | 2.57e-04 | 2915 |
| MGNT | CHMF | 5 | 0.0970 | 1.53e-07 | 4.23e-04 | 2914 |
| SBER | SBERP | 4 | 0.0930 | 4.97e-07 | 1.14e-03 | 2915 |
| FESH | NMTP | 3 | 0.0873 | 2.36e-06 | 4.64e-03 | 2916 |
| SBER | VTBR | 4 | 0.0849 | 4.41e-06 | 7.59e-03 | 2915 |
| VTBR | HYDR | 5 | 0.0842 | 5.30e-06 | 8.11e-03 | 2914 |
| NMTP | MRKC | 4 | 0.0825 | 8.13e-06 | 1.12e-02 | 2915 |
| SBERP | UPRO | 3 | -0.0807 | 1.28e-05 | 1.60e-02 | 2916 |
| MRKC | VSMO | 4 | 0.0758 | 4.22e-05 | 4.47e-02 | 2915 |
| MTLRP | MTLR | 2 | 0.0761 | 3.92e-05 | 4.47e-02 | 2917 |

**16 unique tickers** in the union: BANEP, CHMF, FESH, HYDR, MGNT, MRKC,
MTLR, MTLRP, MTSS, NMTP, SBER, SBERP, SNGSP, UPRO, VSMO, VTBR.

### Observations (pre-confirmation, do not over-read)

- Qualitatively different shape from the daily discovery shortlist (20
  pairs, 19/20 sharing the same lag before residualization, later cleaned
  up — see `phase_c_scratch_pad.md` Amendment 1). Here the 13 hits spread
  across lags 2-5 with no single dominant lag, which is *less* suggestive of
  a residual shared-factor artifact than the initial (pre-fix) daily result
  was. Still fully residualized with the verified leave-one-out method, so
  this isn't "we got lucky and skipped a check" — just noting the shape
  looks more plausible on its face than the daily run's *first* (buggy)
  attempt did.
- **Two same-issuer ordinary/preferred pairs** in the shortlist: SBER↔SBERP
  (3 of the 13 rows) and MTLR↔MTLRP (1 row). These are economically distinct
  from cross-issuer pairs — same-day correlation between share classes of
  one company is expected and uninteresting; a lag-2/lag-4 (2-4 *hour*)
  lead-lag between them could reflect real liquidity/order-flow migration
  between classes, or could reflect a data artifact (e.g. update timing
  differences between two feeds for the same underlying news). Kept in the
  confirmation universe per the pre-registered rule (no same-issuer
  exclusion was pre-registered), flagged here for interpretation regardless
  of confirmation outcome.
- The remaining 8 cross-issuer pairs (BANEP-SNGSP, SNGSP-MTSS, MGNT-CHMF,
  FESH-NMTP, SBER/SBERP-VTBR, VTBR-HYDR, NMTP-MRKC, SBERP-UPRO, MRKC-VSMO)
  are the ones that would actually support a genuine cross-asset lead-lag
  story if they survive confirmation.
- Lags are in **bars** (1h), not trading days — lag 2-5 bars is a
  same-session (intraday) effect, not the "same week" story the daily run's
  1-5 day lags represented. This is a different economic hypothesis
  (intraday information propagation vs multi-day propagation), consistent
  with the user's original stated interest in 1h resolution.

## Confirmation result (2026-09-17)

Ran via `runner.ipynb` §3 (`CONFIG_PATH = "configs/phase_c_leadlag_1h_confirm.yaml"`),
16 tickers, `date_from/till = "2024-05-27"/"2024-12-30"`, `context_len: 250`,
`max_windows: 400`, `group_mode: multivariate`. Confirmation panel: 1247
1h bars × 16 tickers, all 16 tickers survived the coverage filter (no
dropouts — unlike the daily run's X5/RAGR situation).

**Basket-wide Chronos summary** (`summary.json`): `mean_da_primary=0.4936`,
`cells_signif_05=0`, `mean_pearson_primary=-0.023`, `mean_coverage_primary=0.783`.
Chance-level, consistent with every prior negative result.

**Per-pair test** (the actual pre-registered decision-7 criterion — re-applied
the exact discovery methodology, same leave-one-out residualized
`pairwise_lagged_xcorr`, to each of the 13 discovered (pair, lag, direction)
hypotheses restricted to the confirmation window, then BH-corrected within
this 13-test family only, independent of discovery's p-values):

| leader | follower | lag | r (confirm) | p_value | p_value_bh | PASS/FAIL |
|---|---|---|---|---|---|---|
| BANEP | SNGSP | 5 | -0.0064 | 0.822 | 0.977 | FAIL |
| SNGSP | MTSS | 3 | -0.0128 | 0.652 | 0.977 | FAIL |
| SBERP | VTBR | 4 | 0.0536 | 0.059 | 0.382 | FAIL |
| SBERP | SBER | 4 | 0.0008 | 0.977 | 0.977 | FAIL |
| MGNT | CHMF | 5 | 0.0378 | 0.183 | 0.467 | FAIL |
| SBER | SBERP | 4 | 0.0017 | 0.954 | 0.977 | FAIL |
| FESH | NMTP | 3 | -0.0415 | 0.144 | 0.467 | FAIL |
| SBER | VTBR | 4 | 0.0593 | 0.037 | 0.382 | FAIL |
| VTBR | HYDR | 5 | 0.0076 | 0.789 | 0.977 | FAIL |
| NMTP | MRKC | 4 | 0.0422 | 0.137 | 0.467 | FAIL |
| SBERP | UPRO | 3 | 0.0051 | 0.857 | 0.977 | FAIL |
| MRKC | VSMO | 4 | -0.0352 | 0.215 | 0.467 | FAIL |
| MTLRP | MTLR | 2 | -0.0208 | 0.464 | 0.863 | FAIL |

**0/13 PASS.** Every discovered |r| shrank sharply toward zero out-of-sample
(largest survivor: SBER→VTBR at r=0.059, p=0.037 uncorrected — still fails
BH at q<0.05 once corrected for the 13-test family, p_bh=0.38). No
discrepancy between this correlation-screen re-test and the basket-wide
Chronos result — both independently land at "no signal."

### Observations

- Same outcome as the daily run (0/20 → now 0/13), despite the 1h
  discovery shortlist looking structurally more plausible pre-confirmation
  (spread across lags 2-5, not dominated by one lag the way the daily
  run's pre-fix result was). A cleaner-looking discovery shortlist did not
  translate into a better confirmation rate — consistent with the
  shortlist being exactly what BH-correction at q<0.05 across a large test
  family predicts: mostly discovery-window noise, residualization bug or
  not.
- The two same-issuer ordinary/preferred pairs (SBER↔SBERP, MTLR↔MTLRP)
  flagged pre-confirmation as possible microstructure artifacts also
  failed to replicate (r≈0.0008-0.0208, essentially zero) — so even the
  "most economically plausible" pairs in the shortlist showed no
  out-of-sample lead-lag, undercutting a possible objection that the
  screen was picking up something real but mechanical.
- This is the **fourth independent negative result** for lead-lag /
  cross-sectional structure in this MOEX universe, after Stage 2b (60m,
  12 tickers), Phase B (multivariate-vs-univariate gate, daily), and
  Phase C daily (lead-lag screen, daily). Two different bar frequencies
  (daily, 1h) and two different test designs (basket gate, pairwise
  lead-lag) now agree: no detectable cross-sectional or lead-lag structure
  in zero-shot Chronos-2 forecasts on this universe, at these frequencies,
  over this sample period.

## Next steps
1. ~~Run confirmation~~ done.
2. ~~Compute the per-pair confirmation test~~ done, 0/13 PASS.
3. Update `docs/exp_plan.md` §3b and `docs/current_state.md` with the final
   1h verdict (fourth negative result).
4. Per the user's prior sequencing decision: this closes out "all
   currently planned work" (the 1h follow-on was the last queued item
   before Phase E). Next is designing Phase E (burst-detection lead-lag),
   already queued in `docs/current_state.md` session entry 22 — proceeds
   regardless of this outcome per that entry's explicit sequencing, but
   this result is itself a relevant prior for that design: daily and 1h
   full-sample screens both find nothing, which is exactly the
   "stationarity assumption" this new hypothesis questions.
