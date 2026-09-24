"""Generate ft_lora.ipynb (never hand-edit the .ipynb; edit this file and re-run make_bundle.py).

  .venv/bin/python forecasting/risk_experiment/colab/build_notebook.py <out.ipynb>
"""
import sys

import nbformat as nbf

MD, CODE = nbf.v4.new_markdown_cell, nbf.v4.new_code_cell

cells = [
    MD("# Chronos-2 LoRA fine-tuning for the risk study (F1 log-RV, F2 [return, log-RV])\n\n"
       "Upload the **unzipped** bundle folder to Google Drive, set `BUNDLE` below, then **Runtime → Run all** "
       "on a GPU runtime (T4 is enough).\n\n"
       "- **Resumable.** Each (target, year) fold is saved to `BUNDLE/outputs/` as soon as it finishes. After a "
       "disconnect, reconnect and run all again; finished folds are skipped.\n"
       "- **Protocol** (see `code/ft_core.py`):\n"
       "  - the model for year *y* is trained only on data ≤ Dec 31 of *y−1*;\n"
       "  - the learning rate is chosen on the last 60 trading days before that cutoff;\n"
       "  - the evaluation year is never used for any choice.\n"
       "- **When done:** run the last cell and download `outputs.zip` into "
       "`forecasting/runs/risk_ft/<mode>/` in the repo."),
    CODE("!pip -q install chronos-forecasting==2.3.2 peft\n"
         "# Colab ships torchao 0.10; recent peft rejects torchao < 0.16 when it sets up LoRA. Chronos does not\n"
         "# use torchao, so remove it. After this cell: Runtime -> Restart session, then Run all.\n"
         "!pip -q uninstall -y torchao"),
    CODE("from google.colab import drive\n"
         "drive.mount('/content/drive')\n"
         "BUNDLE = '/content/drive/MyDrive/risk_bundle_dev'   # <- the unzipped bundle folder on Drive\n"
         "TRAINER_TMP = '/content/trainer_tmp'                # Trainer scratch on local disk (not Drive)"),
    CODE("import json, sys, time, platform\n"
         "from pathlib import Path\n"
         "import numpy as np, pandas as pd, torch\n"
         "sys.path.insert(0, f'{BUNDLE}/code')\n"
         "import chronos, peft, transformers\n"
         "import chronos_sources as cs, ft_core as fc\n"
         "cfg = json.load(open(f'{BUNDLE}/config.json'))\n"
         "assert torch.cuda.is_available(), 'Select a GPU runtime (Runtime -> Change runtime type -> T4 GPU)'\n"
         "env = {'python': platform.python_version(), 'torch': torch.__version__, 'chronos': getattr(chronos, '__version__', '?'),\n"
         "       'peft': peft.__version__, 'transformers': transformers.__version__, 'gpu': torch.cuda.get_device_name(0),\n"
         "       'mode': cfg['mode'], 'cutoff': cfg['cutoff']}\n"
         "print(json.dumps(env, indent=1))\n"
         "OUT = Path(BUNDLE) / 'outputs'; OUT.mkdir(exist_ok=True)\n"
         "(OUT / 'env.json').write_text(json.dumps(env, indent=1))"),
    CODE("# data: physically truncated at the bundle cutoff\n"
         "ret = pd.read_parquet(f'{BUNDLE}/data/ret.parquet'); rv = pd.read_parquet(f'{BUNDLE}/data/rv.parquet')\n"
         "eligible = pd.read_parquet(f'{BUNDLE}/data/eligible.parquet').astype(bool)\n"
         "assert ret.index.max() <= pd.Timestamp(cfg['cutoff']), 'bundle contains data after its cutoff'\n"
         "panels = cs.rv_panels(ret, rv)\n"
         "print(ret.shape, ret.index.min().date(), ret.index.max().date())"),
    CODE("from chronos import Chronos2Pipeline\n"
         "pipe = Chronos2Pipeline.from_pretrained(cfg['model'], device_map='cuda', torch_dtype=torch.float32)\n"
         "# parity: zero-shot forecasts on GPU must match the local CPU reference (dev bundle only)\n"
         "parity = {}\n"
         "for tgt, info in cfg.get('parity', {}).items():\n"
         "    ref = pd.read_parquet(f'{BUNDLE}/parity/{tgt}_zero_shot_ref.parquet')\n"
         "    P = {v: panels[v] for v in fc.TARGETS[tgt]}\n"
         "    got = cs.generate_multivariate(pipe, P, eligible, pd.DatetimeIndex(cfg['parity_anchors']), ctx=fc.CTX, H=fc.H,\n"
         "                                   cross_learning=True, progress=False)\n"
         "    m = got.merge(ref, on=['anchor', 'ticker', 'variate', 'h'], suffixes=('', '_ref'))\n"
         "    q = [c for c in got.columns if c.startswith('q')]\n"
         "    d = np.abs(m[q].to_numpy() - m[[c + '_ref' for c in q]].to_numpy())\n"
         "    parity[tgt] = {'rows_matched': len(m), 'rows_ref': len(ref), 'max_abs_diff': float(d.max()), 'mean_abs_diff': float(d.mean())}\n"
         "print(json.dumps(parity, indent=1))\n"
         "(OUT / 'parity.json').write_text(json.dumps(parity, indent=1))\n"
         "for tgt, r in parity.items():\n"
         "    assert r['rows_matched'] == r['rows_ref'], f'{tgt}: parity rows mismatch'\n"
         "    assert r['max_abs_diff'] < 5e-3, f'{tgt}: GPU zero-shot differs from the CPU reference by {r[\"max_abs_diff\"]:.2e}'"),
    CODE("# main loop: all folds, resumable. The first fold also serves as the timing smoke test.\n"
         "t0 = time.time()\n"
         "recs = fc.run_all(pipe, panels, eligible, cfg['mode'], OUT, trainer_root=TRAINER_TMP)\n"
         "print(f'done in {(time.time() - t0) / 60:.1f} min')"),
    CODE("import shutil\n"
         "zp = shutil.make_archive('/content/outputs', 'zip', root_dir=OUT)\n"
         "from google.colab import files\n"
         "files.download(zp)"),
]

nb = nbf.v4.new_notebook()
nb["cells"] = cells
nb["metadata"] = {"accelerator": "GPU", "colab": {"provenance": []},
                  "kernelspec": {"name": "python3", "display_name": "Python 3"}}
nbf.write(nb, sys.argv[1] if len(sys.argv) > 1 else "ft_lora.ipynb")
