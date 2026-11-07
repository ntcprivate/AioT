"""Step 6.5: validate artifacts and select a threshold on Validation only.

No training, test inference, split changes or model writes are performed.
Run: .venv/Scripts/python.exe python/065_optimize_threshold.py
"""

from collections import Counter
import csv
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data/processed/mitbih_nv_250hz.npz"
SPLIT = DATA.with_name("mitbih_split_indices.npz")
MODEL = ROOT / "models/ecg_cnn_best.keras"
TRAINING = ROOT / "results/cnn_metrics.json"
SUMMARY = DATA.with_name("mitbih_record_summary.csv")
RAW = ROOT / "mit-bih-arrhythmia-database-1.0.0"
RESULTS = ROOT / "results"
PLOTS = ROOT / "plots"
MIN_RECALL = 0.90


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)


def group(record_id):
    return "patient_201_202" if record_id in {"201", "202"} else f"record_{record_id}"


def metrics_from_counts(threshold, tp, tn, fp, fn):
    def ratio(a, b):
        return a / b if b else 0.0
    return {"threshold": threshold, "accuracy": ratio(tp + tn, tp + tn + fp + fn),
            "precision": ratio(tp, tp + fp), "recall": ratio(tp, tp + fn),
            "specificity": ratio(tn, tn + fp), "f1": ratio(2 * tp, 2 * tp + fp + fn),
            "TP": tp, "TN": tn, "FP": fp, "FN": fn,
            "false_positive_rate": ratio(fp, fp + tn)}


def select_threshold(rows):
    # Exact integer/fraction comparisons implement the specified ties.
    eligible = [r for r in rows if 10 * r["TP"] >= 9 * (r["TP"] + r["FN"])]
    if not eligible:
        return next(r for r in rows if r["threshold"] == 0.5), True
    def rank(r):
        return (Fraction(2 * r["TP"], 2 * r["TP"] + r["FP"] + r["FN"]),
                Fraction(r["TP"], r["TP"] + r["FP"]), -r["threshold"])
    return max(eligible, key=rank), False


def load_and_validate(training):
    with np.load(DATA, allow_pickle=False) as saved:
        if not {"X", "y", "record_ids"} <= set(saved.files):
            raise ValueError(f"NPZ keys khong hop le: {saved.files}")
        X, y, raw_ids = saved["X"], saved["y"], saved["record_ids"]
    if y.ndim != 1 or X.shape != (len(y), 256, 1) or raw_ids.shape != y.shape:
        raise ValueError("Can X=(N,256,1), y=(N,), record_ids=(N,)")
    if X.dtype != np.float32 or y.dtype != np.int32:
        raise ValueError("Can X float32, y int32")
    if not len(y) or not np.isfinite(X).all() or not np.isin(y, [0, 1]).all():
        raise ValueError("Du lieu rong, NaN/Inf hoac nhan ngoai 0/1")
    if raw_ids.dtype.kind not in "USiu":
        raise ValueError("record_ids phai la chuoi hoac so nguyen")
    ids = raw_ids.astype("U")
    if any(len(r) != 3 or not r.isdigit() for r in np.unique(ids)):
        raise ValueError("ID record MIT-BIH khong hop le")
    groups = np.asarray([group(r) for r in ids])
    with np.load(SPLIT, allow_pickle=False) as saved:
        keys = saved.files
        print(f"Split keys: {keys}")
        # This is the actual schema written by Step 6; do not guess other keys.
        required = {"train_indices", "validation_indices", "test_indices"}
        if not required <= set(keys):
            raise ValueError(f"Can cac key {sorted(required)}; tim thay {keys}")
        parts = {name: saved[f"{name}_indices"]
                 for name in ("train", "validation", "test")}
        split_hash = str(saved["dataset_sha256"].item()) if "dataset_sha256" in keys else None
    fingerprint = sha256(DATA)
    for expected in (split_hash, training.get("dataset_sha256")):
        if expected and expected != fingerprint:
            raise ValueError("Dataset SHA256 khong khop split/ket qua huan luyen")
    for name, index in parts.items():
        if (index.ndim != 1 or index.dtype.kind not in "iu" or not len(index)
                or np.any(index < 0) or np.any(index >= len(y))):
            raise ValueError(f"Chi so {name} sai dtype, shape hoac vuot pham vi")
        if len(np.unique(index)) != len(index):
            raise ValueError(f"Chi so trung lap trong {name}")
        if set(np.unique(y[index])) != {0, 1}:
            raise ValueError(f"{name} khong co ca N va V")
    combined = np.concatenate(list(parts.values()))
    if not np.array_equal(np.sort(combined), np.arange(len(y))):
        raise ValueError("Split trung lap, thieu mau hoac khong phu dataset dung mot lan")
    split_info = {}
    for name, index in parts.items():
        split_info[name] = {"samples": len(index),
                            "N": int(np.count_nonzero(y[index] == 0)),
                            "V": int(np.count_nonzero(y[index] == 1)),
                            "records": np.unique(ids[index]).tolist(),
                            "groups": np.unique(groups[index]).tolist()}
        previous = training.get("splits", {}).get(name)
        if previous:
            for key in ("samples", "N", "V", "records"):
                if previous.get(key) != split_info[name][key]:
                    raise ValueError(f"Split {name}/{key} khac metadata Buoc 6")
    names = list(parts)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            for key in ("records", "groups"):
                if set(split_info[a][key]) & set(split_info[b][key]):
                    raise ValueError(f"Ro ri {key} giua {a} va {b}")
    return X, y, ids, parts, split_info, fingerprint, bool(split_hash)


