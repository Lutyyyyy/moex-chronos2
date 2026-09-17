# Sector-basket multivariate experiment, scratchpad

Not a numbered Phase (A-E already used) — a targeted follow-on the user proposed
after seeing Phase B's cross-sector multivariate arm come back null (and the
per-window clustering check confirming no hidden localized effect either, see
`docs/current_state.md` entry 28). Tests a specific, different hypothesis:
Chronos-2's multivariate cross-attention might benefit from real economic
relatedness between the series it attends over. Phase B's 16-ticker basket was
deliberately cross-sector and liquidity-diverse (by design, to avoid testing on
one correlated cluster) — which could, in principle, be close to a worst-case
input for a mechanism that benefits from relatedness. This experiment tests the
opposite composition: baskets drawn entirely from one sector.

## Pointer
- Configs: `configs/phase_sector_<sector>_{multivariate,univariate}.yaml`, one
  pair per sector.
- Started: 2026-09-17

## Pre-registered design (locked in before any run)

1. **Sector classification**: verified via a research agent (not guessed) against
   MOEX/company sources 2026-09-17, since no sector map was ever persisted from
   Phase B's original manual classification (it was ephemeral, encoded directly
   into that phase's 22-ticker list, never saved as a reusable artifact). Full
   classification of all 80 `equity_universe.yaml` tickers:

   | Sector | Tickers | n |
   |---|---|---|
   | oil_gas | GAZP, ROSN, LKOH, NVTK, TATN, SNGS, SNGSP, TATNP, SIBN, RNFT, BANEP, TRNFP | 12 |
   | metals_mining | PLZL, GMKN, MAGN, ALRS, NLMK, CHMF, RUAL, MTLR, MTLRP, SELG, UGLD, ENPG, RASP, VSMO | 14 |
   | financials | SBER, SBERP, T, VTBR, SVCB, SPBE, MOEX, BSPB, DOMRF, CBOM, RENI | 11 |
   | tech | YDEX, VKCO, POSI, HEAD, ASTR | 5 |
   | telecom | MTSS, RTKM, RTKMP | 3 |
   | retail | OZON, X5, MGNT, LENT, MVID, BELU | 6 |
   | transport | AFLT, FLOT, FESH, NMTP, WUSH, DELI | 6 |
   | utilities | IRAO, FEES, UPRO, HYDR, MSNG, MRKC, MSRS, TORS | 8 |
   | chemicals | PHOR | 1 |
   | healthcare | MDMG, PRMD, OZPH | 3 |
   | realestate | SMLT, PIKK, CNRU | 3 |
   | aerospace_defense | IRKT, UNAC | 2 |
   | agriculture | RAGR | 1 |
   | other_industrial | SGZH, UWGN | 2 |
   | conglomerate (excluded) | AFKS, SFIN | 2 |
   | borderline oil_gas (excluded from main bucket) | EUTR | 1 |

   **Flagged uncertainties from the research agent, kept in mind for interpretation**:
   - AFKS (Sistema) and SFIN (SFI) are genuine multi-sector holding companies —
     excluded entirely from sector baskets rather than force-fit into one sector.
   - WUSH (Whoosh, micromobility) and DELI (Delimobil, carsharing) both tagged
     "transport" for labeling consistency (some sources split them tech/transport)
     — not used in this run's sectors anyway (transport was dropped, see below).
   - ENPG (En+ Group) and RUAL (Rusal) are financially linked (En+ controls
     Rusal) — both land in metals_mining here, meaning that basket isn't purely
     independent diversification; a pairing between them specifically shouldn't be
     over-interpreted as "sector" correlation if it shows up.
   - OZPH (Ozon Pharmaceuticals) confirmed distinct from OZON (Ozon Holdings,
     e-commerce) despite the similar name/ticker — not the same company.
   - Preferred-share pairs (SBERP, SNGSP, TATNP, MTLRP, BANEP) carry their
     ordinary counterpart's sector — correct for classification, but they're
     economically distinct instruments (different dividend rights/liquidity).

2. **Basket size**: NOT fixed across sectors (a strictly fixed N turned out to
   exclude most sectors — only 4 of 14 real sector buckets have ≥8 tickers).
   Decision (discussed with the user): use each qualifying sector's full
   available ticker count, restricted to sectors with ≥5 tickers pre-coverage.
3. **Sectors run**: after checking REAL coverage survival (below), only 4 of the
   7 initially-qualifying sectors have enough tickers left to be a meaningful
   test — **oil_gas, metals_mining, financials, utilities**. Tech (5→2),
   retail (6→3), transport (6→3) dropped: too thin post-coverage to test
   cross-attention meaningfully (2-3 series is barely more than a pairwise test).
4. **Coverage check** (`build_price_panel`'s 0.9 raw-coverage guard, same daily
   2020-2024 panel as Phase B/C):

   | Sector | Configured | Survives | Final tickers |
   |---|---|---|---|
   | oil_gas | 12 | 12 | GAZP, ROSN, LKOH, NVTK, TATN, SNGS, SNGSP, TATNP, SIBN, RNFT, BANEP, TRNFP |
   | metals_mining | 14 | 13 | PLZL, GMKN, MAGN, ALRS, NLMK, CHMF, RUAL, MTLR, MTLRP, SELG, ENPG, RASP, VSMO (UGLD dropped, coverage=0.216) |
   | financials | 11 | 7 | SBER, SBERP, T, VTBR, MOEX, BSPB, CBOM (SVCB/SPBE/DOMRF/RENI dropped, recent listings) |
   | utilities | 8 | 8 | IRAO, FEES, UPRO, HYDR, MSNG, MRKC, MSRS, TORS |

5. **Design mirrors Phase B exactly** except ticker composition: same
   `context_len=250`, `horizon=5`, `max_windows=400`, `covariates=full`, same
   indexes/futures_proxies, same daily 2020-2024 window, same paired
   multivariate/univariate configs (identical except `group_mode`, matching
   `mcnemar_gate_test`'s pairing requirement). This keeps the comparison clean:
   the ONLY deliberate difference from Phase B is basket composition
   (homogeneous-sector vs. Phase B's cross-sector diverse basket).
6. **Success criterion**: same three-part gate shape as Phase B — per sector,
   PASS requires aggregate ΔDA > 0 AND ≥1 BH-significant (ticker, horizon) cell
   favoring multivariate (via `mcnemar_gate_test`, §13, already built and
   verified) AND multivariate still beats the `last` baseline. Each sector is
   its own independent test — not pooled into one BH family across sectors,
   since each sector's basket is a genuinely different hypothesis instance
   (different tickers, different implicit "does this specific sector show
   cross-attention benefit" question), matching how Phase B's own gate was a
   single self-contained test, not a multi-cell family across baskets.
7. **0/4 sectors passing is a valid, complete result** — same discipline as
   every other phase in this project. Given tech/retail/transport were already
   dropped for insufficient coverage (not for looking unpromising), there's no
   temptation to drop more sectors after seeing results — the 4 tested here are
   fixed before any run.

## Next steps
1. User runs all 8 configs (`runner.ipynb` §3, one CONFIG_PATH edit + run per
   config) — 4 sectors × 2 arms.
2. For each sector, run `mcnemar_gate_test` on the paired preds.parquet outputs
   (same reusable function Phase B's gate used).
3. Report per-sector PASS/FAIL, write up in this scratchpad.
