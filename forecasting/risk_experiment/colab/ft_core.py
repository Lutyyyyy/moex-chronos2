"""LoRA fine-tuning protocol for the risk study (plan v3, sources F1/F2). Runs in Colab from a bundle.
Also importable locally, where the tests drive it with a fake pipeline.

Protocol (fixed before any fine-tuned result is seen)
- Targets: F1 = log-RV (one variate per stock), F2 = [return, log-RV] (two variates per stock).
  Both are forecast with cross_learning=True, context 250 and H=5, like their zero-shot twins Z3 and N1,
  so the comparison isolates fine-tuning.
- Causal yearly refits: the model for year y is trained only on data <= Dec 31 of y-1
  (dev: 2022..2024; holdout: 2025, 2026). No 2021 fold: the data start on 2020-01-03, so before its
  training end (2020-10-06) no series reaches CTX+H observations (plan deviation E4, approved).
- Inner validation: the last VAL_DAYS trading days before the cutoff are held out of training. Validation
  series end every VAL_STRIDE days inside that block (target windows end <= cutoff). The Trainer evaluates
  every 100 steps and keeps the best checkpoint (load_best_model_at_end).
- Hyperparameters: LoRA (default r=8, alpha=16 on attention q/k/v/o + output layer) with learning rate in
  LR_GRID, and NUM_STEPS as the upper bound. The lr with the lowest best eval loss is chosen per fold.
  The evaluation year is never used for any choice.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
for p in (HERE, HERE.parent, HERE.parents[1] / "alpha_experiment"):      # bundle layout or repo layout
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))
import chronos_sources as cs  # noqa: E402

TARGETS = {"F1": ["logrv"], "F2": ["ret", "logrv"]}
CTX, H = 250, 5
LR_GRID = (1e-5, 3e-5, 1e-4)
NUM_STEPS = 1000
VAL_DAYS, VAL_STRIDE = 60, 5
FOLDS = {"dev": {2022: "2021-12-31", 2023: "2022-12-31", 2024: "2023-12-31"},
         "holdout": {2025: "2024-12-31", 2026: "2025-12-31"}}


def _series_dates(first: pd.Series, end) -> pd.DatetimeIndex:
    return first.loc[:end].dropna().index


def training_inputs(panels: dict, cutoff, variates: list, min_len: int = CTX + H) -> tuple[list, dict]:
    """Per ticker, the full observed history up to the training end (cutoff minus VAL_DAYS trading days),
    as a 1-D (one variate) or 2-D (variates x T) float32 array. Tickers with fewer than `min_len` points
    are dropped. Returns (inputs, info)."""
    first = panels[variates[0]]
    cal = first.index[first.index <= pd.Timestamp(cutoff)]
    train_end = cal[-VAL_DAYS - 1]
    inputs, used = [], []
    for t in first.columns:
        idx = _series_dates(first[t], train_end)
        if len(idx) < min_len:
            continue
        rows = [panels[v][t].reindex(idx).ffill().fillna(0.0).to_numpy() for v in variates]
        x = np.vstack(rows).astype(np.float32)
        inputs.append(x[0] if len(variates) == 1 else x)
        used.append(t)
    return inputs, {"train_end": str(train_end.date()), "tickers": used}


def validation_inputs(panels: dict, cutoff, variates: list, min_len: int = CTX + H) -> tuple[list, dict]:
    """Truncated copies of each ticker's history ending every VAL_STRIDE trading days inside the validation
    block (after train_end, <= cutoff). In VALIDATION mode Chronos uses the last H points of each copy as
    the target, so every validation target lies after the training data and on or before the cutoff."""
    first = panels[variates[0]]
    cal = first.index[first.index <= pd.Timestamp(cutoff)]
    train_end = cal[-VAL_DAYS - 1]
    ends = cal[cal > train_end][H - 1::VAL_STRIDE]                 # a target window of H days after train_end
    inputs = []
    for t in first.columns:
        for e in ends:
            idx = _series_dates(first[t], e)
            if len(idx) < min_len or idx[-H] <= train_end:
                continue
            idx = idx[-(CTX + H):]
            rows = [panels[v][t].reindex(idx).ffill().fillna(0.0).to_numpy() for v in variates]
            x = np.vstack(rows).astype(np.float32)
            inputs.append(x[0] if len(variates) == 1 else x)
    return inputs, {"val_block": [str(cal[cal > train_end][0].date()), str(cal[-1].date())], "n_val_series": len(inputs),
                    "val_ends": [str(e.date()) for e in ends]}


try:                                                                  # a real TrainerCallback when available
    from transformers import TrainerCallback as _CallbackBase
except ImportError:                                                   # tests without transformers
    _CallbackBase = object


class EvalRecorder(_CallbackBase):
    """Records eval_loss by step (HF TrainerCallback)."""
    def __init__(self):
        super().__init__()
        self.log = []

    def on_evaluate(self, args, state, control, metrics=None, **kw):
        if metrics and "eval_loss" in metrics:
            self.log.append((int(state.global_step), float(metrics["eval_loss"])))


def assert_lora_available():
    """chronos' fit() silently falls back to FULL fine-tuning without peft. Refuse to run in that case."""
    try:
        import peft  # noqa: F401
    except ImportError as e:
        raise RuntimeError("peft is not installed: LoRA would silently fall back to full fine-tuning") from e


