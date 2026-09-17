# Phase E — event-conditioned burst detection, scratchpad

Detection-only follow-on after four full-sample negative results (Stage 2b, Phase B,
Phase C daily, Phase C 1h). Tests a genuinely different hypothesis: lead-lag
dependencies may not hold across the whole sample but occur in short, real bursts
that a full-sample correlation/DA number averages away. Full background, deferred
experiment families, and the statistical-safeguards checklist this design follows:
`docs/transient_dependency_research.md`. Design discussed with the user 2026-09-17
(scope: E1 then E2 only, defer experiments E-H and 10-minute-or-finer resolution).

## Pointer
- Core functions: `basic_cells.ipynb` §16 (`residualize_market_factor` — extracted
  from §14 for reuse, `detect_leader_events`, `event_conditioned_response`,
  `block_permute_panel`, `scan_pair_family`, `bh_correct`, `run_e2_discovery`,
  `run_e2_confirmation`, plus E1's synthetic-validation functions
  `make_synthetic_panel`/`inject_burst`/`e1_power_test`/`e1_null_false_alert_rate`).
- E1 runs automatically every time `basic_cells.ipynb` is sourced (§16's assertion
  cell) — E2's functions are not reachable without E1's assertions passing first.
- E2 driver: `runner.ipynb` §2c (discovery) + §2d (confirmation), no config file —
  pandas-only, no Chronos, no `run_stage`.
- Started: 2026-09-17
- Status: **done, NULL RESULT at discovery (2026-09-17)** — 0/11024 candidate
  (leader, follower, lag) hypotheses BH-significant in the discovery window.
  Confirmation stage not reached (nothing to confirm). Fifth independent negative
  result (after Stage 2b, Phase B, Phase C daily, Phase C 1h).

## Pre-registered design (locked in 2026-09-17, before running E2 on real data)

1. **Mechanism tested**: event-conditioned leader/follower response (research doc's
   Experiment A / "recommended primary claim"). At time `t`, `leader`'s
   market-residualized return exceeds `threshold_std=2.0` trailing standard
   deviations (causal — only past `min_history=60` bars used, never future data).
   `follower`'s residualized return `lag` bars later is checked for same-direction
   response. Statistic: fraction of qualifying events with same-direction response,
   tested against the 50% no-relationship null via a two-sided binomial test.
2. **Universe**: same 76-ticker 1h AlgoPack pull used for Phase C's 1h follow-on;
   53 tickers survive `build_price_panel`'s 0.9 coverage guard on this specific
   discovery-window slice (fewer than Phase C's 1h discovery, which used the same
   window and threshold but a different panel-build call — expected minor
   variation, not a bug, both draw from the identical underlying parquet).
3. **Discovery/confirmation split**: identical to Phase C's 1h follow-on —
   discovery 2023-01-02→2024-05-24 (2919 bars), confirmation 2024-05-27→2024-12-30
   — reusing the split, not the ticker shortlist (Phase C's shortlist was a
   different mechanism, a full-sample linear correlation screen; reusing it here
   would bias toward pairs already tested and failed for that other hypothesis).
4. **Candidate pairs**: every ordered pair among the 53 tickers (leader, follower
   both directions) × lags 1-4 = 53×52×4 = 11024 candidate tests. Not restricted to
   any prior shortlist.
5. **Event-count floor**: n≥85 qualifying leader-events required per candidate for
   eligibility, derived via binomial two-proportion power calculation (target
   effect: 65% same-direction response vs. 50% null, 80% power, α=0.05) — see
   `basic_cells.ipynb` §16 header for the full derivation and the real-data sanity
   check (SBER 1h, ~72 expected events at this threshold, close to the floor).
   Pairs below the floor are recorded as ineligible, not silently dropped.
6. **Shortlist rule**: BH-significant at q<0.05 across the full 11024-test discovery
   family (same BH pattern as §13/§14, `bh_correct` in §16).
7. **0 survivors is a valid, complete result** — same pre-registered rule as every
   prior phase in this project (Phase B decision, Phase C decisions 5).
