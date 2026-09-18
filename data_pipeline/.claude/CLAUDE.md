# data_pipeline

Goal, rules, ALGOPACK API notes, and the file index are in
[`../CONTRIBUTING.md`](../CONTRIBUTING.md) — read that first.

Session/development history is archived locally in `../archive/` (not published).

- Before editing or creating any file, check [`../index.md`](../index.md) for the current
  file map.
- Pipeline code lives only in `../src/algopack_pipeline.py`; after any change run
  `python ../tools/build_notebook.py` and `pytest` from `data_pipeline/`. Never hand-edit
  `../notebooks/algopack_pipeline.ipynb`.
- Secrets only in `.env` (git-ignored). Never print, log, or commit the API key.
