from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
os.environ.setdefault("TF_ENABLE_ONEDNN_OPTS", "0")

import numpy as np
import tensorflow as tf


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/cnn_v7/final_test"
V7_PATH = ROOT / "models/v7/ecg_cnn_v7_best.keras"
V7_EVAL = ROOT / "results/cnn_v7/evaluation.json"
PRIOR = ROOT / "results/cnn_v6/main_dataset_comparison/evaluation.json"
V8_CONFIG = ROOT / "results/cnn_v8/config.json"
THRESHOLD = 0.95


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def metrics(y: np.ndarray, scores: np.ndarray) -> dict:
    prediction = scores >= THRESHOLD
    tp = int(np.sum((y == 1) & prediction)); tn = int(np.sum((y == 0) & ~prediction))
    fp = int(np.sum((y == 0) & prediction)); fn = int(np.sum((y == 1) & ~prediction))
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"accuracy": (tp + tn) / len(y), "precision": precision, "recall": recall, "f1": f1,
            "TP": tp, "FP": fp, "FN": fn, "TN": tn, "confusion_rows_N_V": [[tn, fp], [fn, tp]]}


def main() -> None:
    if OUT.exists():
        raise RuntimeError(f"V7 final Test already exists; refusing to rerun: {OUT}")
    frozen = json.loads(V7_EVAL.read_text(encoding="utf-8"))
    if frozen["threshold"] != THRESHOLD or frozen["checkpoint_sha256"] != sha256(V7_PATH):
        raise RuntimeError("Frozen V7 checkpoint/threshold mismatch")
    v8_design_hash = sha256(V8_CONFIG)
    prior = json.loads(PRIOR.read_text(encoding="utf-8"))
    model = tf.keras.models.load_model(V7_PATH, compile=False)

    mit = np.load(ROOT / "data/processed/mitbih_nv_250hz.npz")
    split = np.load(ROOT / "data/processed/mitbih_split_indices.npz")
    mit_test = split["test_indices"]
    y_mit = mit["y"][mit_test].astype(np.int32)
    scores_mit = model.predict(mit["X"][mit_test], batch_size=512, verbose=0).reshape(-1)
    inc = np.load(ROOT / "data/processed/incart_v4_250hz.npz")
    inc_test = inc["split"].astype(str) == "test"
    y_inc = inc["y"][inc_test].astype(np.int32)
    scores_inc = model.predict(inc["X"][inc_test], batch_size=512, verbose=0).reshape(-1)

    result = {
        "scope": "retrospective comparison on previously examined MIT-BIH/INCART Test",
        "independent_evidence": False,
        "v8_design_sha256_before_v7_test": v8_design_hash,
        "thresholds": {"V4": 0.88, "V5": 0.33, "V6": 0.87, "V7": THRESHOLD},
        "v4_v5_v6_reused_without_inference": True,
        "v7_test_inference_runs": {"MITBIH": 1, "INCART": 1},
        "datasets": {
            "MITBIH": {**prior["test"]["MITBIH"], "V7": metrics(y_mit, scores_mit)},
            "INCART": {**prior["test"]["INCART"], "V7": metrics(y_inc, scores_inc)},
        },
        "selection_or_tuning_on_test": False,
    }
    OUT.mkdir(parents=True)
    (OUT / "evaluation.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    (OUT / "evaluation.lock.json").write_text(json.dumps({"completed": True,
        "v7_sha256": sha256(V7_PATH), "threshold": THRESHOLD,
        "v8_design_sha256_before_v7_test": v8_design_hash}, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
