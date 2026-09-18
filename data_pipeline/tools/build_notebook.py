"""Build notebooks/algopack_pipeline.ipynb from src/algopack_pipeline.py (`# %%` cells) + Colab setup/run cells.
The Russian Trusted CA PEM is embedded so the notebook needs no repo files.  Usage: python tools/build_notebook.py"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "algopack_pipeline.py"
PEM = ROOT / "certs" / "russian_trusted_ca.pem"
OUT = ROOT / "notebooks" / "algopack_pipeline.ipynb"

HEAD = [
    ("markdown", """# ALGOPACK pipeline (Colab)
1. Put `config.md` and `.env` (`ALGOPACK_API_KEY=...`) into one Google Drive folder, default `MyDrive/data_pipeline/`.
2. Edit `config.md` (tickers, intervals, period, datasets); see `docs/usage.md`.
3. *Runtime → Run all*. Re-running resumes: finished month chunks are cached under `<output_root>/raw/`."""),
    ("code", """# 0. Mount Google Drive and point to config.md (relative paths inside it resolve against its folder)
CONFIG_PATH = "/content/drive/MyDrive/data_pipeline/config.md"
try:
    from google.colab import drive
    drive.mount("/content/drive")
except ImportError:  # local Jupyter: config.md in the working directory
    CONFIG_PATH = "config.md\""""),
]

TAIL = [
    ("markdown", "## 8. Run"),
    ("code", """cfg = load_config(CONFIG_PATH)
print(cfg.describe())"""),
    ("code", """summary = run(cfg)  # fetch missing months → rebuild <output_root>/processed/*
summary"""),
    ("markdown", "## 9. Optional: universe snapshot (what is listed now + turnover)"),
    ("code", """# universe = universe_report(cfg)  # writes <output_root>/universe/universe.md + parquet"""),
    ("markdown", "## 10. Load results"),
    ("code", """processed = cfg.output_root / "processed"
for f in sorted(processed.glob("*/*.parquet")):
    print(f.relative_to(processed))
df = pd.read_parquet(processed / f"candles_{cfg.intervals[0]}" / "shares.parquet") if (processed / f"candles_{cfg.intervals[0]}" / "shares.parquet").exists() else None
df.head() if df is not None else None"""),
]


def split_cells(source: str) -> list[tuple[str, str]]:
    cells, kind, buf = [], None, []
    for line in source.splitlines():
        m = re.match(r"# %%(?:\s*\[(markdown)\])?\s*$", line)
        if m:
            if kind:
                cells.append((kind, "\n".join(buf).strip("\n")))
            kind, buf = ("markdown" if m.group(1) else "code"), []
        elif kind:
            buf.append(re.sub(r"^# ?", "", line) if kind == "markdown" else line)
    if kind:
        cells.append((kind, "\n".join(buf).strip("\n")))
    return cells


def build() -> Path:
    source = SRC.read_text(encoding="utf-8")
    pem = PEM.read_text().replace("\r", "").strip()
    source, n = re.subn(r"^RUSSIAN_TRUSTED_CA_PEM = None$", f'RUSSIAN_TRUSTED_CA_PEM = """\n{pem}\n"""', source, flags=re.M)
    assert n == 1, "RUSSIAN_TRUSTED_CA_PEM placeholder not found"
    cells = HEAD + split_cells(source) + TAIL
    nb = {"nbformat": 4, "nbformat_minor": 5,
          "metadata": {"kernelspec": {"name": "python3", "display_name": "Python 3"}, "language_info": {"name": "python"}},
          "cells": []}
    for i, (kind, text) in enumerate(cells):
        cell = {"cell_type": kind, "id": f"cell-{i}", "metadata": {}, "source": text.splitlines(keepends=True)}
        if kind == "code":
            cell.update(execution_count=None, outputs=[])
        nb["cells"].append(cell)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(nb, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return OUT


if __name__ == "__main__":
    print(f"written {build()}")
