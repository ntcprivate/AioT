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
OUT = ROOT / "results/cnn_v8/final_test"
MODEL_PATH = ROOT / "models/v8/ecg_cnn_v8_best.keras"
V8_EVAL = ROOT / "results/cnn_v8/evaluation.json"
V8_LOCK = ROOT / "results/cnn_v8/locked.json"
V7_TEST = ROOT / "results/cnn_v7/final_test/evaluation.json"
V7_DEV = ROOT / "results/cnn_v7/evaluation.json"
THRESHOLD = 0.965


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalize(row: dict) -> dict:
    tp, fp, fn, tn = (int(row[key]) for key in ("TP", "FP", "FN", "TN"))
    total = tp + fp + fn + tn
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"accuracy": (tp + tn) / total, "precision": precision, "recall": recall, "f1": f1,
            "TP": tp, "FP": fp, "FN": fn, "TN": tn,
            "confusion_rows_N_V": [[tn, fp], [fn, tp]]}


def metrics(y: np.ndarray, scores: np.ndarray) -> dict:
    prediction = scores >= THRESHOLD
    return normalize({"TP": np.sum((y == 1) & prediction), "FP": np.sum((y == 0) & prediction),
                      "FN": np.sum((y == 1) & ~prediction), "TN": np.sum((y == 0) & ~prediction)})


def aggregate(first: dict, second: dict) -> dict:
    return normalize({key: int(first[key]) + int(second[key]) for key in ("TP", "FP", "FN", "TN")})


def main() -> None:
    if OUT.exists():
        raise RuntimeError(f"V8 final Test already exists; refusing to rerun: {OUT}")
    frozen = json.loads(V8_EVAL.read_text(encoding="utf-8"))
    lock = json.loads(V8_LOCK.read_text(encoding="utf-8"))
    model_hash = sha256(MODEL_PATH)
    if frozen["threshold"] != THRESHOLD or lock["threshold"] != THRESHOLD:
        raise RuntimeError("Frozen V8 threshold mismatch")
    if frozen["checkpoint_sha256"] != model_hash or lock["checkpoint_sha256"] != model_hash:
        raise RuntimeError("Frozen V8 checkpoint hash mismatch")

    # V4-V7 are artifact-only; no old model invocation.
    old_test = json.loads(V7_TEST.read_text(encoding="utf-8"))["datasets"]
    old_dev = json.loads(V7_DEV.read_text(encoding="utf-8"))["comparison_same_development_partitions"]
    dev8 = frozen["comparison_same_development_partitions"]
    development = {}
    for dataset in ("INCART", "MITBIH"):
        development[dataset] = {}
        for name in ("V4", "V5", "V6", "V7"):
            development[dataset][name] = aggregate(old_dev[f"checkpoint_{dataset}"][name],
                                                   old_dev[f"threshold_{dataset}"][name])
        development[dataset]["V8"] = aggregate(dev8[f"checkpoint_{dataset}"]["V8"],
                                                dev8[f"threshold_{dataset}"]["V8"])

    model = tf.keras.models.load_model(MODEL_PATH, compile=False)
    mit = np.load(ROOT / "data/processed/mitbih_nv_250hz.npz")
    split = np.load(ROOT / "data/processed/mitbih_split_indices.npz")
    mit_index = split["test_indices"]
    y_mit = mit["y"][mit_index].astype(np.int32)
    score_mit = model.predict(mit["X"][mit_index], batch_size=512, verbose=0).reshape(-1)
    inc = np.load(ROOT / "data/processed/incart_v4_250hz.npz")
    inc_mask = inc["split"].astype(str) == "test"
    y_inc = inc["y"][inc_mask].astype(np.int32)
    score_inc = model.predict(inc["X"][inc_mask], batch_size=512, verbose=0).reshape(-1)

    test = {dataset: {name: normalize(old_test[dataset][name]) for name in ("V4", "V5", "V6", "V7")}
            for dataset in ("MITBIH", "INCART")}
    test["MITBIH"]["V8"] = metrics(y_mit, score_mit)
    test["INCART"]["V8"] = metrics(y_inc, score_inc)
    result = {
        "scope": "retrospective comparison; MIT-BIH/INCART Test were examined before V8",
        "independent_new_evidence": False,
        "thresholds": {"V4": 0.88, "V5": 0.33, "V6": 0.87, "V7": 0.95, "V8": THRESHOLD},
        "v8_checkpoint_sha256": model_hash,
        "v4_v5_v6_v7_reused_without_inference": True,
        "v8_test_inference_runs": {"MITBIH": 1, "INCART": 1},
        "development": development,
        "development_partition_note": "each dataset aggregates the saved group-disjoint checkpoint and threshold Development partitions",
        "test": test,
        "selection_or_tuning_on_test": False,
    }
    OUT.mkdir(parents=True)
    (OUT / "evaluation.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    (OUT / "evaluation.lock.json").write_text(json.dumps({"completed": True, "threshold": THRESHOLD,
        "checkpoint_sha256": model_hash, "MITBIH_Test_samples": len(y_mit),
        "INCART_Test_samples": len(y_inc)}, indent=2) + "\n", encoding="utf-8")

    def pct(value: float) -> str:
        return f"{100 * value:.4f}%"
    lines = ["# V4-V8 main-dataset retrospective comparison", "",
             "Not an independent new evaluation: both Test sets were examined before V8.", ""]
    for dataset in ("MITBIH", "INCART"):
        lines += [f"## {dataset}", "", "| Split | Model | Accuracy | Precision | Recall | F1 | TP | FP | FN | TN |",
                  "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
        for split_name, values in (("Development (checkpoint+threshold groups)", development[dataset]),
                                   ("Test (retrospective)", test[dataset])):
            for name in ("V4", "V5", "V6", "V7", "V8"):
                row = values[name]
                lines.append(f"| {split_name} | {name} | {pct(row['accuracy'])} | {pct(row['precision'])} | {pct(row['recall'])} | {pct(row['f1'])} | {row['TP']} | {row['FP']} | {row['FN']} | {row['TN']} |")
        lines.append("")
    lines += ["Only V8 Test inference was run. No threshold or model parameter was selected from Test."]
    (OUT / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"development": development, "test": test}, indent=2))


if __name__ == "__main__":
    main()
