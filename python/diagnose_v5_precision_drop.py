from __future__ import annotations

import csv
import hashlib
import json
import os
from collections import defaultdict
from pathlib import Path

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
os.environ.setdefault("TF_ENABLE_ONEDNN_OPTS", "0")

import numpy as np
import tensorflow as tf
import wfdb


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/cnn_v5/precision_drop_diagnostic"
V4_PATH = ROOT / "models/v4/ecg_cnn_v4_best.keras"
V5_PATH = ROOT / "models/v5/ecg_cnn_v5_best.keras"
THRESHOLDS = {"V4": 0.88, "V5": 0.33}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def reconstruct_mit_centers(record_ids: np.ndarray) -> np.ndarray:
    """Reproduce 05_build_dataset.py annotation mapping, preserving dataset order."""
    source = ROOT / "mit-bih-arrhythmia-database-1.0.0"
    by_record: dict[str, list[int]] = {}
    for record in np.unique(record_ids):
        ann = wfdb.rdann(str(source / str(record)), "atr")
        header = wfdb.rdheader(str(source / str(record)))
        signal_length_250 = (int(header.sig_len) * 25 + 35) // 36
        centers = (ann.sample.astype(np.int64) * 25 + 18) // 36
        by_record[str(record)] = [
            int(center)
            for center, symbol in zip(centers, ann.symbol)
            if symbol in {"N", "V"} and center >= 128 and center + 128 <= signal_length_250
        ]

    cursor: dict[str, int] = defaultdict(int)
    result = np.empty(len(record_ids), dtype=np.int64)
    for index, record_value in enumerate(record_ids):
        record = str(record_value)
        position = cursor[record]
        if position >= len(by_record[record]):
            raise RuntimeError(f"MIT center reconstruction underflow for record {record}")
        result[index] = by_record[record][position]
        cursor[record] += 1
    for record, centers in by_record.items():
        expected = int(np.sum(record_ids == record))
        if expected != len(centers):
            raise RuntimeError(
                f"MIT center reconstruction mismatch for {record}: dataset={expected}, annotation={len(centers)}"
            )
    return result


def morphology(x: np.ndarray) -> dict[str, float | int | str]:
    signal = x[:, 0].astype(np.float64)
    region = signal[103:154]
    local = int(np.argmax(np.abs(region)))
    peak_index = 103 + local
    peak = float(signal[peak_index])
    central_energy = float(np.mean(np.square(region)))
    flank = np.concatenate((signal[:103], signal[154:]))
    flank_energy = float(np.mean(np.square(flank)))
    return {
        "qrs_peak_offset_samples": peak_index - 128,
        "qrs_peak_offset_ms": (peak_index - 128) * 4,
        "qrs_peak_signed": peak,
        "qrs_peak_abs": abs(peak),
        "qrs_polarity": "positive" if peak >= 0 else "negative",
        "qrs_ptp": float(np.ptp(region)),
        "central_energy": central_energy,
        "flank_energy": flank_energy,
        "central_to_flank_energy": central_energy / max(flank_energy, 1e-12),
    }


def neighbour_fields(records: np.ndarray, labels: np.ndarray, centers: np.ndarray, index: int) -> dict[str, object]:
    record = records[index]
    previous = index - 1 if index > 0 and records[index - 1] == record else None
    following = index + 1 if index + 1 < len(labels) and records[index + 1] == record else None

    def values(neighbour: int | None, prefix: str) -> dict[str, object]:
        if neighbour is None:
            return {f"{prefix}_label": "", f"{prefix}_distance_samples": ""}
        return {
            f"{prefix}_label": "V" if labels[neighbour] == 1 else "N",
            f"{prefix}_distance_samples": int(abs(centers[index] - centers[neighbour])),
        }

    result = values(previous, "previous")
    result.update(values(following, "next"))
    result["adjacent_v"] = int(
        (previous is not None and labels[previous] == 1)
        or (following is not None and labels[following] == 1)
    )
    return result


