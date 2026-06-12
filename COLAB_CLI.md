# Colab CLI — fine-tuning Chronos-2 on a Colab GPU

Run GPU fine-tuning from the terminal via the [Google Colab CLI](https://github.com/googlecolab/google-colab-cli)
(`google-colab-cli`, announced 2026-06-05). Reference: `COLAB_SKILL.md` in this folder, or `colab readme`.

## Install (already done on this machine)

```bash
brew install uv                       # macOS; uv brings its own Python 3.12+
uv tool install google-colab-cli      # installs the `colab` executable to ~/.local/bin
```
- Requires Python ≥ 3.12 (uv handles this in isolation — system Python 3.9 untouched).
- macOS / Linux only. No Windows.
- Auth: default is browser `oauth2` (no gcloud / GCP project needed). Triggered on first command.

## Deps for this project (from the notebook install cells)

- Core (Path A + data): `chronos-forecasting "pandas[pyarrow]" requests matplotlib numpy tqdm pyyaml scipy`
- Path B fine-tuning (heavy, ~2-4 min): `"autogluon.timeseries[chronos]"`

## Fine-tuning workflow (Path B)

```bash
colab new -s ft --gpu T4                          # provision a named T4 session
colab install -s ft chronos-forecasting "pandas[pyarrow]" requests matplotlib numpy tqdm pyyaml scipy
colab install -s ft "autogluon.timeseries[chronos]"
colab exec -s ft -f moex_chronos2_pipeline.ipynb  # run the pipeline
colab download -s ft ag_chronos2_ft ./ag_chronos2_ft  # pull fine-tuned model back
colab stop -s ft                                  # ALWAYS stop (free tier auto-caps at 24h)
```

Use a **named persistent session** (`-s ft`), not `colab run`, so the heavy AutoGluon
install isn't repeated every run.

## Gotchas

- **Path B cells (21–25 in `moex_chronos2_pipeline.ipynb`) are currently commented out.**
  Running the notebook as-is does NOT fine-tune. Activate those cells (or use a standalone
  script) for an actual GPU fine-tune.
- **T4 has no bfloat16.** The fine-tune cell sets `torch_dtype="bfloat16"`; on a free-tier T4
  this must fall back to `float16` (the code conditions on `DTYPE` — verify it resolves to
  `torch.float16`). bf16 needs A100/L4 (Colab Pro).
- **T4 = 16 GB VRAM.** Fine on the 12-series MVP panel; for larger panels use LoRA/QLoRA and
  checkpoint to Drive (`colab drivemount`) against disconnects.

## Useful commands

```bash
colab sessions          # list active sessions (watch for forgotten = $$$)
colab status -s ft      # session status
colab log -s ft --output run.ipynb   # capture run history as a notebook
colab repl -s ft        # interactive REPL on the GPU (needs a TTY)
colab skill | colab readme           # bundled docs
```