def history_audit(training):
    history = training.get("history", {})
    keys = ("loss", "val_loss", "accuracy", "val_accuracy")
    if not all(history.get(key) for key in keys):
        return {"status": "UNKNOWN", "reason": "Numeric history unavailable",
                "recorded_best_epoch": training.get("best_epoch"),
                "limitation": "No invented epoch values or overfitting severity"}
    arrays = {key: np.asarray(history[key], dtype=float) for key in keys}
    if (any(a.ndim != 1 or not np.isfinite(a).all() for a in arrays.values())
            or len({len(a) for a in arrays.values()}) != 1):
        return {"status": "NEEDS_REVIEW", "reason": "Invalid numeric history"}
    best = int(np.argmin(arrays["val_loss"]))
    deltas = {key: float(a[-1] - a[best]) for key, a in arrays.items()}
    evidence = deltas["loss"] < 0 and deltas["val_loss"] > 0 and best < len(arrays["loss"]) - 1
    return {"status": "ANALYZED", "best_epoch": best + 1,
            "actual_epochs": len(arrays["loss"]),
            "best_epoch_values": {key: float(a[best]) for key, a in arrays.items()},
            "last_epoch_values": {key: float(a[-1]) for key, a in arrays.items()},
            "changes_after_best": deltas,
            "validation_loss_relative_increase": deltas["val_loss"] / float(arrays["val_loss"][best])
                if arrays["val_loss"][best] != 0 else None,
            "post_best_values": {key: a[best + 1:].tolist() for key, a in arrays.items()},
            "overfitting_signs": evidence,
            "assessment": "Diverging train/validation loss after best epoch" if evidence else
                          "No divergence established by this simple history check",
            "limitation": "Descriptive evidence only; no universal severity cutoff. Train loss is class-weighted, validation loss is unweighted; absolute loss gaps are not directly comparable."}


