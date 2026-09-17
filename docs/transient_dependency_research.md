# Transient cross-asset dependencies — research notebook

## Research goal

Find rigorous evidence that dependencies between MOEX instruments appear for limited periods,
even if those dependencies are not stable over the full sample. The target claim is detection,
not necessarily a profitable trading strategy:

> Using only information available by time `t`, a frozen detector identifies a temporary
> leader/follower relationship whose effect continues in subsequent, unseen observations more
> often or more strongly than expected under an appropriate null model.

This is deliberately narrower than proving a causal mechanism. Price data can demonstrate a
replicable lagged association. Claiming that the association is caused by delayed investor
decisions requires additional evidence such as order flow, volume, ownership, or timestamped
news.

## What the completed experiments establish

Phase C gives strong negative evidence against **persistent daily linear lead-lag dependence**
at lags 1–5 in the tested universe and dates:

- 20 discovery pairs survived the original large screen, but 0/20 replicated in the later
  confirmation interval.
- Basket-level directional accuracy was approximately 0.508 and mean Pearson correlation was
  approximately -0.037.
- The earlier grouped-versus-independent experiment found essentially no average benefit from
  giving Chronos multiple ticker series together.

These results do **not** rule out:

- dependencies that exist only in short bursts;
- intraday delays that disappear by the daily close;
- event- or regime-conditioned dependencies;
- nonlinear or asymmetric relationships;
- dependencies expressed in volatility, volume, liquidity, or order flow rather than returns;
- changing leader, follower, lag, or sign across regimes;
- relationships outside the tested dates, tickers, or data fields.

The current directional-accuracy heat map is not itself a pair-dependency map. A green cell
means the model predicted one ticker's sign relatively often; it does not identify which other
ticker supplied useful information. With 72 inspected cells and 135 forecasts per cell, several
values around 0.55 are expected by chance. Such cells may nominate candidates, but they are not
evidence without an out-of-sample incremental comparison.

## Candidate economic and market mechanisms

Potential mechanisms worth testing separately:

1. **Slow reaction to a common shock.** Liquid or closely watched names react first; less liquid
   names react later.
2. **Sector information diffusion.** A shock to one oil, metals, banking, utility, or transport
   company changes expectations for peers.
3. **Commodity and FX transmission.** Brent, gold, USD/RUB, or futures move before exposed
   equities incorporate the information.
4. **Index and futures price discovery.** IMOEX/RTS futures or an index move before constituent
   shares.
5. **Institutional order splitting.** Similar decisions are executed gradually across related
   instruments, producing temporary serial and cross-serial dependence.
6. **Liquidity and stale prices.** Thinly traded shares appear to lag active shares because their
   observed prices update less frequently. This is a real statistical dependency but may be a
   microstructure artifact rather than exploitable information diffusion.
7. **Trading halts, auctions, and price limits.** One instrument is temporarily prevented from
   incorporating information.
8. **News propagation.** A company or macro announcement reaches and affects related instruments
   at different speeds.
9. **Index rebalancing, dividends, and corporate actions.** Scheduled events can create temporary
   common or sequential flows.
10. **Regime-dependent behavior.** High volatility, sanctions, capital controls, crises, or calm
    markets may have different dependency networks.
11. **Leadership switching.** The economic leader can change with liquidity, news source, or
    regime; a full-sample correlation then averages toward zero.
12. **Asymmetric transmission.** Dependence may exist only after negative shocks, positive shocks,
    unusually large moves, or high-volume moves.

Each mechanism should imply an observable trigger, lag range, controls, and expected sign before
the confirmation data are examined.

## Data resolutions and target variables

### Resolution priorities

1. **1-hour bars:** best immediate next step and already scaffolded. Delayed reaction over one to
   several hours is more plausible than over several days in liquid equities.
2. **10-minute bars:** useful if the 1-hour result suggests intraday structure. It creates a much
   larger multiple-testing and microstructure problem, so it should follow a frozen design.
3. **Daily bars:** still suitable for slower macro, commodity, or low-liquidity effects and for
   20–60 day regime windows.
4. **1-minute or trade/order-book data:** strongest for market microstructure questions, but only
   worthwhile with reliable timestamps, spreads, and sufficient liquidity.

### Possible response variables

- market- and sector-residual log return;
- cumulative residual return over the next `k` bars;
- realized volatility or absolute return;
- volume and relative-volume innovations;
- spread, depth, imbalance, or signed order flow when available;
- jump/event indicators rather than raw returns;
- probability of a follower move exceeding a practical effect-size threshold.

