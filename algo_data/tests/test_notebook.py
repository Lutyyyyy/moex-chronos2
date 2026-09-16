import json
import sys

from conftest import ROOT

sys.path.insert(0, str(ROOT / "tools"))
import build_notebook  # noqa: E402


def test_notebook_builds_compiles_and_is_current(tmp_path, monkeypatch):
    committed = build_notebook.OUT.read_text(encoding="utf-8") if build_notebook.OUT.exists() else None
    monkeypatch.setattr(build_notebook, "OUT", tmp_path / "nb.ipynb")
    nb = json.loads(build_notebook.build().read_text(encoding="utf-8"))

    code = ["".join(c["source"]) for c in nb["cells"] if c["cell_type"] == "code"]
    for i, src in enumerate(code):
        compile(src, f"cell-{i}", "exec")
    assert sum(src.count("-----BEGIN CERTIFICATE-----") for src in code) == 2
    assert any("def run(" in src for src in code) and any("load_config(CONFIG_PATH)" in src for src in code)
    assert committed == (tmp_path / "nb.ipynb").read_text(encoding="utf-8"), \
        "notebooks/algopack_pipeline.ipynb is stale: run python tools/build_notebook.py"