8. **E1 gate**: E2's real-data functions are only trusted after E1's synthetic
   validation passes (both the injected-burst power test and the pure-null
   false-alert-rate test) — enforced structurally, not just by convention: E1's
   assertions run automatically as part of sourcing `basic_cells.ipynb` §16, before
   any of E2's functions are used.

## E1 — synthetic validation result (2026-09-17)

Both tests pass, run automatically on every notebook load:

- **E1a (injected-burst power test)**: 20 trials, 76-ticker synthetic panels
  matching the real universe's scale, a known injected 75%-same-direction
  relationship at lag=2. Result: `eligible_rate=1.0`, `detection_rate=1.0`,
  `mean_abs_frac_error=0.031` (estimated same_dir_frac vs. the 0.75 ground truth).
  The detector reliably recovers a known relationship when one exists.
- **E1b (null false-alert rate)**: 20 trials × 380 candidate pairs on PURE-NULL
  synthetic panels (no injected structure). Result: 0/7600 BH-significant hits
  (`overall_false_positive_rate=0.0`), comfortably under the nominal 5% ceiling —
  BH correction controls the false-alert rate on this detector, if anything
  conservatively.
- One real bug caught and fixed during E1 development: an early version of
  `inject_burst` used a different, non-causal event definition than
  `detect_leader_events`/`event_conditioned_response` actually use, causing only
  ~17-50% overlap between "injected" events and "detected" events — this diluted
  the measured detection rate to ~20% (looked like the detector barely worked) when
  the actual mechanism was fine. Fixed by making `inject_burst` detect events the
  same way the real pipeline does (residualized series, same trailing-std rule).
  Lesson: a synthetic positive-control test is only as good as how precisely its
  ground-truth injection matches what the detector will actually scan for — a
  mismatch here would have either hidden a working detector (this direction) or,
  worse, hidden a broken one, if the mismatch had gone the other way.

## E2 — discovery result (2026-09-17)

Ran `runner.ipynb` §2c on the real 1h panel, discovery window 2023-01-02→2024-05-24.

- 53/76 tickers survive the 0.9 coverage guard on this window (mostly recent-IPO
  and thinly-traded names dropped — same pattern as every prior phase).
- 2919 discovery bars, 11024 candidate (leader, follower, lag) tests.
- **100% of candidates cleared the n≥85 event floor** (`eligible_frac=1.0`) — the
  floor derivation was realistic for this universe/window, not a null result driven
  by an unreachable floor.
- **0/11024 BH-significant at q<0.05.**

No confirmation run needed — nothing survived discovery to confirm. Per the
pre-registered rule (decision 7), this is itself the complete result, not a partial
one requiring a threshold change and re-run.

## Interpretation

This is a genuinely different test from all four prior negative results — full
event-conditioning (not aggregate correlation), causal trailing-window detection
(not a single full-sample number), its own multiple-testing family and BH
correction, and a validated detector (E1) rather than an assumed-correct one. It
directly targets the hypothesis the user raised: "dependencies might not be
stationary, but occur in short bursts." At 1h resolution, 2σ leader-event
threshold, lags 1-4 bars, over this ~17-month discovery window, on 53 tickers: no
such bursts were found.

This does not close off the burst-detection hypothesis entirely — the research doc
(`docs/transient_dependency_research.md`) lists several dimensions not yet
explored: different threshold_std values, different lag ranges, regime
conditioning (Experiment C), volume-conditioned events, or finer resolution
(10-minute bars). But per the user's explicit "detection only, finish what's
planned" framing, and the project's standing discipline against p-hacking by
re-running with loosened parameters after a null, none of those should be tried
as an immediate "try again" — they'd need their own fresh pre-registration and
justification, not a retry of this exact test with a different knob.

## Next steps
1. ~~Build E1 (synthetic validation)~~ done, both tests pass.
2. ~~Run E2 discovery on real data~~ done, 0/11024 significant.
3. ~~Run E2 confirmation~~ not applicable (empty discovery shortlist).
4. Update `docs/exp_plan.md` and `docs/current_state.md` with the Phase E result.
5. Decide with the user: write up all five negative results as the project's
   deliverable, or design a specific, justified Phase E variant (different
   threshold/regime/resolution) with its own pre-registration.
