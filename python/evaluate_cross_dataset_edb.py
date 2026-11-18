from __future__ import annotations

import json
import os
import sys
from collections import Counter
from pathlib import Path

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
os.environ.setdefault("TF_ENABLE_ONEDNN_OPTS", "0")
ROOT = Path(__file__).resolve().parents[1]
# Reuse the existing WFDB/SciPy installation; both environments use Python 3.13.
sys.path.append(str(ROOT / "tools/ecg_monitor/.venv/Lib/site-packages"))

import numpy as np
import tensorflow as tf
import wfdb

EDB = ROOT / "european-st-t-database-1.0.0"
OUT = ROOT / "results/cross_dataset_edb"
RESULT = OUT / "evaluation.json"
REPORT = OUT / "report.md"
LOCK = OUT / "evaluation.lock.json"
V1_PATH = ROOT / "models/ecg_cnn_best.keras"
V4_PATH = ROOT / "models/v4/ecg_cnn_v4_best.keras"


def choose_lead(names: list[str]) -> tuple[int, str, str]:
    upper = [name.strip().upper() for name in names]
    # EDB has no II/MLII. Prefer a modified limb lead without looking at labels
    # or predictions; otherwise use the first recorded channel.
    for preferred in ("MLIII", "MLI", "D3"):
        if preferred in upper:
            return upper.index(preferred), names[upper.index(preferred)], "modified_limb_priority"
    return 0, names[0], "first_channel_no_limb_lead"


def metrics(counts: Counter) -> dict:
    tp, tn, fp, fn = (int(counts[key]) for key in ("TP", "TN", "FP", "FN"))
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    f1 = 2 * precision * recall / (precision + recall) if precision is not None and recall is not None and precision + recall else None
    return {"precision": precision, "recall": recall, "f1": f1, "TP": tp, "TN": tn, "FP": fp, "FN": fn,
            "confusion_rows_N_V": [[tn, fp], [fn, tp]]}


def update(counter: Counter, y: np.ndarray, scores: np.ndarray, threshold: float) -> None:
    pred = scores >= threshold
    counter.update(TP=int(np.sum((y == 1) & pred)), TN=int(np.sum((y == 0) & ~pred)),
                   FP=int(np.sum((y == 0) & pred)), FN=int(np.sum((y == 1) & ~pred)))