Returns should remain the first target, but volume/volatility dependencies could exist even when
return direction is unpredictable.

## Experiment families

### A. Event-conditioned leader/follower study

This is the cleanest first test of the stated hypothesis.

1. Residualize each instrument against market and, where possible, sector factors.
2. Define a leader event using only past data, for example:
   - absolute residual return above 2 rolling standard deviations;
   - optionally combined with relative volume above a fixed percentile;
   - separate positive and negative events.
3. Measure each candidate follower's residual return over the next 1–4 bars.
4. Compare the response with matched non-event periods and with block-permuted data.
5. Freeze leader/follower pairs, trigger, lag, and effect-size threshold in discovery.
6. Confirm on untouched dates.

Useful outputs:

- mean and median post-event response by lag;
- bootstrap confidence interval;
- probability of same-direction and opposite-direction response;
- response relative to matched controls;
- number of qualifying events;
- fraction of discovery effects that replicate with the same sign.

### B. Causal rolling-window detection

At every time `t`, compute pair statistics from a trailing window ending at `t`; never let the
window include future observations. Candidate daily windows are 20, 40, and 60 trading days.
Candidate 1-hour windows should be defined in bars and should span enough separate sessions to
avoid treating within-day observations as fully independent.

An alert is successful only when the relationship continues into a subsequent holdout block.
Merely finding a high historical rolling correlation is not evidence of detectability.

Possible detector statistics:

- lagged Pearson and Spearman correlation;
- lagged regression coefficient after controls;
- incremental out-of-sample `R²`;
- same-sign response probability after leader events;
- conditional mutual information;
- stability of the lag and sign across adjacent trailing windows.

### C. Regime-conditioned dependency

Define regimes without using future returns, then estimate relationships separately within them:

- market realized-volatility terciles;
- positive/negative market trend;
- high/low liquidity or volume;
- opening, middle, and closing session;
- commodity or FX shock periods;
- scheduled announcement windows;
- crisis versus normal periods;
- sector-relative momentum or dispersion regimes.

Regimes should be coarse, economically motivated, and frozen. Trying many arbitrary partitions
and retaining the best is another form of multiple testing.

### D. Predictive ablation

For a proposed pair `A -> B`, fit or run the same predictor twice on identical observations:

1. restricted model: history of `B` plus common controls;
2. augmented model: the restricted inputs plus lagged history of `A`.

The dependency statistic is the paired out-of-sample improvement:

`delta = score(augmented) - score(restricted)`.

This can use linear/regularized regression before Chronos. A simple model makes attribution
clearer. Chronos or another nonlinear model is useful later if direct tests locate a signal.

Possible scores include incremental `R²`, correlation, log loss for an event label, weighted
directional accuracy, and pinball-loss improvement. A raw accuracy above 0.5 is insufficient;
the augmented model must beat the restricted model on the same held-out cases.

### E. Dynamic dependency network

Represent instruments as nodes and validated lagged effects as directed edges. Track over time:

- edge appearance and disappearance;
- leader centrality;
- sector clustering;
- duration and recurrence of edges;
- whether changes align with volume, volatility, news, or market regimes.

Network plots are descriptive unless edge selection is calibrated against the complete search.
A useful statistic is whether the observed number, strength, or persistence of edges exceeds the
same maximum statistic in block-permuted panels.

### F. Change-point-first analysis

Instead of scanning every possible window, detect market or covariance change points using only
past observations. Test dependencies within the resulting regimes. This can reduce the number of
arbitrary window starts, but the change-point procedure itself must be included in the null
simulation and applied identically to real and randomized data.

### G. Nonlinear and asymmetric dependence

Only after the linear/event tests are fixed and reported, consider:

- quantile regression for tail effects;
- mutual information or conditional mutual information;
- nonlinear Granger-style prediction with regularization;
- tree/boosting models evaluated by strict ablation;
- copula or tail-dependence measures;
- separate positive and negative shock responses;
- volatility-spillover models;
- Hawkes/event-intensity models for timestamped jumps or order flow.

These methods increase flexibility and false-discovery risk. They should be judged only by
untouched out-of-sample improvement and compared with simple baselines.

### H. Natural experiments and mechanism evidence

For stronger causal interpretation, study events with a credible information ordering:

- timestamped company announcements affecting peers;
- a commodity/futures shock preceding related equities;
- temporary halt in one of two related instruments;
- exchange opening differences or auction releases;
- index-rebalancing announcements and implementation times.

An event study with known timestamps can support a delayed-reaction mechanism much more directly
than an unconstrained pair search.

