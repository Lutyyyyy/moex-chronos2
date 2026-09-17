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
- E2 driver (1h): `runner.ipynb` §2c (discovery) + §2d (confirmation).
- E2 driver (daily): `runner.ipynb` §2e (discovery) + §2f (confirmation), same
  mechanism, re-derived parameters (see below). All pandas-only, no Chronos, no
  `run_stage`.
- Started: 2026-09-17
- Status: **done, NULL RESULT at both resolutions (2026-09-17)**. 1h: 0/11024
  candidates significant at discovery, confirmation not reached. Daily: 3
  candidates at discovery, 0 confirmable (all below the confirmation event floor),
  0 significant. Fifth independent negative result (after Stage 2b, Phase B, Phase
  C daily, Phase C 1h) — this entry covers both the 1h and daily E2 runs.

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

## E2 (1h) — discovery result (2026-09-17)

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

## E2 (daily) — design, discovery, and confirmation result (2026-09-17)

User asked to also run the daily equivalent. Daily bars needed their own re-derived
design, not a resolution swap on the 1h parameters — a 2σ threshold gives only
~9-16 expected events per ticker over a comparable window (or ~56 over the FULL
2020-2024 history), far under the n≥85 floor. Re-derivation (discussed and agreed
with the user before running):

- **`threshold_std=1.25`** (vs. 1h's 2.0) — a "notable move" threshold rather than
  a strict shock (1.25σ happens ~21% of days vs. 2σ's ~4.5%), needed to generate
  enough events on daily's much sparser bar count.
- **70/30 split of the FULL 2020-2024 history** (1249 bars total) rather than a
  shorter sub-window — daily doesn't have bars to spare. Discovery
  2020-01-03→2023-07-17 (874 bars), confirmation 2023-07-18→2024-12-30 (375 bars),
  verified zero overlap. Not identical to Phase C's daily split (2020-01-03/
  2023-06-30/2023-07-01/2024-12-30) — re-derived independently for this test's own
  70/30 target, not copied.
- **Floor n≥79**, derived via the same binomial two-proportion power calculation as
  1h's floor (target ~66% same-direction effect, 80% power, α=0.05), but set by the
  CONFIRMATION window's achievable event count (~79 expected at threshold_std=1.25
  over 375 bars) rather than discovery's — confirmation is the binding constraint
  at daily resolution (discovery gets ~185 events, comfortably above the floor;
  confirmation does not have that same headroom, unlike 1h where both sides had
  large margins).
- **Lags 1-4 trading days** (not hours) — Phase C's daily economic story
  (multi-day propagation), not 1h's intraday one.

**Discovery** (`runner.ipynb` §2e): 55/76 tickers survive coverage, 887 discovery
bars (2020-02-21→2023-07-17 — shorter than the nominal 874-bar target since
`build_price_panel`'s inner-join trims to the intersection of all 55 tickers'
coverage), 11880 candidate tests, 100% cleared the floor. **3 BH-significant
hypotheses** (q<0.05):

| leader | follower | lag | n_events (disc.) | same_dir_frac | p_value_bh |
|---|---|---|---|---|---|
| SBER | SFIN | 2 | 140 | 0.279 | 0.0019 |
| CHMF | ROSN | 2 | 137 | 0.307 | 0.0375 |
| SBERP | VSMO | 2 | 141 | 0.312 | 0.0375 |

Notable: all 3 show `same_dir_frac` well BELOW 50% (0.28-0.31), i.e. an
**opposite-direction** pattern (follower tends to move against the leader 2 days
later), not the same-direction burst the floor was originally framed around. The
binomial test is two-sided, so it correctly caught this — a real, if unexpected,
discovery-phase pattern, not a bug.

**Confirmation** (`runner.ipynb` §2f, window 2023-07-19→2024-12-30, 379 bars):

| leader | follower | n_events (confirm.) | eligible | same_dir_frac | p_value_bh_confirm | confirmed |
|---|---|---|---|---|---|---|
| SBER | SFIN | 60 | **False** | 0.417 | 0.434 | False |
| CHMF | ROSN | 44 | **False** | 0.477 | 0.880 | False |
| SBERP | VSMO | 57 | **False** | 0.421 | 0.434 | False |

**0/3 confirmed — and critically, none of the 3 were even eligible for a properly
powered confirmation test** (44-60 confirmation-window events, all below the n≥79
floor). This is a materially different and weaker outcome than "tested and failed"
— the honest statement is "the discovery-phase pattern could not be adequately
re-tested in the confirmation window at all," not "we tested it and it didn't
replicate," though both `same_dir_frac` values regressing hard toward ~0.42-0.48
(much closer to the 0.50 no-relationship value than the ~0.30 discovery-phase
reading) is at least suggestive that the discovery pattern was not a real, stable
effect even setting the power question aside.

