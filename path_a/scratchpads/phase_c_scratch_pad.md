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
- Status: `pending` — waiting on the 80-ticker AlgoPack pull (`algo_data`
  `config.md`, already widened 22→80, not yet run) before discovery can start.

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
None yet — plan followed as written (rev. 3).

## Run log
| Date | Stage | Notes / changes since last run |
|------|-------|--------------------------------|
| 2026-09-17 | pre-registration | Design locked in above, before any code run or data looked at. `algo_data/config.md` widened 22→80 tickers; pull not yet executed by the user (manual-run policy — see plan/CLAUDE.md). |

## Discovery results (fill in after running §14 against the 2020-01-03..2023-06-30 slice)
```
(paste pairwise_lagged_xcorr / select_pair_shortlist summary here)
```

### Shortlist (from `select_pair_shortlist`)
| ticker_i | ticker_j | lag | direction | leader | follower | r | p_value_bh |
|----------|----------|-----|-----------|--------|----------|---|------------|

## Confirmation results (fill in after running `phase_c_leadlag_confirm.yaml`)
```
(paste summary.json here)
```

### Per-pair confirmation outcome
| pair | DA | pearson | p_bh (confirmation family) | beats `last`? | PASS/FAIL |
|------|----|---------|-----------------------------|----------------|-----------|

## Plots checked
- [ ] `plots/da_heatmap.png`
- [ ] `plots/da_vs_last.png`
- [ ] `plots/corr_hist.png`
- [ ] `plots/amplitude.png`
- [ ] `plots/coverage.png`
- [ ] `plots/examples.png`

## Observations
(fill in after running)

## Decision / Next
(fill in after running — if 0 survivors at discovery, this is a complete
answer per decision 5 above: write up and stop, do not loosen the rule.)