def paced_audit(y, ids, parts):
    summary = {}
    if SUMMARY.is_file():
        with SUMMARY.open(encoding="utf-8-sig", newline="") as handle:
            summary = {row["record_id"]: row for row in csv.DictReader(handle)}
    records = {}
    for record_id in ("102", "104", "107", "217"):
        item = {"dataset_N": int(np.count_nonzero((ids == record_id) & (y == 0))),
                "dataset_V": int(np.count_nonzero((ids == record_id) & (y == 1))),
                "present_in_dataset": bool(np.any(ids == record_id)),
                "split_membership": [name for name, index in parts.items()
                                     if np.any(ids[index] == record_id)],
                "step5_csv": summary.get(record_id), "evidence_status": "UNKNOWN"}
        try:
            path = RAW / record_id
            header = wfdb.rdheader(str(path))
            annotation = wfdb.rdann(str(path), "atr")
            counts = dict(Counter(annotation.symbol))
            paced = counts.get("/", 0) + counts.get("f", 0)
            item.update(leads=header.sig_name, header_comments=header.comments,
                        annotation_counts=counts, paced_annotation_count=paced,
                        paced_symbols={"/": "paced beat", "f": "fusion of paced and normal beat"},
                        evidence_status="CONFIRMED" if paced else "NEEDS_REVIEW",
                        evidence_files=[str(path.with_suffix(".hea")), str(path.with_suffix(".atr"))],
                        no_mlii="MLII" not in [s.strip().upper() for s in header.sig_name])
        except (OSError, ValueError, IndexError, EOFError) as error:
            item["error"] = str(error)
        records[record_id] = item
    return {"records": records, "test_inference_performed": False,
            "risk": "Paced/fusion morphology and patient-specific signal context may alter N/V discrimination. Non-N/V annotations were omitted, but that does not make a paced record equivalent to a non-paced record.",
            "action": "No records removed; no split or weights changed. Any exclusion must be a separate prespecified experiment, without choosing exclusions from test performance."}


def source_evidence(path, terms):
    if not path.is_file():
        return {"status": "UNKNOWN", "path": str(path), "reason": "Source unavailable"}
    lines = path.read_text(encoding="utf-8").splitlines()
    return {"path": str(path), "sha256": sha256(path),
            "status": "NEEDS_REVIEW",
            "excerpts": [{"line": i + 1, "text": line.strip()}
                         for i, line in enumerate(lines) if any(t in line for t in terms)],
            "limitation": "Current source evidence only; keyword excerpts are not proof of historical execution. Training artifacts do not record executed source hashes."}


def leakage_audit(y, parts, split_info, training, fingerprint, split_hash_present):
    counts = np.bincount(y[parts["train"]], minlength=2)
    expected_weights = {str(i): len(parts["train"]) / (2 * int(counts[i])) for i in (0, 1)}
    recorded = training.get("class_weights_train_only", {})
    match = all(key in recorded and np.isclose(recorded[key], value)
                for key, value in expected_weights.items())
    return {
        "index_record_known_group_disjointness": {"status": "PASS", "evidence": split_info},
        "known_patient_201_202": {"status": "PASS" if all(
            r in set(ids for s in split_info.values() for ids in s["records"])
            for r in ("201", "202")) else "UNKNOWN",
            "evidence": "201/202 mapped to same group; disjointness checked on saved indices"},
        "dataset_fingerprint": {"status": "PASS" if split_hash_present else "UNKNOWN",
                                "sha256": fingerprint},
        "train_only_weight_arithmetic": {"status": "PASS" if match else "NEEDS_REVIEW",
                                         "expected": expected_weights, "recorded": recorded},
        "historical_training_and_sampling": source_evidence(
            ROOT / "python/06_train_evaluate.py",
            ("train_counts", "class_weight", "model.fit", "X[train]", "oversampl", "SMOTE")),
        "source_review_findings": {
            "status": "NEEDS_REVIEW",
            "reviewed_sha256": {
                "05_build_dataset.py": "fc811be21a0c7a386bc47f7af108c4b5590d658f647469564a12a72ce0c195be",
                "06_train_evaluate.py": "4f63cedbb5a366c45032e68ce9e18574550b8d234638ac10994565d0cb729792"},
            "step6_review": "Manual review at script creation: weights calculated from y[train], fit uses X[train]/y[train], validation passed separately; no oversampling call found.",
            "step5_review": "Manual review at script creation: fixed resample ratio and per-beat mean/std; no dataset-fitted scaler found.",
            "limitation": "These findings apply only to the reviewed hashes. Compare current source evidence hashes; historical executed source was not fingerprinted."},
        "historical_preprocessing": source_evidence(
            ROOT / "python/05_build_dataset.py",
            ("beat.std", "beat.mean", "resample_poly", "fit(", "scaler", "LABELS")),
        "current_threshold_test_access": {
            "status": "PASS", "evidence": "Only model.predict(X[validation_indices]) is called; test indices used only for structural/provenance audit.",
            "source_sha256": sha256(Path(__file__))},
        "patient_identity_completeness": {"status": "UNKNOWN",
            "reason": "201/202 linked explicitly; other record IDs are patient proxies, not independently verified identities"},
        "previous_test_exposure": {"status": "NEEDS_REVIEW",
            "reason": "Test results already viewed in Step 6. No new independent test claim. Split selection used class counts, so holdout construction was label-informed."},
        "overall_status": "NEEDS_REVIEW",
        "note": "Structural PASS does not certify historical execution or all patient relationships."}


