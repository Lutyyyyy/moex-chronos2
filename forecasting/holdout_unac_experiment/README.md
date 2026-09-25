# Holdout test: UNAC ctx=100 anomaly — resolved

**Result: the anomaly did not replicate.** See [FINDINGS.md](../../FINDINGS.md)'s lead-lag
confirmation section for the full write-up. Kept here as the actual config and process
behind that result.

## What was being tested

`leadlag_confirm_adj_ctx100.yaml`'s confirmation run found UNAC BH-significant at all 4
evaluated horizons (DA 0.60–0.64, beats every baseline) — on its own, a result that clears
every leg of this project's pre-registered gate. But the same ticker, same confirmation
window, tested at `context_len=35` and `context_len=250` instead, was null in both. A
within-window stability check (splitting the ctx=100 confirmation windows into
halves/quarters) showed the effect held up internally rather than being one lucky cluster —
so this wasn't a settled false positive, and it wasn't a confirmed discovery either. It was
genuinely ambiguous on the data tested so far, so the only way to actually resolve it was to
test the same (ticker, context_len) combination on **data nobody had looked at yet**.

## What was run

`configs/leadlag_confirm_adj_ctx100_holdout2025.yaml` — identical to
`leadlag_confirm_adj_ctx100.yaml` (same 18-ticker family, same `context_len=100`, same
covariates/quantiles/baselines) except the date range: 2024-11-01 → 2026-09-17, strictly
after everything discovery/confirmation/the context-length sweep had touched
(2020-02-21 → 2024-12-30 combined). Required extending `data_pipeline`'s pull
(`config.md`'s `period.end` widened from `2024-12-31` to `today`) to fetch the new ~21
months of daily candles.

## Result

385 scorable windows (more than either original run). UNAC's DA dropped from 0.60–0.64 to
0.545–0.569, and none of its four horizons survived BH correction (best p_bh=0.26, nowhere
near 0.05). No other ticker in the 18-ticker family came back significant either.

0.545–0.569 is still the top 4 cells out of 72 tested, so "not BH-significant" alone isn't a
full explanation — it was checked further rather than left there. Two things closed it:
(1) under a pure global null, the chance that *some* cell among 72 looks this extreme by pure
luck is ≈44% (from the single best cell's raw p≈0.008), so this level of result is a
plausible, unremarkable draw from noise, not something that requires a real effect to explain;
and (2) the mechanism is directly identifiable in UNAC's own price series — a lag-1 return
autocorrelation of 0.222 in the original confirmation window (vs. 0.054–0.068 elsewhere),
driven by a real +157% spike in August 2023 followed by a ~9-month one-directional unwind. A
zero-information "yesterday's sign predicts h=2 sign" rule tracks the same rise-and-fall
pattern Chronos showed (0.535 in the confirmation window → 0.478, below chance, in the
holdout). This points to a transient, idiosyncratic momentum regime in UNAC's own history,
not a cross-asset lead-lag dependency — which is what this test family was built to detect.

Full numbers, reasoning, and how this fits into the project's overall findings are in
[FINDINGS.md](../../FINDINGS.md).
