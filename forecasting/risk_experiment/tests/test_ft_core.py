import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "colab"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import chronos_sources as cs  # noqa: E402
import ft_core as fc  # noqa: E402


class FakeModel:
    peft_config = {"default": "lora"}

    def save_pretrained(self, path):
        Path(path).mkdir(parents=True, exist_ok=True)


class FakePipe:
    """predict_quantiles echoes each variate's last context value; fit() records its inputs and reports a
    fake eval loss minimized at lr = 3e-5."""
    def __init__(self):
        self.fits = []
        self.model = FakeModel()

    def predict_quantiles(self, inputs, prediction_length, quantile_levels, **kw):
        out = []
        for x in inputs:
            x = np.atleast_2d(x)
            out.append(np.repeat(x[:, -1][:, None, None], prediction_length, 1).repeat(len(quantile_levels), 2))
        return out, None

    def fit(self, inputs, prediction_length, validation_inputs, callbacks, learning_rate, **kw):
        self.fits.append(dict(n=len(inputs), n_val=len(validation_inputs), lr=learning_rate, kw=kw,
                              train_last=[np.atleast_2d(x)[0, -1] for x in inputs]))
        for step, base in [(100, 1.0), (200, 0.9)]:
            loss = base + abs(np.log10(learning_rate) - np.log10(3e-5))
            for cb in callbacks:
                cb.on_evaluate(None, SimpleNamespace(global_step=step), None, metrics={"eval_loss": loss})
        return self


def _panels(seed=0):
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2019-06-03", "2022-12-30")
    cols = [f"S{i}" for i in range(6)]
    ret = pd.DataFrame(rng.normal(0, 0.02, (len(dates), 6)), dates, cols)
    rv = pd.DataFrame(np.exp(rng.normal(-8, 0.5, (len(dates), 6))), dates, cols)
    ret.iloc[:600, 5] = np.nan; rv.iloc[:600, 5] = np.nan              # a late listing
    return cs.rv_panels(ret, rv), pd.DataFrame(True, dates, cols)


def test_training_and_validation_inputs_are_causal_and_disjoint():
    P, _ = _panels()
    cutoff = "2021-12-31"
    tr, ti = fc.training_inputs(P, cutoff, ["ret", "logrv"])
    va, vi = fc.validation_inputs(P, cutoff, ["ret", "logrv"])
    cal = P["ret"].index[P["ret"].index <= cutoff]
    assert pd.Timestamp(ti["train_end"]) == cal[-fc.VAL_DAYS - 1]
    assert pd.Timestamp(vi["val_block"][0]) > pd.Timestamp(ti["train_end"])
    assert pd.Timestamp(vi["val_block"][1]) <= pd.Timestamp(cutoff)
    assert all(pd.Timestamp(e) <= pd.Timestamp(cutoff) for e in vi["val_ends"])
    assert tr[0].shape[0] == 2 and va[0].shape == (2, fc.CTX + fc.H)
    s0 = P["ret"]["S0"].loc[:ti["train_end"]].dropna()
    assert tr[0][0, -1] == pytest.approx(s0.iloc[-1])                   # training data ends at train_end
    P2 = {k: v.copy() for k, v in P.items()}
    for v in P2.values():
        v.loc["2022-01-01":] = 99.0                                     # the future must not leak in
    tr2, _ = fc.training_inputs(P2, cutoff, ["ret", "logrv"])
    va2, _ = fc.validation_inputs(P2, cutoff, ["ret", "logrv"])
    assert all(np.array_equal(a, b) for a, b in zip(tr, tr2)) and all(np.array_equal(a, b) for a, b in zip(va, va2))


def test_univariate_target_gives_1d_inputs():
    P, _ = _panels()
    tr, _ = fc.training_inputs({"logrv": P["logrv"]}, "2021-12-31", ["logrv"])
    assert tr[0].ndim == 1


def test_run_fold_selects_lr_forecasts_year_and_resumes(tmp_path):
    P, elig = _panels()
    pipe = FakePipe()
    rec = fc.run_fold(pipe, P, elig, "F2", 2022, "2021-12-31", tmp_path, check_lora=False)
    assert rec["chosen_lr"] == 3e-5 and len(pipe.fits) == 3
    assert all(f["kw"]["finetune_mode"] == "lora" and f["kw"]["context_length"] == fc.CTX for f in pipe.fits)
    preds = pd.read_parquet(tmp_path / "F2" / "2022" / "preds.parquet")
    assert preds["anchor"].min() >= pd.Timestamp("2022-01-01") and preds["anchor"].max() <= pd.Timestamp("2022-12-31")
    assert set(preds["variate"]) == {"ret", "logrv"}
    n = len(pipe.fits)
    fc.run_fold(pipe, P, elig, "F2", 2022, "2021-12-31", tmp_path, check_lora=False)
    assert len(pipe.fits) == n                                          # resumed: no refit


def test_run_fold_guards(tmp_path):
    P, elig = _panels()
    with pytest.raises(AssertionError):
        fc.run_fold(FakePipe(), P, elig, "F1", 2022, "2022-03-31", tmp_path, check_lora=False)


def test_fold_without_enough_history_fails_before_training(tmp_path):
    P, elig = _panels()
    pipe = FakePipe()
    with pytest.raises(ValueError, match="cannot be fine-tuned"):
        fc.run_fold(pipe, P, elig, "F1", 2020, "2019-12-31", tmp_path, check_lora=False)
    assert pipe.fits == []


def test_dev_folds_start_in_2022():
    assert list(fc.FOLDS["dev"]) == [2022, 2023, 2024]


def test_refuses_non_lora_model(tmp_path, monkeypatch):
    P, elig = _panels()
    pipe = FakePipe()
    pipe.model = SimpleNamespace(save_pretrained=lambda p: None)       # no peft_config
    monkeypatch.setattr(fc, "assert_lora_available", lambda: None)
    with pytest.raises(RuntimeError):
        fc.run_fold(pipe, P, elig, "F1", 2022, "2021-12-31", tmp_path, check_lora=True)