## Covariates and controls

### High-priority controls

- IMOEX and relevant sector-index returns;
- leave-one-out market return;
- Brent, USD/RUB, gold, and appropriate futures returns;
- rolling realized volatility;
- hour of day, day of week, and session-open/close indicators;
- per-ticker relative volume;
- liquidity measures when available.

### Mechanism-specific additions

- Brent and USD/RUB **levels**, encoded as log levels or trailing z-scores rather than raw levels;
- sector aggregates constructed without the target ticker;
- market dispersion and correlation regime;
- news/announcement flags;
- futures basis or index-futures difference;
- order imbalance and signed flow;
- dividend, rebalance, halt, or corporate-action flags.

More covariates are not automatically better. Add them in small, pre-defined blocks and require
incremental held-out improvement. Large post-hoc searches over covariate subsets can manufacture
positive results.

## Window, lag, and context-size ideas

These parameters answer different questions and should not be conflated:

- **Correlation/detector window:** the trailing sample used to estimate whether a dependency is
  currently active. Short windows localize bursts but have high variance; long windows improve
  precision but dilute transient effects.
- **Lag:** the hypothesized delay between leader and follower. It should be matched to bar size
  and mechanism.
- **Model context length:** how much history Chronos or another predictor receives. Changing it
  cannot create evidence in the direct pairwise test; it only changes model behavior.
- **Confirmation block:** the future period used to decide whether an alert generalized.

A bounded discovery grid could include:

| Resolution | Detector windows | Candidate lags | Initial confirmation block |
|---|---:|---:|---:|
| Daily | 20, 40, 60 days | 1–5 days | 5–20 days |
| 1 hour | 10, 20, 40 sessions | 1–8 bars | 1–5 sessions |
| 10 minute | 5, 10, 20 sessions | 1–12 bars | 1–3 sessions |

These are starting candidates, not thresholds to optimize on the final test set. Prefer fewer,
economically meaningful choices over a dense grid.

## Metrics

No single metric is sufficient.

### Existence and effect size

- residual lagged correlation or beta;
- incremental out-of-sample `R²`;
- average post-event follower response;
- response divided by contemporaneous volatility;
- same-sign response probability;
- conditional mutual information;
- tail-event odds ratio.

### Detection quality

- precision: fraction of alerts followed by a valid effect;
- recall relative to retrospectively identified episodes;
- alert lead time;
- episode coverage and duration;
- false alerts per year;
- recurrence with the same leader, follower, lag, and sign.

### Forecast quality

- Pearson and Spearman correlation;
- directional accuracy and balanced accuracy;
- return-weighted directional accuracy;
- MAE/RMSE;
- pinball loss and interval coverage;
- augmented-minus-restricted paired score.

P&L after costs is optional for the current detection-only goal. If economic exploitability later
becomes a claim, costs, spread, liquidity, turnover, and execution delay become mandatory.

## Statistical safeguards

Transient-dependency research has an unusually large search space: pair × direction × lag ×
window × start time × regime × covariate set × metric. The following safeguards are essential.

1. **Nested chronological evaluation.** Use discovery to select the detector, a validation period
   to tune a small number of thresholds, and a final untouched confirmation period.
2. **Real-time legality.** At time `t`, every rolling statistic, scaling parameter, regime label,
   and covariate must use data available by `t`.
3. **Family definition.** Record every tested pair, lag, window, regime, metric, and model variant;
   correction must cover the actual search, not only the results retained for presentation.
4. **Hierarchical testing.** First test whether the full system produces more/stronger episodes
   than its null. Only then interpret individual pairs. This can be more powerful than correcting
   every cell in one enormous flat family.
5. **Block bootstrap/permutation.** Preserve serial dependence, cross-sectional common shocks,
   trading sessions, and intraday seasonality. Do not randomly shuffle individual bars.
6. **Maximum-statistic null.** Run the complete selection pipeline on each randomized panel and
   compare the best real result with the distribution of best null results. This automatically
   penalizes searching many windows and pairs.
7. **Effect-size floor.** Require economic or scientific relevance in addition to a p-value.
8. **Minimum observations/events.** Reject cells supported by too few sessions or leader events.
9. **Uncertainty for overlapping observations.** Use block methods or clustered/HAC errors;
   overlapping horizons are not independent.
10. **Negative controls.** Include random ticker pairings, impossible reverse-time lags, or
    intentionally unrelated assets to detect pipeline artifacts.
