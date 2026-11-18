from __future__ import annotations

import json
import os
import sys
from collections import Counter
from pathlib import Path

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
os.environ.setdefault("TF_ENABLE_ONEDNN_OPTS", "0")
ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT / "tools/ecg_monitor/.venv/Lib/site-packages"))
import numpy as np
import tensorflow as tf
import wfdb
from scipy.signal import resample_poly

DB = ROOT / "mit-bih-supraventricular-arrhythmia-database-1.0.0"
OUT = ROOT / "results/cross_dataset_svdb"
RESULT = OUT / "evaluation.json"
LOCK = OUT / "evaluation.lock.json"


def metrics(counter: Counter) -> dict:
    tp, tn, fp, fn = (int(counter[k]) for k in ("TP", "TN", "FP", "FN"))
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"precision": precision, "recall": recall, "f1": f1, "TP": tp, "TN": tn, "FP": fp, "FN": fn,
            "confusion_rows_N_V": [[tn, fp], [fn, tp]]}


def update(counter: Counter, y, scores, threshold):
    pred = scores >= threshold
    counter.update(TP=int(np.sum((y == 1) & pred)), TN=int(np.sum((y == 0) & ~pred)),
                   FP=int(np.sum((y == 0) & pred)), FN=int(np.sum((y == 1) & ~pred)))


def main() -> None:
    if LOCK.exists(): raise RuntimeError(f"SVDB already evaluated: {LOCK}")
    OUT.mkdir(parents=True, exist_ok=True)
    records = sorted(path.stem for path in DB.glob("*.hea"))
    if len(records) != 78 or any(not all((DB / f"{r}.{ext}").is_file() for ext in ("hea", "dat", "atr")) for r in records):
        raise RuntimeError("Expected 78 complete SVDB records")
    v4 = tf.keras.models.load_model(ROOT / "models/v4/ecg_cnn_v4_best.keras", compile=False)
    v5 = tf.keras.models.load_model(ROOT / "models/v5/ecg_cnn_v5_best.keras", compile=False)
    totals = {"V4": Counter(), "V5": Counter()}; rows = []
    total_n = total_v = other = boundary_removed = numeric_removed = 0
    offsets = np.arange(-128, 128)
    for i, record in enumerate(records, 1):
        header = wfdb.rdheader(str(DB / record))
        if header.fs != 128 or list(header.sig_name) != ["ECG1", "ECG2"]: raise RuntimeError(f"Unexpected header {record}")
        # Lead choice was fixed before inference: ECG1/channel 0 for every record.
        signal = wfdb.rdrecord(str(DB / record), channels=[0], physical=True, return_res=32).p_signal[:, 0]
        signal = resample_poly(signal, 125, 64).astype(np.float32)
        ann = wfdb.rdann(str(DB / record), "atr")
        symbols = np.asarray(ann.symbol); source = np.asarray(ann.sample, dtype=np.int64)
        nv = np.isin(symbols, ["N", "V"]); other += int(np.sum(~nv))
        centers = np.floor(source[nv] * 250 / 128 + 0.5).astype(np.int64)
        labels = (symbols[nv] == "V").astype(np.int32)
        keep = (centers >= 128) & (centers + 128 <= len(signal)); boundary_removed += int(np.sum(~keep))
        centers, labels = centers[keep], labels[keep]
        windows = signal[centers[:, None] + offsets].astype(np.float64)
        mean = windows.mean(axis=1, keepdims=True); std = windows.std(axis=1, keepdims=True)
        finite = np.isfinite(windows).all(axis=1) & np.isfinite(std[:, 0]) & (std[:, 0] > 1e-8)
        numeric_removed += int(np.sum(~finite)); labels = labels[finite]
        X = (((windows[finite] - mean[finite]) / std[finite]).astype(np.float32))[:, :, None]
        total_n += int(np.sum(labels == 0)); total_v += int(np.sum(labels == 1))
        scores4 = v4.predict(X, batch_size=512, verbose=0).reshape(-1)
        scores5 = v5.predict(X, batch_size=512, verbose=0).reshape(-1)
        local = {"V4": Counter(), "V5": Counter()}
        update(local["V4"], labels, scores4, 0.88); update(local["V5"], labels, scores5, 0.33)
        totals["V4"].update(local["V4"]); totals["V5"].update(local["V5"])
        rows.append({"record": record, "lead": "ECG1", "N": int(np.sum(labels == 0)), "V": int(np.sum(labels == 1)),
                     "V4": metrics(local["V4"]), "V5": metrics(local["V5"])})
        print(f"{i}/78 {record} N={np.sum(labels==0)} V={np.sum(labels==1)}", flush=True)
    result = {"dataset": "MIT-BIH Supraventricular Arrhythmia Database (SVDB)",
              "independent_protocol": "dataset/ECG1/preprocessing/thresholds fixed before inference; no tuning",
              "records": len(records), "lead": "ECG1 (channel 0) for all records", "source_hz": 128,
              "target_hz": 250, "resample_poly": [125, 64], "window": 256,
              "valid_N": total_n, "valid_V": total_v, "excluded_OTHER": other,
              "removed_boundary": boundary_removed, "removed_numeric": numeric_removed,
              "V4": {"threshold": 0.88, **metrics(totals["V4"])},
              "V5": {"threshold": 0.33, **metrics(totals["V5"])}, "per_record": rows}
    result["V5_better_f1"] = result["V5"]["f1"] > result["V4"]["f1"]
    RESULT.write_text(json.dumps(result, indent=2) + "\n")
    LOCK.write_text(json.dumps({"completed": True, "records": len(records), "thresholds": {"V4": 0.88, "V5": 0.33}}, indent=2) + "\n")
    print(json.dumps({k: result[k] for k in ("records", "valid_N", "valid_V", "excluded_OTHER", "removed_boundary", "removed_numeric", "V4", "V5", "V5_better_f1")}, indent=2))


if __name__ == "__main__":
    main()