**Bug caught and fixed during this run**: `run_e2_confirmation`'s `confirmed` flag
was computed purely from BH significance, without checking `eligible` — meaning a
pair under the confirmation-window event floor that happened to clear BH by chance
would have been incorrectly marked "confirmed," contradicting the function's own
docstring ("marked ineligible/FAIL, not dropped"). Didn't change this run's outcome
(none were BH-significant either), but is a real latent bug fixed before it could
produce a false positive in a future run. Fixed by AND-ing `confirmed` with
`eligible` explicitly.

## E2 (daily, v2) — loosened threshold re-run (2026-09-17)

User asked to loosen the criteria and try again, after seeing the v1 result above
(3 discovery candidates, none confirmable — a power shortfall, not a clean null).
Flagged before running: re-testing the SAME 3 v1 candidates on the SAME
confirmation window with a looser floor would not be a valid test (we'd already
seen those numbers — same_dir_frac 0.42-0.48, clearly regressing toward null). User
agreed to a genuinely fresh run instead: new `threshold_std`, full re-derivation,
new discovery AND new confirmation, not just re-checking known numbers under a
looser bar.

**Re-derived parameters**: `threshold_std=1.0` (down from 1.25 — still an
above-median move, the outer ~32% of days, not "any day"), floor **n≥90** (derived
the same way, with headroom above the exact ~85-event power-calc minimum at this
threshold's ~119 expected confirmation-window events). Same 70/30 full-history
split (874/375 bars) and same lags (1-4 days) as v1 — only the event definition
and floor changed.

**Discovery result**: 887 bars, 55 tickers (same panel as v1 — only the threshold
changed), 11880 candidate tests, **100% eligible** (more headroom than v1's already
resolvedly full 100%) — and **0/11880 BH-significant**. Not just "the 3 v1
candidates dropped out" — nothing at all replaces them; a strictly more powerful
test (more events, same rigor) found nothing where the weaker v1 test found 3
marginal, unconfirmable candidates. Confirmation stage not reached — nothing to
confirm.

**This is a cleaner, more decisive negative result than v1.** v1 left a genuinely
ambiguous finding (3 candidates that couldn't be properly tested one way or the
other — "insufficient power," not "no effect"). v2, with meaningfully more
statistical power and the same discipline, resolves that ambiguity: no
event-conditioned burst structure survives even a fairer look. Both v1's 3
candidates and any new candidates that a looser threshold might have picked up are
absent here.

## Interpretation

This is a genuinely different test from all four prior negative results — full
event-conditioning (not aggregate correlation), causal trailing-window detection
(not a single full-sample number), its own multiple-testing family and BH
correction, and a validated detector (E1) rather than an assumed-correct one. It
directly targets the hypothesis the user raised: "dependencies might not be
stationary, but occur in short bursts."

- **1h**: 2σ leader-event threshold, lags 1-4 bars, ~17-month discovery window, 53
  tickers — no significant bursts found at discovery (0/11024).
- **Daily v1**: 1.25σ threshold (re-derived, not copied — 2σ was infeasible at
  daily's bar count), lags 1-4 days, full 2020-2024 history, 55 tickers — 3
  candidates found at discovery, but **none could be adequately re-tested in
  confirmation** (all 3 fell below the confirmation-window event floor) and none
  were BH-significant there either. The honest characterization was not "0/3
  confirmed as failed replications" but "3 discovery candidates, 0 properly
  testable, 0 significant regardless" — an ambiguous, underpowered negative.
- **Daily v2 (loosened, 2026-09-17)**: `threshold_std=1.0`, floor n≥90 — more
  events, more power, same 70/30 split and lags. **0/11880 significant at
  discovery** — a strictly cleaner result than v1: not just "the 3 marginal
  candidates disappeared," but no new candidates emerged either, despite
  meaningfully more statistical power to find them if they existed.
- All three runs (1h, daily v1, daily v2) land at the same practical conclusion —
  no confirmable event-conditioned burst structure found — but daily v2 is the
  first daily result to match 1h's decisiveness (a clean discovery-stage null with
  adequate power, not an ambiguous underpowered one). Going from v1 to v2
  illustrates the tradeoff directly: v1's stricter threshold (1.25σ) was more
  economically meaningful ("real shocks only") but couldn't generate enough
  confirmation-window events to test its own candidates; v2's looser threshold
  (1.0σ, still an above-median move, not "any day") traded some of that economic
  specificity for enough power to get a clean answer — and that answer was null.

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
2. ~~Run E2 discovery on real 1h data~~ done, 0/11024 significant.
3. ~~Run E2 confirmation (1h)~~ not applicable (empty discovery shortlist).
4. ~~Run E2 discovery + confirmation on daily data (re-derived design)~~ done —
   3 discovery candidates, 0 confirmable (all below the confirmation event floor),
   0 significant. Caught and fixed a latent bug in `run_e2_confirmation`'s
   `confirmed` flag (wasn't checking `eligible`) along the way.
5. Update `docs/exp_plan.md` and `docs/current_state.md` with both results.
6. Decide with the user: write up all five negative results as the project's
   deliverable, or design a specific, justified Phase E variant (different
   threshold/regime/resolution) with its own pre-registration.