def run_fold(pipe, panels: dict, eligible: pd.DataFrame, target: str, year: int, cutoff: str, out_dir: Path,
             lr_grid=LR_GRID, num_steps: int = NUM_STEPS, batch_size: int = 256, holdout_unlock: bool = False,
             fit_kwargs: dict | None = None, callback_factory=EvalRecorder, check_lora: bool = True,
             trainer_root: str | Path | None = None) -> dict:
    """Fine-tune one (target, year) fold, choose lr on inner validation, forecast every anchor of `year` with
    the chosen model and save preds + a JSON record. Skips the fold if its preds already exist (resume).
    `trainer_root`: where the HF Trainer writes its intermediate checkpoints (use fast local disk in Colab;
    only preds, record and the chosen adapter go to `out_dir`)."""
    out_dir = Path(out_dir) / target / str(year)
    fpred, frec = out_dir / "preds.parquet", out_dir / "record.json"
    if fpred.exists() and frec.exists():
        return json.loads(frec.read_text())
    if pd.Timestamp(cutoff) >= pd.Timestamp(f"{year}-01-01"):
        raise AssertionError(f"training cutoff {cutoff} must be before the evaluation year {year}")
    variates = TARGETS[target]
    P = {v: panels[v] for v in variates}
    tr, tr_info = training_inputs(P, cutoff, variates)
    va, va_info = validation_inputs(P, cutoff, variates)
    if not tr or not va:
        raise ValueError(f"{target} {year}: {len(tr)} training / {len(va)} validation series before {cutoff} "
                         f"(each needs >= {CTX + H} observations); this fold cannot be fine-tuned")
    if check_lora:
        assert_lora_available()
    rec = {"target": target, "year": year, "cutoff": cutoff, **tr_info, **va_info, "n_train_series": len(tr), "runs": []}
    best = None
    for lr in lr_grid:
        cb = callback_factory()
        t0 = time.time()
        ft = pipe.fit(tr, prediction_length=H, validation_inputs=va, finetune_mode="lora", context_length=CTX,
                      learning_rate=lr, num_steps=num_steps, batch_size=batch_size, callbacks=[cb],
                      output_dir=str(Path(trainer_root or out_dir) / target / str(year) / f"trainer_lr{lr:g}"),
                      **(fit_kwargs or {}))
        is_lora = type(getattr(ft, "model", None)).__name__.lower().startswith("peft") or hasattr(getattr(ft, "model", None), "peft_config")
        if check_lora and not is_lora:
            raise RuntimeError("fine-tuned model is not a PEFT/LoRA model: refusing to continue")
        best_loss = min((l for _, l in cb.log), default=np.nan)
        best_step = min(cb.log, key=lambda x: x[1])[0] if cb.log else None
        rec["runs"].append({"lr": lr, "best_eval_loss": best_loss, "best_step": best_step, "eval_log": cb.log,
                            "fit_seconds": round(time.time() - t0, 1)})
        if best is None or (np.isfinite(best_loss) and best_loss < best[0]):
            best = (best_loss, lr, ft)
        else:
            del ft
    rec["chosen_lr"] = best[1]
    first = panels[variates[0]]
    anchors = first.index[(first.index >= f"{year}-01-01") & (first.index <= f"{year}-12-31")]
    anchors = anchors[anchors.isin(eligible.index)]
    t0 = time.time()
    preds = cs.generate_multivariate(best[2], P, eligible, anchors, ctx=CTX, H=H, cross_learning=True,
                                     batch_size=batch_size, holdout_unlock=holdout_unlock, progress=False)
    rec["forecast_seconds"] = round(time.time() - t0, 1)
    rec["n_pred_rows"] = len(preds)
    out_dir.mkdir(parents=True, exist_ok=True)
    try:                                                              # keep the chosen adapter (small)
        best[2].model.save_pretrained(str(out_dir / "adapter"))
        rec["adapter_saved"] = True
    except Exception as e:                                            # noqa: BLE001
        rec["adapter_saved"] = f"no ({type(e).__name__})"
    preds.to_parquet(fpred)
    frec.write_text(json.dumps(rec, indent=1, default=str))
    return rec


def run_all(pipe, panels: dict, eligible: pd.DataFrame, mode: str, out_dir: Path, targets=("F1", "F2"), **kw) -> list:
    """All folds of `mode` ('dev' or 'holdout') for each target, resumable fold by fold."""
    recs = []
    for target in targets:
        for year, cutoff in FOLDS[mode].items():
            print(f"=== {target} {year} (train <= {cutoff}) ===", flush=True)
            r = run_fold(pipe, panels, eligible, target, year, cutoff, out_dir,
                         holdout_unlock=(mode == "holdout"), **kw)
            print({k: r[k] for k in ("chosen_lr", "n_train_series", "n_val_series", "n_pred_rows")},
                  [(x["lr"], round(x["best_eval_loss"], 4), x["fit_seconds"]) for x in r["runs"]], flush=True)
            recs.append(r)
    return recs
