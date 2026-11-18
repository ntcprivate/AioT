from __future__ import annotations

import hashlib
import json
import os
from collections import Counter
from pathlib import Path

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
os.environ.setdefault("TF_ENABLE_ONEDNN_OPTS", "0")

import numpy as np
import tensorflow as tf
import wfdb
from scipy.signal import resample_poly


ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "mit-bih-st-change-database-1.0.0"
OUT = ROOT / "results/cross_dataset_stdb_v6"
RESULT = OUT / "evaluation.json"
REPORT = OUT / "report.md"
LOCK = OUT / "evaluation.lock.json"
MODELS = {
    "V4": (ROOT / "models/v4/ecg_cnn_v4_best.keras", 0.88),
    "V5": (ROOT / "models/v5/ecg_cnn_v5_best.keras", 0.33),
    "V6": (ROOT / "models/v6/ecg_cnn_v6_best.keras", 0.87),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def metrics(counter: Counter) -> dict:
    tp, tn, fp, fn = (int(counter[key]) for key in ("TP", "TN", "FP", "FN"))
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"precision": precision, "recall": recall, "f1": f1,
            "TP": tp, "TN": tn, "FP": fp, "FN": fn,
            "confusion_rows_N_V": [[tn, fp], [fn, tp]]}


def update(counter: Counter, y: np.ndarray, scores: np.ndarray, threshold: float) -> None:
    prediction = scores >= threshold
    counter.update(TP=int(np.sum((y == 1) & prediction)), TN=int(np.sum((y == 0) & ~prediction)),
                   FP=int(np.sum((y == 0) & prediction)), FN=int(np.sum((y == 1) & ~prediction)))


def verify_checksums(records: list[str]) -> None:
    expected = {}
    for line in (DB / "SHA256SUMS.txt").read_text(encoding="ascii").splitlines():
        parts = line.split(maxsplit=1)
        if len(parts) == 2:
            expected[parts[1].lstrip("*")] = parts[0]
    for record in records:
        for extension in ("hea", "dat", "atr"):
            name = f"{record}.{extension}"
            if name not in expected or sha256(DB / name) != expected[name]:
                raise RuntimeError(f"Checksum failed: {name}")


