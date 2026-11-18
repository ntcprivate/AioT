from __future__ import annotations

import json
import os
from pathlib import Path

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
os.environ.setdefault("TF_ENABLE_ONEDNN_OPTS", "0")
import numpy as np
import tensorflow as tf

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/cnn_v5/final_evaluation"
RESULT = OUT / "evaluation.json"
LOCK = OUT / "evaluation.lock.json"


def metrics(y, scores, threshold):
    pred = scores >= threshold
    tp = int(np.sum((y == 1) & pred)); tn = int(np.sum((y == 0) & ~pred))
    fp = int(np.sum((y == 0) & pred)); fn = int(np.sum((y == 1) & ~pred))
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"accuracy": (tp + tn) / len(y), "precision": precision, "recall": recall, "f1": f1,
            "TP": tp, "TN": tn, "FP": fp, "FN": fn, "confusion_rows_N_V": [[tn, fp], [fn, tp]]}


def add_accuracy(row):
    row = dict(row); total = row["TP"] + row["TN"] + row["FP"] + row["FN"]
    row["accuracy"] = (row["TP"] + row["TN"]) / total
    return row


def main():
    if LOCK.exists(): raise RuntimeError(f"Final V5 Test evaluation already exists: {LOCK}")
    OUT.mkdir(parents=True, exist_ok=True)
    prior = json.loads((ROOT / "results/cnn_v5/evaluation.json").read_text())
    v4_test = json.loads((ROOT / "results/cnn_v4/test_evaluation.json").read_text())
    model = tf.keras.models.load_model(ROOT / "models/v5/ecg_cnn_v5_best.keras", compile=False)

    mit = np.load(ROOT / "data/processed/mitbih_nv_250hz.npz")
    split = np.load(ROOT / "data/processed/mitbih_split_indices.npz")
    mit_test = split["test_indices"]
    y_mit = mit["y"][mit_test].astype(np.int32)
    scores_mit = model.predict(mit["X"][mit_test], batch_size=512, verbose=0).reshape(-1)

    inc = np.load(ROOT / "data/processed/incart_v4_250hz.npz")
    inc_test = inc["split"] == "test"; y_inc = inc["y"][inc_test].astype(np.int32)
    scores_inc = model.predict(inc["X"][inc_test], batch_size=512, verbose=0).reshape(-1)

    result = {
        "thresholds": {"V4": 0.88, "V5": 0.33},
        "selection_or_tuning_on_test": False,
        "validation_reused_without_inference": True,
        "MITBIH": {
            "Validation": {"V4": add_accuracy(prior["comparison"]["MITBIH_Validation"]["V4"]),
                           "V5": add_accuracy(prior["comparison"]["MITBIH_Validation"]["V5"])},
            "Test": {"samples": len(y_mit), "N": int(np.sum(y_mit == 0)), "V": int(np.sum(y_mit == 1)),
                     "V4": None, "V4_note": "No pre-existing V4 MIT-BIH Test result; not rerun by request",
                     "V5": metrics(y_mit, scores_mit, 0.33)},
        },
        "INCART": {
            "Validation": {"V4": add_accuracy(prior["comparison"]["INCART_Validation"]["V4"]),
                           "V5": add_accuracy(prior["comparison"]["INCART_Validation"]["V5"])},
            "Test": {"samples": len(y_inc), "N": int(np.sum(y_inc == 0)), "V": int(np.sum(y_inc == 1)),
                     "V4": add_accuracy(v4_test["V4"]["overall"]), "V5": metrics(y_inc, scores_inc, 0.33)},
        },
    }
    RESULT.write_text(json.dumps(result, indent=2) + "\n")
    LOCK.write_text(json.dumps({"completed": True, "threshold": 0.33,
                                "MITBIH_Test_samples": len(y_mit), "INCART_Test_samples": len(y_inc)}, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