def plot_thresholds(rows, selected):
    thresholds = [r["threshold"] for r in rows]
    for filename, keys, ylabel in (
        ("threshold_precision_recall.png", ("precision", "recall", "f1"), "Metric"),
        ("threshold_false_positives.png", ("FP", "FN"), "Number of beats"),
    ):
        fig, ax = plt.subplots(figsize=(10, 5))
        for key in keys:
            ax.plot(thresholds, [r[key] for r in rows], label=key)
        ax.axvline(0.5, color="gray", linestyle=":", label="Default 0.50")
        ax.axvline(selected, color="black", linestyle="--", label=f"Selected {selected:.2f}")
        ax.set(title="Validation only - threshold analysis", xlabel="Sigmoid score threshold", ylabel=ylabel)
        ax.grid(alpha=0.3)
        ax.legend()
        fig.tight_layout()
        fig.savefig(PLOTS / filename, dpi=150)
        plt.close(fig)


def main():
    training = json.loads(TRAINING.read_text(encoding="utf-8")) if TRAINING.is_file() else {}
    X, y, ids, parts, split_info, fingerprint, hash_present = load_and_validate(training)
    print(f"Validated X={X.shape}/{X.dtype}, y={y.shape}/{y.dtype}; NaN/Inf=False")
    for name, info in split_info.items():
        print(name, json.dumps(info))
    for directory in (RESULTS, PLOTS):
        directory.mkdir(parents=True, exist_ok=True)
    paced = paced_audit(y, ids, parts)
    leakage = leakage_audit(y, parts, split_info, training, fingerprint, hash_present)
    write_json(RESULTS / "paced_records_audit.json", paced)
    write_json(RESULTS / "data_leakage_audit.json", leakage)
    history = history_audit(training)
    print("Overfitting audit:", json.dumps(history, indent=2))
    model_hash = sha256(MODEL)
    model = tf.keras.models.load_model(MODEL, compile=False)
    if tuple(model.input_shape) != (None, 256, 1) or tuple(model.output_shape) != (None, 1):
        raise ValueError(f"Unexpected model shapes: {model.input_shape}, {model.output_shape}")
    if getattr(model.layers[-1].activation, "__name__", "") != "sigmoid":
        raise ValueError("Can dau ra sigmoid")
    if training.get("parameters") is not None and model.count_params() != training["parameters"]:
        raise ValueError("Model parameter count khac metadata Buoc 6")
    print(f"Model parameters: {model.count_params()}")
    validation_indices = parts["validation"]
    truth = y[validation_indices]
    # Sole inference call in Step 6.5: absolutely no Test inference.
    scores = model.predict(X[validation_indices], batch_size=64, verbose=0)
    if scores.shape != (len(truth), 1):
        raise ValueError("Validation prediction shape khong hop le")
    scores = scores[:, 0]
    if not np.isfinite(scores).all() or np.any((scores < 0) | (scores > 1)):
        raise ValueError("Diem sigmoid khong hop le hoac NaN/Inf")
    rows = []
    for tick in range(5, 96):
        threshold = tick / 100
        predicted = scores >= threshold
        tp = int(np.count_nonzero(predicted & (truth == 1)))
        tn = int(np.count_nonzero(~predicted & (truth == 0)))
        fp = int(np.count_nonzero(predicted & (truth == 0)))
        fn = int(np.count_nonzero(~predicted & (truth == 1)))
        rows.append(metrics_from_counts(threshold, tp, tn, fp, fn))
    selected, fallback = select_threshold(rows)
    baseline = next(r for r in rows if r["threshold"] == 0.5)
    changes = {key: selected[key] - baseline[key] for key in baseline if key != "threshold"}
    with (RESULTS / "threshold_validation.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    plot_thresholds(rows, selected["threshold"])
    if sha256(MODEL) != model_hash:
        raise ValueError("Model file changed during analysis")
    config = {"model_path": str(MODEL), "model_sha256": model_hash,
              "model_parameter_count": model.count_params(), "input_shape": list(model.input_shape),
              "dataset_sha256": fingerprint, "split_sha256": sha256(SPLIT),
              "original_threshold": 0.5, "selected_threshold": selected["threshold"],
              "selection_criterion": "Validation recall >= 0.90; maximize F1, then precision, then smaller threshold",
              "minimum_validation_recall": MIN_RECALL, "fallback_used": fallback,
              "fallback_reason": "No grid threshold meets recall >= 0.90" if fallback else None,
              "validation_metrics_original": baseline, "validation_metrics_selected": selected,
              "metric_changes": changes, "validation_samples": len(truth),
              "validation_class_fractions": {"Normal": float(np.mean(truth == 0)), "PVC": float(np.mean(truth == 1))},
              "test_used_for_selection": False, "test_inference_performed": False,
              "test_note": "Previously exposed Test is not a new independent evaluation. No Test inference in Step 6.5.",
              "score_note": "Sigmoid scores are not automatically calibrated probabilities.",
              "overfitting_audit": history}
    write_json(RESULTS / "optimized_threshold.json", config)
    print("\nValidation comparison (delta = selected - default):")
    print(f"{'metric':24s} {'default 0.50':>14s} {'selected':>14s} {'delta':>14s}")
    for key in baseline:
        print(f"{key:24s} {baseline[key]:14.6f} {selected[key]:14.6f} {(selected[key]-baseline[key]):14.6f}")
    print(f"Selected threshold={selected['threshold']:.2f}; fallback={fallback}")
    if fallback:
        print("No threshold met Validation recall >= 90%; using 0.50 fallback.")
    print("Paced records:", json.dumps(paced, indent=2))
    print("Leakage overall: NEEDS_REVIEW; see audit for PASS/UNKNOWN evidence.")
    for path in (RESULTS / "threshold_validation.csv", RESULTS / "optimized_threshold.json",
                 RESULTS / "paced_records_audit.json", RESULTS / "data_leakage_audit.json",
                 PLOTS / "threshold_precision_recall.png", PLOTS / "threshold_false_positives.png"):
        if not path.is_file() or not path.stat().st_size:
            raise OSError(f"Missing or empty output: {path}")
        print(f"Saved: {path}")


if __name__ == "__main__":
    try:
        import numpy as np
        import tensorflow as tf
        import wfdb
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        main()
    except (ImportError, OSError, ValueError, KeyError, IndexError, RuntimeError) as error:
        print(f"ERROR: {type(error).__name__}: {error}", file=sys.stderr)
        sys.exit(1)