def main() -> None:
    if OUT.exists():
        raise RuntimeError(f"STDB evaluation output already exists; refusing to rerun: {OUT}")
    records = [str(number) for number in range(300, 328)]
    verify_checksums(records)
    models = {name: tf.keras.models.load_model(path, compile=False)
              for name, (path, _) in MODELS.items()}
    totals = {name: Counter() for name in MODELS}
    rows = []
    valid_n = valid_v = excluded_other = boundary_removed = numeric_removed = 0
    offsets = np.arange(-128, 128)

    for sequence, record in enumerate(records, 1):
        header = wfdb.rdheader(str(DB / record))
        if float(header.fs) != 360.0 or not header.sig_name or any(name != "ECG" for name in header.sig_name):
            raise RuntimeError(f"Unexpected signal contract for {record}: fs={header.fs}, leads={header.sig_name}")
        # Fixed before inference. Signal names provide no lead identity, so channel 0 is used for every record.
        signal = wfdb.rdrecord(str(DB / record), channels=[0], physical=True, return_res=32).p_signal[:, 0]
        signal = resample_poly(signal, 25, 36).astype(np.float32)
        annotations = wfdb.rdann(str(DB / record), "atr")
        symbols = np.asarray(annotations.symbol)
        source_samples = np.asarray(annotations.sample, dtype=np.int64)
        nv = np.isin(symbols, ["N", "V"])
        excluded_other += int(np.sum(~nv))
        centers = (source_samples[nv] * 25 + 18) // 36
        labels = (symbols[nv] == "V").astype(np.int32)
        keep = (centers >= 128) & (centers + 128 <= len(signal))
        boundary_removed += int(np.sum(~keep)); centers, labels = centers[keep], labels[keep]
        windows = signal[centers[:, None] + offsets].astype(np.float64)
        means = windows.mean(axis=1, keepdims=True); stds = windows.std(axis=1, keepdims=True)
        finite = np.isfinite(windows).all(axis=1) & np.isfinite(stds[:, 0]) & (stds[:, 0] > 1e-8)
        numeric_removed += int(np.sum(~finite)); labels = labels[finite]
        x = (((windows[finite] - means[finite]) / stds[finite]).astype(np.float32))[:, :, None]
        if not np.isfinite(x).all():
            raise RuntimeError(f"Non-finite normalized input in {record}")
        valid_n += int(np.sum(labels == 0)); valid_v += int(np.sum(labels == 1))
        local = {name: Counter() for name in MODELS}
        for name, model in models.items():
            scores = model.predict(x, batch_size=512, verbose=0).reshape(-1)
            update(local[name], labels, scores, MODELS[name][1])
            totals[name].update(local[name])
        rows.append({"record": record, "lead": "ECG channel 0", "N": int(np.sum(labels == 0)),
                     "V": int(np.sum(labels == 1)),
                     **{name: metrics(local[name]) for name in MODELS}})
        print(f"{sequence}/28 {record} N={np.sum(labels == 0)} V={np.sum(labels == 1)}", flush=True)

    result = {
        "dataset": "MIT-BIH ST Change Database v1.0.0",
        "dataset_role": "new locked cross-dataset evaluation; not used for training, checkpoint, threshold, or prior error analysis",
        "source": "https://physionet.org/content/stdb/1.0.0/",
        "checksum": "84/84 current .hea/.dat/.atr files match official SHA256SUMS.txt",
        "records": len(records), "patients": None,
        "patient_note": "Patient identifiers are not provided in the WFDB headers; record count must not be called patient count.",
        "lead": "channel 0 for every record; all channel names are generic ECG",
        "lead_policy_fixed_before_inference": True,
        "source_hz": 360, "target_hz": 250, "resample_poly": [25, 36],
        "window": 256, "normalization": "per-window z-score matching V4/V5/V6",
        "valid_N": valid_n, "valid_V": valid_v, "excluded_OTHER": excluded_other,
        "removed_boundary": boundary_removed, "removed_numeric": numeric_removed,
        "models": {name: {"threshold": threshold, "sha256": sha256(path), **metrics(totals[name])}
                   for name, (path, threshold) in MODELS.items()},
        "per_record": rows,
        "selection_or_tuning_on_stdb": False,
    }
    OUT.mkdir(parents=True)
    RESULT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    def pct(value: float) -> str:
        return f"{100 * value:.4f}%"
    lines = ["# Locked cross-dataset evaluation — MIT-BIH ST Change Database", "",
             f"Records: {len(records)}; patient IDs unavailable. Valid N/V: {valid_n:,}/{valid_v:,}.",
             f"Excluded OTHER: {excluded_other:,}; boundary: {boundary_removed:,}; numeric: {numeric_removed:,}.", "",
             "| Model | Threshold | Precision | Recall | F1 | FP | FN | Confusion matrix [N,V] |",
             "|---|---:|---:|---:|---:|---:|---:|---|"]
    for name in MODELS:
        value = result["models"][name]
        lines.append(f"| {name} | {value['threshold']:.2f} | {pct(value['precision'])} | {pct(value['recall'])} | {pct(value['f1'])} | {value['FP']} | {value['FN']} | `{value['confusion_rows_N_V']}` |")
    lines += ["", "No model, threshold, lead, or preprocessing choice was adjusted using STDB. Per-record results are in evaluation.json."]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    LOCK.write_text(json.dumps({"completed": True, "records": len(records),
                                "thresholds": {name: value[1] for name, value in MODELS.items()}}, indent=2) + "\n",
                    encoding="utf-8")
    print(json.dumps({"records": len(records), "patients": None, "valid_N": valid_n, "valid_V": valid_v,
                      "models": result["models"]}, indent=2))


if __name__ == "__main__":
    main()