11. **Positive controls.** Verify on synthetic data with injected temporary dependencies of known
    start, end, lag, sign, and strength. Report detection power, delay, and false-alert rate.
12. **Robustness without result shopping.** Sensitivity checks should show nearby parameter
    behavior, not redefine success after observing the test set.

## Important confounders and failure modes

- A common market factor can create apparent pairwise lead-lag relationships.
- Non-synchronous or stale prices can manufacture lagged correlation.
- Intraday seasonality can create same-lag effects across unrelated instruments.
- Corporate actions, bad candles, and futures-roll jumps can dominate correlations.
- Survivorship and coverage filters can change the tested universe.
- Reusing overlapping forecasts exaggerates the effective sample size.
- Selecting the best window after viewing the full history is look-ahead bias.
- Repeatedly modifying the design after a failed confirmation is p-hacking unless a new untouched
  test period is reserved.
- Multiple significant cells from the same ticker and overlapping horizons are correlated, not
  independent replications.
- A predictive association may reflect a shared omitted cause rather than `A` causing `B`.

## Evidence levels

Use explicit language matched to the strength of the result:

1. **Descriptive episode:** a relationship is visible retrospectively.
2. **Discovery candidate:** it passes a corrected discovery screen.
3. **Replicated association:** the same frozen effect appears in an untouched period.
4. **Real-time detectable episode:** a frozen trailing-data rule alerts before the confirmation
   effect is observed and beats its calibrated null.
5. **Mechanistic evidence:** timestamped events, order flow, or a natural experiment support a
   particular delayed-decision explanation.
6. **Exploitable edge:** a feasible strategy remains positive after costs and execution limits.

The present goal is level 4. Level 4 proves that temporary structure can be detected without
claiming causality or profitability.

## Proposed Phase E sequence

### E0 — finish the already-scaffolded 1-hour follow-on

- Run the 1-hour data pull, discovery screen, and independent confirmation exactly as currently
  specified.
- Preserve the result whether positive or negative.
- Do not use it as an opportunity to retune the daily Phase C test.

### E1 — synthetic validation

- Generate panels with realistic common-market structure and temporary injected edges.
- Vary episode length, lag, effect size, volatility, and liquidity.
- Verify that the detector controls false alerts on null panels and measure its power and delay.

### E2 — simple event-conditioned MVP

- Start at 1-hour resolution.
- Use market/sector-residual returns.
- Use one pre-defined leader-shock threshold, one volume condition, and lags 1–4.
- Compare follower responses with block-permuted and matched-event nulls.
- Select a small candidate set in discovery; freeze it before confirmation.

### E3 — rolling real-time detector

- Add bounded trailing windows and an edge-stability requirement.
- Calibrate an alert threshold using the maximum statistic from the full randomized pipeline.
- Score alerts only in subsequent blocks.

### E4 — regime and covariate ablations

- Add volatility/session/commodity regimes one block at a time.
- Compare restricted and augmented predictors on identical observations.
- Retain only effects that improve held-out performance and have adequate event counts.

### E5 — nonlinear or richer-data extensions

- Apply nonlinear/tail methods only to hypotheses localized by E2–E4.
- If available, add news timestamps, order flow, spreads, and depth to investigate mechanism.

## Example pre-registration template

Before each confirmation run, record:

- scientific hypothesis and proposed mechanism;
- universe and exact date splits;
- bar resolution and session handling;
- target and residualization method;
- leader-event definition;
- candidate pairs and direction;
- lags, trailing windows, and confirmation horizon;
- all covariate blocks;
- primary metric and minimum effect size;
- minimum event count;
- null-generation method and number of resamples;
- complete multiple-testing family and correction method;
- success criterion;
- permitted diagnostics after failure;
- statement that the final period will not be reused for redesign.

## Recommended primary claim and test

The most defensible first positive target is:

> At 1-hour resolution, after unusually large market-adjusted moves accompanied by high relative
> volume in a pre-selected leader, one or more pre-selected followers exhibit a same-signed
> residual response over the next 1–4 bars. A detector defined in the discovery period identifies
> these episodes using only trailing information and produces a larger held-out effect than the
> 95th percentile of the complete block-permuted selection pipeline.

This claim directly represents temporary delayed reaction, makes no unnecessary profitability or
causality claim, and can be falsified cleanly.

## Decision rule for future ideas

A modification is legitimate when it tests a substantively different, pre-specified hypothesis
on untouched data—for example, changing from persistent daily correlation to event-conditioned
1-hour diffusion. A modification is not legitimate when it merely searches more thresholds,
windows, covariates, or metrics until the same test becomes significant.

