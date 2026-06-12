# Path B — Chronos-2 fine-tuning

Code and configs for **Path B** of the MOEX × Chronos-2 experiment: fine-tuning
Chronos-2 on the MOEX panel via AutoGluon's `TimeSeriesPredictor`
(vs. Path A's raw zero-shot forecast in [`../moex_chronos2_pipeline.ipynb`](../moex_chronos2_pipeline.ipynb)).

## What lives here
- Fine-tuning scripts / notebooks for Path B.
- Path B configs (extends the stage configs in [`../configs/`](../configs/)).
- The written plan is in [`../stage_B/B_plan_v1.md`](../stage_B/B_plan_v1.md).

## Where things go (project sync rules)
- **Code** (this folder's `.py` / `.ipynb` / configs) → **GitHub** only.
- **Artifacts** (fine-tuned model `ag_chronos2_ft/`, `*.parquet`, result `*.csv`,
  executed `*_run.ipynb`) → **partner's Google Drive** `moex-hack/ilia`, pushed
  automatically on each commit (see [`../scripts/push_drive.sh`](../scripts/push_drive.sh)).

## Running on a Colab GPU (Colab CLI)
```bash
colab new -s ft --gpu T4
colab install -s ft chronos-forecasting "pandas[pyarrow]" requests matplotlib numpy tqdm pyyaml scipy
colab install -s ft "autogluon.timeseries[chronos]"
colab exec -s ft -f path_b/finetune_chronos2.py     # once the script exists
colab download -s ft ag_chronos2_ft ./ag_chronos2_ft
colab stop -s ft
```

## T4 note
Free-tier T4 has **no bfloat16** — use `float16` (the pipeline picks dtype by GPU
capability: bf16 only on Ampere+). bf16 needs A100/L4 (Colab Pro). See
[`../COLAB_CLI.md`](../COLAB_CLI.md) for the full workflow and gotchas.
