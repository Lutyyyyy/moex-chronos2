#!/usr/bin/env bash
# Unattended runbook for the remaining alpha-experiment work (stops BEFORE the holdout).
# Usage (from repo root):  nohup caffeinate -i bash forecasting/alpha_experiment/run_all.sh > forecasting/runs/run_all.out 2>&1 &
# Progress:                tail -f forecasting/runs/runbook_logs/*.log
# Re-runnable: every stage skips work whose outputs already exist (forecasts are cached).
set -euo pipefail
cd "$(dirname "$0")/../.."
PY=.venv/bin/python
RUN="$PY forecasting/alpha_experiment/alpha_run.py"
LOG=forecasting/runs/runbook_logs; mkdir -p "$LOG"
stamp() { date "+%Y-%m-%d %H:%M:%S"; }

echo "$(stamp) step 0: tests"
$PY -m pytest forecasting/alpha_experiment/tests -q > "$LOG/00_tests.log" 2>&1

echo "$(stamp) step 1: wait for any running config sweep, then finish it (C0-C4 forecasts + configs_map.csv)"
while pgrep -f "alpha_run.py configs" > /dev/null; do sleep 60; done
$RUN configs > "$LOG/01_configs.log" 2>&1

echo "$(stamp) step 2: select winners (pre-stated rules) -> C3 context follow-up -> step 3 incl. extended mimic on winners"
$RUN select > "$LOG/02_select.log" 2>&1

echo "$(stamp) step 3: quantile-shape check on the Track A winner (if not the baseline)"
WIN_A=$($PY -c "import json;print(json.load(open('forecasting/runs/alpha_variants/winners.json'))['track_a'])")
if [ "$WIN_A" != "uni" ]; then $RUN qshape "$WIN_A" > "$LOG/03_qshape_${WIN_A}.log" 2>&1; fi

echo "$(stamp) step 4: refresh vol attribution (cheap; cached)"
$RUN volattr > "$LOG/04_volattr.log" 2>&1

echo "$(stamp) step 5: summary"
$PY - > "$LOG/05_summary.log" 2>&1 <<'PYEOF'
import json, pandas as pd
pd.set_option("display.width", 250)
R = "forecasting/runs/"
W = json.load(open(R + "alpha_variants/winners.json")); print("winners:", W)
T = pd.read_csv(R + "alpha_variants/configs_map.csv", index_col=0)
cols = ["phase", "MED_SIG_ic", "fm_t", "fm_t_over_uni", "span_alpha_t", "ls_net_sharpe", "ls_turnover",
        "qlike_scaled", "qlike_sc_dm_t_vs_uni", "coverage_vs_base"]
print(T[[c for c in cols if c in T.columns]].round(3).to_string())
for cfg in sorted(set(W.values())):
    t = pd.read_csv(R + f"alpha_improve/{cfg}/improve_table.csv", index_col=0)
    print(f"\n== step 3 on {cfg} =="); print(t[["ic", "ic_t", "ls_net_sharpe", "turnover", "span_alpha_t", "fm_t"]].round(3).to_string())
    print(json.load(open(R + f"alpha_improve/{cfg}/improve_extra.json")))
print("\nDECISION RULE (return alpha): dead unless the winner's 'chronos_minus_mimic_ext' row has fm_t > 2.")
PYEOF
cat "$LOG/05_summary.log"
echo "$(stamp) done. Holdout NOT run (needs a pre-registration decision; see tmp/plans/alpha_experiment_handoff.md)."