def main() -> None:
    if LOCK.exists():
        raise RuntimeError(f"EDB evaluation already completed; refusing to rerun: {LOCK}")
    OUT.mkdir(parents=True, exist_ok=True)
    records = [line.strip() for line in (EDB / "RECORDS").read_text().splitlines() if line.strip()]
    if len(records) != 90 or any(not all((EDB / f"{record}.{ext}").is_file() for ext in ("hea", "dat", "atr")) for record in records):
        raise RuntimeError("Expected 90 complete WFDB record triplets")
    v1 = tf.keras.models.load_model(V1_PATH, compile=False)
    v4 = tf.keras.models.load_model(V4_PATH, compile=False)
    totals = {"V1": Counter(), "V4": Counter()}; per_record = []
    leads = Counter(); total_n = total_v = total_other = removed_boundary = removed_numeric = 0
    offsets = np.arange(-128, 128)

    for number, record in enumerate(records, 1):
        header = wfdb.rdheader(str(EDB / record))
        if float(header.fs) != 250.0: raise RuntimeError(f"{record}: expected 250 Hz, got {header.fs}")
        channel, lead, policy = choose_lead(list(header.sig_name)); leads[lead] += 1
        signal = wfdb.rdrecord(str(EDB / record), channels=[channel], physical=True, return_res=32).p_signal[:, 0]
        ann = wfdb.rdann(str(EDB / record), "atr")
        symbols = np.asarray(ann.symbol); samples = np.asarray(ann.sample, dtype=np.int64)
        nv = np.isin(symbols, ["N", "V"]); total_other += int(np.sum(~nv))
        centers = samples[nv]; labels = (symbols[nv] == "V").astype(np.int32)
        boundary = (centers >= 128) & (centers + 128 <= len(signal))
        removed_boundary += int(np.sum(~boundary)); centers = centers[boundary]; labels = labels[boundary]
        windows = signal[centers[:, None] + offsets[None, :]].astype(np.float64)
        means = windows.mean(axis=1, keepdims=True); stds = windows.std(axis=1, keepdims=True)
        finite = np.isfinite(windows).all(axis=1) & np.isfinite(stds[:, 0]) & (stds[:, 0] > 1e-8)
        removed_numeric += int(np.sum(~finite)); windows = ((windows[finite] - means[finite]) / stds[finite]).astype(np.float32)
        labels = labels[finite]; X = windows[:, :, None]
        if not np.isfinite(X).all(): raise RuntimeError(f"{record}: non-finite normalized input")
        total_n += int(np.sum(labels == 0)); total_v += int(np.sum(labels == 1))
        scores1 = v1.predict(X, batch_size=512, verbose=0).reshape(-1)
        scores4 = v4.predict(X, batch_size=512, verbose=0).reshape(-1)
        row_counts = {"V1": Counter(), "V4": Counter()}
        update(row_counts["V1"], labels, scores1, 0.52); update(row_counts["V4"], labels, scores4, 0.88)
        totals["V1"].update(row_counts["V1"]); totals["V4"].update(row_counts["V4"])
        per_record.append({"record": record, "lead": lead, "lead_policy": policy,
                           "N": int(np.sum(labels == 0)), "V": int(np.sum(labels == 1)),
                           "removed_boundary": int(np.sum(~boundary)), "removed_numeric": int(np.sum(~finite)),
                           "V1": metrics(row_counts["V1"]), "V4": metrics(row_counts["V4"])})
        print(f"{number}/90 {record} lead={lead} N={np.sum(labels==0)} V={np.sum(labels==1)}", flush=True)

    result = {"scope": "European ST-T cross-dataset evaluation only; no training/selection/tuning",
              "records": len(records), "source_hz": 250, "target_hz": 250, "resampling": "not required",
              "window": 256, "normalization": "per-window z-score matching V1/V4",
              "lead_policy": "prefer MLIII, then MLI, then D3; otherwise first recorded channel; fixed before inference",
              "lead_counts": dict(sorted(leads.items())), "valid_N": total_n, "valid_V": total_v,
              "excluded_OTHER": total_other, "removed_boundary": removed_boundary, "removed_numeric": removed_numeric,
              "V1": {"threshold": 0.52, **metrics(totals["V1"])},
              "V4": {"threshold": 0.88, **metrics(totals["V4"])}, "per_record": per_record}
    result["V4_better_f1"] = result["V4"]["f1"] > result["V1"]["f1"]
    RESULT.write_text(json.dumps(result, indent=2) + "\n")
    def pct(value): return "n/a" if value is None else f"{100*value:.4f}%"
    lines = ["# European ST-T cross-dataset evaluation", "", f"Records: {len(records)}. Valid N/V: {total_n:,}/{total_v:,}.",
             f"Excluded OTHER: {total_other:,}; boundary: {removed_boundary:,}; numeric: {removed_numeric:,}.",
             f"Lead policy: {result['lead_policy']}. Counts: {dict(leads)}.", "",
             "| Model | Threshold | Precision | Recall | F1 | Confusion matrix N/V |", "| --- | ---: | ---: | ---: | ---: | --- |"]
    for name in ("V1", "V4"):
        value = result[name]; lines.append(f"| {name} | {value['threshold']:.2f} | {pct(value['precision'])} | {pct(value['recall'])} | {pct(value['f1'])} | `{value['confusion_rows_N_V']}` |")
    lines += ["", f"V4 better F1: {result['V4_better_f1']}.", "",
              "OTHER annotations were excluded, never relabeled as NORMAL. European ST-T was not used for training, checkpoint selection or threshold tuning.", "",
              "Per-record metrics are stored in `evaluation.json`."]
    REPORT.write_text("\n".join(lines) + "\n")
    LOCK.write_text(json.dumps({"completed": True, "records": len(records), "valid_N": total_n, "valid_V": total_v}, indent=2) + "\n")
    print(json.dumps({k: result[k] for k in ("records", "valid_N", "valid_V", "excluded_OTHER", "removed_boundary", "removed_numeric", "V1", "V4", "V4_better_f1")}, indent=2))


if __name__ == "__main__":
    main()
