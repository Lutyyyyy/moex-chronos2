# Path B — Chronos-2 fine-tuning

Code and configs for **Path B** of the MOEX × Chronos-2 experiment: fine-tuning
Chronos-2 on the MOEX panel via AutoGluon's `TimeSeriesPredictor`
(vs. Path A's raw zero-shot forecast in [`../moex_chronos2_pipeline.ipynb`](../moex_chronos2_pipeline.ipynb)).

## What lives here
- Fine-tuning scripts / notebooks for Path B.
- Path B configs (extends the stage configs in [`../configs/`](../configs/)).
- The written plan is in [`../stage_B/B_plan_v1.md`](../stage_B/B_plan_v1.md).
- [`COLAB_SKILL.md`](COLAB_SKILL.md) — bundled Colab CLI command reference (`colab skill`).
- [`push_drive.sh`](push_drive.sh) / [`sync.sh`](sync.sh) — artifact → Drive and commit+sync helpers.

## Where things go (project sync rules)
- **Code** (this folder's `.py` / `.ipynb` / configs) → **GitHub** only.
- **Artifacts** (fine-tuned model `ag_chronos2_ft/`, `*.parquet`, result `*.csv`,
  executed `*_run.ipynb`) → **partner's Google Drive** `moex-hack/ilia`, pushed
  automatically on each commit (see [`push_drive.sh`](push_drive.sh); the local
  `.git/hooks/post-commit` fires it).

## Running on a Colab GPU (Colab CLI)
```bash
colab new -s ft --gpu T4
colab install -s ft chronos-forecasting "pandas[pyarrow]" requests matplotlib numpy tqdm pyyaml scipy
colab install -s ft "autogluon.timeseries[chronos]"
colab exec -s ft -f path_b/finetune_chronos2.py --timeout 1800   # once the script exists
colab download -s ft ag_chronos2_ft ./ag_chronos2_ft
colab stop -s ft
```
**Gotcha:** `colab exec` defaults to a **30 s** timeout — always pass `--timeout 1800`
for real runs or it kills the job mid-execution. Full command reference: [`COLAB_SKILL.md`](COLAB_SKILL.md).

## T4 note
Free-tier T4 has **no bfloat16** — use `float16` (the pipeline picks dtype by GPU
capability: bf16 only on Ampere+). bf16 needs A100/L4 (Colab Pro).