def metrics(y: np.ndarray, pred: np.ndarray) -> dict[str, float | int]:
    tp = int(np.sum((y == 1) & (pred == 1)))
    tn = int(np.sum((y == 0) & (pred == 0)))
    fp = int(np.sum((y == 0) & (pred == 1)))
    fn = int(np.sum((y == 1) & (pred == 0)))
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"TP": tp, "TN": tn, "FP": fp, "FN": fn, "precision": precision, "recall": recall, "f1": f1}


def load_test(dataset: str) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    if dataset == "MITBIH":
        data = np.load(ROOT / "data/processed/mitbih_nv_250hz.npz")
        split = np.load(ROOT / "data/processed/mitbih_split_indices.npz")
        indices = split["test_indices"]
        all_records = data["record_ids"].astype(str)
        all_centers = reconstruct_mit_centers(all_records)
        return data["X"][indices], data["y"][indices], all_records[indices], all_records[indices], all_centers[indices]
    data = np.load(ROOT / "data/processed/incart_v4_250hz.npz")
    mask = data["split"].astype(str) == "test"
    return (
        data["X"][mask], data["y"][mask], data["record_ids"][mask].astype(str),
        data["patient_ids"][mask].astype(str), data["centers_250hz"][mask],
    )


def main() -> None:
    if OUT.exists():
        raise RuntimeError(f"Refusing to overwrite existing diagnostic output: {OUT}")
    models = {
        "V4": tf.keras.models.load_model(V4_PATH, compile=False),
        "V5": tf.keras.models.load_model(V5_PATH, compile=False),
    }
    beat_rows: list[dict[str, object]] = []
    summary: dict[str, object] = {
        "fixed_inference": True,
        "test_used_for_tuning": False,
        "thresholds": THRESHOLDS,
        "model_sha256": {"V4": sha256(V4_PATH), "V5": sha256(V5_PATH)},
        "datasets": {},
    }
    group_rows: list[dict[str, object]] = []

    for dataset in ("MITBIH", "INCART"):
        x, y, records, patients, centers = load_test(dataset)
        if not (len(x) == len(y) == len(records) == len(patients) == len(centers)):
            raise RuntimeError(f"Length mismatch in {dataset}")
        scores = {name: model.predict(x, batch_size=512, verbose=0).reshape(-1) for name, model in models.items()}
        dataset_summary: dict[str, object] = {"samples": len(y), "N": int(np.sum(y == 0)), "V": int(np.sum(y == 1))}
        for name in models:
            pred = (scores[name] >= THRESHOLDS[name]).astype(np.int32)
            dataset_summary[name] = metrics(y, pred)
            for patient in np.unique(patients):
                for record in np.unique(records[patients == patient]):
                    mask = (patients == patient) & (records == record)
                    row = {"dataset": dataset, "patient": patient, "record": record, "model": name, "samples": int(mask.sum())}
                    row.update(metrics(y[mask], pred[mask]))
                    group_rows.append(row)
        summary["datasets"][dataset] = dataset_summary

        for index in range(len(y)):
            row: dict[str, object] = {
                "dataset": dataset, "patient": patients[index], "record": records[index],
                "beat_position_250hz": int(centers[index]), "true_label": "V" if y[index] else "N",
            }
            row.update(morphology(x[index]))
            row.update(neighbour_fields(records, y, centers, index))
            for name in models:
                prediction = int(scores[name][index] >= THRESHOLDS[name])
                row[f"{name.lower()}_score"] = float(scores[name][index])
                row[f"{name.lower()}_prediction"] = "V" if prediction else "N"
                row[f"{name.lower()}_outcome"] = (
                    "TP" if y[index] == 1 and prediction == 1 else
                    "TN" if y[index] == 0 and prediction == 0 else
                    "FP" if y[index] == 0 else "FN"
                )
            beat_rows.append(row)

    # Do not leave a misleading partial result directory if loading or inference fails.
    OUT.mkdir(parents=True)
    with (OUT / "beat_predictions.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(beat_rows[0]))
        writer.writeheader(); writer.writerows(beat_rows)
    with (OUT / "per_record_metrics.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(group_rows[0]))
        writer.writeheader(); writer.writerows(group_rows)
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
