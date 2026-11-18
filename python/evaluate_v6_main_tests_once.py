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
OUT = ROOT / "results/cnn_v6/main_dataset_comparison"
MODEL_PATH = ROOT / "models/v6/ecg_cnn_v6_best.keras"
V6_EVAL_PATH = ROOT / "results/cnn_v6/evaluation.json"
V5_EVAL_PATH = ROOT / "results/cnn_v5/evaluation.json"
PRIOR_TEST_PATH = ROOT / "results/cnn_v5/precision_drop_diagnostic/summary.json"
THRESHOLD = 0.87


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalize_counts(row: dict) -> dict:
    tp, tn, fp, fn = (int(row[key]) for key in ("TP", "TN", "FP", "FN"))
    total = tp + tn + fp + fn
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"accuracy": (tp + tn) / total if total else 0.0,
            "precision": precision, "recall": recall, "f1": f1,
            "TP": tp, "FP": fp, "FN": fn, "TN": tn,
            "confusion_rows_N_V": [[tn, fp], [fn, tp]]}


def from_scores(y: np.ndarray, scores: np.ndarray) -> dict:
    prediction = scores >= THRESHOLD
    return normalize_counts({
        "TP": np.sum((y == 1) & prediction), "TN": np.sum((y == 0) & ~prediction),
        "FP": np.sum((y == 0) & prediction), "FN": np.sum((y == 1) & ~prediction),
    })


def add_rows(first: dict, second: dict) -> dict:
    return normalize_counts({key: int(first[key]) + int(second[key]) for key in ("TP", "TN", "FP", "FN")})


def main() -> None:
    if OUT.exists():
        raise RuntimeError(f"V6 main Test comparison already exists; refusing to rerun: {OUT}")
    v6_existing = json.loads(V6_EVAL_PATH.read_text(encoding="utf-8"))
    expected_hash = v6_existing["checkpoint_sha256"]
    actual_hash = sha256(MODEL_PATH)
    if actual_hash != expected_hash or float(v6_existing["selected_threshold"]) != THRESHOLD:
        raise RuntimeError("V6 checkpoint or threshold does not match the frozen V6 artifact")

    # Existing results only: no V4/V5 model invocation in this script.
    v5_existing = json.loads(V5_EVAL_PATH.read_text(encoding="utf-8"))
    prior_test = json.loads(PRIOR_TEST_PATH.read_text(encoding="utf-8"))
    comparison = v6_existing["comparison"]
    validation = {}
    for dataset, source_key in (("MITBIH", "MITBIH_Validation"), ("INCART", "INCART_Validation")):
        prefix = "MITBIH" if dataset == "MITBIH" else "INCART"
        validation[dataset] = {
            "V4": normalize_counts(v5_existing["comparison"][source_key]["V4"]),
            "V5": normalize_counts(v5_existing["comparison"][source_key]["V5"]),
            "V6": add_rows(comparison[f"checkpoint_{prefix}"]["V6"],
                           comparison[f"threshold_{prefix}"]["V6"]),
            "V6_source": "aggregated without inference from saved disjoint checkpoint and threshold development partitions",
        }

    model = tf.keras.models.load_model(MODEL_PATH, compile=False)
    mit = np.load(ROOT / "data/processed/mitbih_nv_250hz.npz")
    split = np.load(ROOT / "data/processed/mitbih_split_indices.npz")
    mit_test = split["test_indices"]
    y_mit = mit["y"][mit_test].astype(np.int32)
    scores_mit = model.predict(mit["X"][mit_test], batch_size=512, verbose=0).reshape(-1)

    inc = np.load(ROOT / "data/processed/incart_v4_250hz.npz")
    inc_test = inc["split"].astype(str) == "test"
    y_inc = inc["y"][inc_test].astype(np.int32)
    scores_inc = model.predict(inc["X"][inc_test], batch_size=512, verbose=0).reshape(-1)

    test = {
        "MITBIH": {
            "V4": normalize_counts(prior_test["datasets"]["MITBIH"]["V4"]),
            "V5": normalize_counts(prior_test["datasets"]["MITBIH"]["V5"]),
            "V6": from_scores(y_mit, scores_mit),
        },
        "INCART": {
            "V4": normalize_counts(prior_test["datasets"]["INCART"]["V4"]),
            "V5": normalize_counts(prior_test["datasets"]["INCART"]["V5"]),
            "V6": from_scores(y_inc, scores_inc),
        },
    }
    result = {
        "scope": "retrospective main-dataset comparison; not an independent final evaluation",
        "reason": "MIT-BIH and INCART Test results were examined before V6 design",
        "thresholds": {"V4": 0.88, "V5": 0.33, "V6": THRESHOLD},
        "v6_checkpoint_sha256": actual_hash,
        "v4_v5_reused_without_inference": True,
        "v6_test_inference_runs": {"MITBIH": 1, "INCART": 1},
        "validation": validation,
        "v6_saved_development_partitions": {
            key: comparison[key] for key in (
                "checkpoint_INCART", "threshold_INCART", "checkpoint_MITBIH", "threshold_MITBIH")
        },
        "test": test,
        "selection_or_tuning_on_test": False,
    }
    OUT.mkdir(parents=True)
    (OUT / "evaluation.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    def pct(value: float) -> str:
        return f"{100 * value:.4f}%"
    lines = ["# V4/V5/V6 — MIT-BIH and INCART", "",
             "Retrospective comparison only. MIT-BIH/INCART Test had already been examined before V6.", ""]
    for dataset in ("MITBIH", "INCART"):
        lines += [f"## {dataset}", "",
                  "| Split | Model | Accuracy | Precision | Recall | F1 | TP | FP | FN | TN |",
                  "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
        for split_name, values in (("Validation", validation[dataset]), ("Test", test[dataset])):
            for name in ("V4", "V5", "V6"):
                row = values[name]
                lines.append(f"| {split_name} | {name} | {pct(row['accuracy'])} | {pct(row['precision'])} | {pct(row['recall'])} | {pct(row['f1'])} | {row['TP']} | {row['FP']} | {row['FN']} | {row['TN']} |")
        lines.append("")
    lines += ["V6 Validation is reconstructed from its saved group-disjoint checkpoint/threshold partitions; no Validation inference was rerun.",
              "V4/V5 Test values were reused from the fixed V5 diagnostic. Only V6 Test inference was performed."]
    (OUT / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (OUT / "evaluation.lock.json").write_text(json.dumps({"completed": True, "v6_threshold": THRESHOLD,
        "v6_checkpoint_sha256": actual_hash, "MITBIH_Test_samples": len(y_mit),
        "INCART_Test_samples": len(y_inc)}, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"validation": validation, "test": test}, indent=2))


if __name__ == "__main__":
    main()
