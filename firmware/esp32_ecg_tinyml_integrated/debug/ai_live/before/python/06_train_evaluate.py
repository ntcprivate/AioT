"""Step 6: group-disjoint split, small 1D-CNN training and held-out evaluation.

Run from any directory with the project's Python 3.11 environment:
    .venv/Scripts/python.exe python/06_train_evaluate.py --epochs 30
Split selection uses labels/counts only, never model predictions on test data.
All input records are retained, including 107/217 if present (only N/V beats).
"""

import argparse
import hashlib
import json
from pathlib import Path
import sys
import time


ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "processed" / "mitbih_nv_250hz.npz"
SPLITS = DATA.with_name("mitbih_split_indices.npz")
BEST = ROOT / "models" / "ecg_cnn_best.keras"
FINAL = BEST.with_name("ecg_cnn_final.keras")
HISTORY_PLOT = ROOT / "plots" / "cnn_training_history.png"
CM_PLOT = HISTORY_PLOT.with_name("cnn_confusion_matrix.png")
METRICS = ROOT / "results" / "cnn_metrics.json"
SEED = 42
THRESHOLD = 0.5


def patient_group(record_id):
    """Known MIT-BIH duplicate patient: records 201 and 202.

    Other IDs are record-based patient proxies, not independently verified
    patient identifiers. Extend this mapping for any additional known linkage.
    """
    return "patient_201_202" if record_id in {"201", "202"} else f"record_{record_id}"


def load_data():
    if not DATA.is_file():
        raise FileNotFoundError(f"Khong tim thay du lieu Buoc 5: {DATA}")
    with np.load(DATA, allow_pickle=False) as saved:
        X, y, raw_ids = saved["X"], saved["y"], saved["record_ids"]
    if y.ndim != 1 or raw_ids.shape != y.shape or X.shape != (len(y), 256, 1):
        raise ValueError("Can X=(N,256,1), y=(N,), record_ids=(N,)")
    if X.dtype != np.float32 or y.dtype != np.int32:
        raise ValueError("Can X float32 va y int32")
    if not len(y) or not np.isfinite(X).all() or not np.isin(y, [0, 1]).all():
        raise ValueError("Du lieu rong, chua NaN/Inf, hoac nhan ngoai 0/1")
    if raw_ids.dtype.kind not in "USiu":
        raise ValueError("record_ids phai la chuoi hoac so nguyen")
    # Accept numeric or string IDs; reject unknown/non-MIT-BIH ID formats.
    ids = raw_ids.astype("U")
    if any(not value.isdigit() or len(value) != 3 for value in np.unique(ids)):
        raise ValueError("record_ids phai la ID MIT-BIH gom 3 chu so")
    groups = np.asarray([patient_group(value) for value in ids])
    if len(np.unique(groups)) < 3:
        raise ValueError("Can it nhat 3 nhom de chia Train/Validation/Test")
    return X, y, ids, groups


def check_split(parts, y, ids, groups):
    all_indices = np.concatenate(list(parts.values()))
    if (len(all_indices) != len(y)
            or not np.array_equal(np.sort(all_indices), np.arange(len(y)))):
        raise ValueError("Split indices khong phu du lieu dung mot lan")
    names = list(parts)
    for name, indices in parts.items():
        if set(np.unique(y[indices])) != {0, 1}:
            raise ValueError(f"{name} khong co du hai lop N/V")
    for i, name in enumerate(names):
        for other in names[i + 1:]:
            a, b = parts[name], parts[other]
            if (set(ids[a]) & set(ids[b])) or (set(groups[a]) & set(groups[b])):
                raise ValueError(f"Ro ri record/nhom giua {name} va {other}")


def choose_split(y, ids, groups):
    """Search 200 fixed candidates; score beat/class fractions against 70/15/15.

    GroupShuffleSplit sizes refer to groups, so actual beat ratios are reported.
    Searching class counts is permitted here; no model or test prediction exists.
    """
    target = np.asarray([0.70, 0.15, 0.15])
    total_classes = np.bincount(y, minlength=2)
    if np.any(total_classes == 0):
        raise ValueError("Bo du lieu phai co ca N va V")
    best = None
    dummy = np.zeros(len(y), dtype=np.uint8)
    for seed in range(SEED, SEED + 200):
        outer = GroupShuffleSplit(n_splits=1, test_size=0.15, random_state=seed)
        development, test = next(outer.split(dummy, y, groups))
        inner = GroupShuffleSplit(n_splits=1, test_size=0.15 / 0.85,
                                  random_state=seed + 1000)
        train_local, val_local = next(inner.split(
            dummy[development], y[development], groups[development]))
        parts = {"train": np.sort(development[train_local]),
                 "validation": np.sort(development[val_local]),
                 "test": np.sort(test)}
        counts = np.asarray([np.bincount(y[index], minlength=2)
                             for index in parts.values()])
        if np.any(counts == 0):
            continue
        fractions = counts.sum(axis=1) / len(y)
        score = float(np.square(fractions - target).sum()
                      + np.square(counts / total_classes - target[:, None]).sum())
        if best is None or score < best[0]:
            best = (score, seed, parts)
    if best is None:
        raise ValueError("Khong tim duoc split theo nhom co hai lop sau 200 seed; "
                         "khong chuyen sang chia ngau nhien tung nhip")
    score, seed, parts = best
    check_split(parts, y, ids, groups)
    return parts, seed, score


def build_model():
    model = tf.keras.Sequential([
        tf.keras.layers.Input(shape=(256, 1)),
        tf.keras.layers.Conv1D(8, 5, activation="relu"),
        tf.keras.layers.MaxPooling1D(pool_size=2),
        tf.keras.layers.Conv1D(16, 5, activation="relu"),
        tf.keras.layers.MaxPooling1D(pool_size=2),
        tf.keras.layers.GlobalAveragePooling1D(),
        tf.keras.layers.Dense(8, activation="relu"),
        tf.keras.layers.Dense(1, activation="sigmoid"),
    ], name="ecg_nv_cnn")
    model.compile(optimizer=tf.keras.optimizers.Adam(learning_rate=0.001),
                  loss="binary_crossentropy",
                  metrics=[tf.keras.metrics.BinaryAccuracy(name="accuracy"),
                           tf.keras.metrics.Precision(name="precision"),
                           tf.keras.metrics.Recall(name="recall")])
    return model


def save_plots(history, matrix):
    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    epochs = range(1, len(history["loss"]) + 1)
    for ax, metric in zip(axes, ["loss", "accuracy"]):
        ax.plot(epochs, history[metric], label="Train")
        ax.plot(epochs, history[f"val_{metric}"], label="Validation")
        ax.set(xlabel="Epoch", ylabel=metric.title(), title=metric.title())
        ax.legend()
        ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(HISTORY_PLOT, dpi=150)
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(6, 5))
    ConfusionMatrixDisplay(matrix, display_labels=["Normal (0)", "PVC (1)"]).plot(
        ax=ax, cmap="Blues", colorbar=False, values_format="d")
    ax.set_title("Independent test set (threshold = 0.5)")
    fig.tight_layout()
    fig.savefig(CM_PLOT, dpi=150)
    plt.close(fig)


def main(epochs):
    np.random.seed(SEED)
    tf.keras.utils.set_random_seed(SEED)
    tf.config.experimental.enable_op_determinism()
    X, y, ids, groups = load_data()
    parts, split_seed, split_score = choose_split(y, ids, groups)
    split_info = {}
    for name, index in parts.items():
        counts = np.bincount(y[index], minlength=2)
        split_info[name] = {
            "samples": len(index), "fraction": len(index) / len(y),
            "N": int(counts[0]), "V": int(counts[1]),
            "records": np.unique(ids[index]).tolist(),
            "patient_groups": np.unique(groups[index]).tolist(),
        }
        print(f"{name}: {json.dumps(split_info[name], ensure_ascii=False)}", flush=True)
    print("Split verified: no shared records/groups; both classes in every set.")
    print("Known patient link: 201 + 202. Other group IDs are record proxies.")
    for path in (SPLITS, BEST, HISTORY_PLOT, METRICS):
        path.parent.mkdir(parents=True, exist_ok=True)
    # Fingerprint ties sample indices to this exact input NPZ.
    digest = hashlib.sha256()
    with DATA.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    fingerprint = digest.hexdigest()
    np.savez_compressed(SPLITS, train_indices=parts["train"],
                        validation_indices=parts["validation"], test_indices=parts["test"],
                        dataset_sha256=np.asarray(fingerprint),
                        split_seed=np.asarray(split_seed))
    with np.load(SPLITS, allow_pickle=False) as saved:
        reloaded = {name: saved[f"{name}_indices"] for name in parts}
        check_split(reloaded, y, ids, groups)
        if any(not np.array_equal(parts[name], reloaded[name]) for name in parts):
            raise ValueError("Split indices doc lai khong khop")

    train, val, test = parts["train"], parts["validation"], parts["test"]
    train_counts = np.bincount(y[train], minlength=2)
    class_weight = {label: float(len(train) / (2 * train_counts[label]))
                    for label in (0, 1)}
    print(f"Class weights (Train only): {class_weight}")
    model = build_model()
    model.summary()
    print(f"Total parameters: {model.count_params()}")
    callbacks = [
        tf.keras.callbacks.ModelCheckpoint(str(BEST), monitor="val_loss", mode="min",
                                           save_best_only=True),
        tf.keras.callbacks.EarlyStopping(monitor="val_loss", patience=5,
                                         restore_best_weights=True),
        tf.keras.callbacks.TerminateOnNaN(),
    ]
    started = time.perf_counter()
    history = model.fit(X[train], y[train], validation_data=(X[val], y[val]),
                        epochs=epochs, batch_size=64, class_weight=class_weight,
                        callbacks=callbacks, verbose=2, shuffle=True).history
    elapsed = time.perf_counter() - started
    if (not history["val_loss"]
            or any(not np.isfinite(values).all() for values in history.values())):
        raise ValueError("Training history chua NaN/Inf; khong danh gia Test")
    # Load the validation-selected checkpoint, also when max epochs is reached.
    model = tf.keras.models.load_model(BEST)
    model.save(FINAL)

    # Exactly one test inference pass. All test metrics reuse these probabilities.
    probabilities = model.predict(X[test], batch_size=64, verbose=0).reshape(-1)
    if not np.isfinite(probabilities).all():
        raise ValueError("Test predictions chua NaN/Inf")
    predictions = (probabilities >= THRESHOLD).astype(np.int32)
    truth = y[test]
    matrix = confusion_matrix(truth, predictions, labels=[0, 1])
    tn, fp, fn, tp = [int(value) for value in matrix.ravel()]
    curve_precision, curve_recall, _ = precision_recall_curve(truth, probabilities)
    report = classification_report(truth, predictions, labels=[0, 1],
                                   target_names=["Normal (0)", "PVC (1)"],
                                   zero_division=0, output_dict=True)
    evaluation = {
        "threshold": THRESHOLD,
        "accuracy": float(accuracy_score(truth, predictions)),
        "precision": float(precision_score(truth, predictions, zero_division=0)),
        "recall_sensitivity_pvc": float(recall_score(truth, predictions, zero_division=0)),
        "specificity": tn / (tn + fp),
        "f1": float(f1_score(truth, predictions, zero_division=0)),
        "roc_auc": float(roc_auc_score(truth, probabilities)),
        "pr_auc_trapezoidal": float(auc(curve_recall, curve_precision)),
        "average_precision": float(average_precision_score(truth, probabilities)),
        "TP": tp, "TN": tn, "FP": fp, "FN": fn,
        "confusion_matrix": matrix.tolist(), "classification_report": report,
    }
    save_plots(history, matrix)
    results = {
        "seed": SEED, "split_seed": split_seed, "split_score": split_score,
        "split_search": "200 fixed seeds; class/sample count score only; no predictions",
        "dataset": str(DATA), "dataset_sha256": fingerprint,
        "split_indices": str(SPLITS), "splits": split_info,
        "patient_group_note": "201/202 merged; other groups are record proxies",
        "excluded_records": [], "record_policy": "All input N/V records retained, including 107/217 if present",
        "group_overlap_checked": True,
        "model_config": model.get_config(), "parameters": model.count_params(),
        "optimizer": "Adam", "initial_learning_rate": 0.001,
        "loss": "binary_crossentropy", "batch_size": 64,
        "max_epochs": epochs, "actual_epochs": len(history["loss"]),
        "best_epoch": int(np.argmin(history["val_loss"])) + 1,
        "early_stopping_patience": 5, "class_weights_train_only": class_weight,
        "training_seconds": elapsed,
        "history": {key: [float(v) for v in values] for key, values in history.items()},
        "evaluation": evaluation,
        "versions": {"python": sys.version, "numpy": np.__version__,
                     "tensorflow": tf.__version__, "scikit_learn": sklearn.__version__},
        "model_file_sizes_bytes": {str(path.relative_to(ROOT)): path.stat().st_size
                                   for path in (BEST, FINAL)},
    }
    with METRICS.open("w", encoding="utf-8") as handle:
        json.dump(results, handle, ensure_ascii=False, indent=2, allow_nan=False)
    print("\nIndependent test results (PVC is the positive class):")
    print(json.dumps(evaluation, ensure_ascii=False, indent=2))
    print(classification_report(truth, predictions, labels=[0, 1],
                                target_names=["Normal (0)", "PVC (1)"], zero_division=0))
    print(f"Epochs: {len(history['loss'])}; best epoch: {results['best_epoch']}; "
          f"training time: {elapsed:.1f}s")
    for path in (SPLITS, BEST, FINAL, HISTORY_PLOT, CM_PLOT, METRICS):
        if not path.is_file() or path.stat().st_size == 0:
            raise OSError(f"Missing or empty output: {path}")
        print(f"Saved: {path} ({path.stat().st_size} bytes)")
    print("Step 6 complete. No TFLite conversion or ESP32 deployment performed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--epochs", type=int, default=30, help="Maximum epochs (1-30)")
    args = parser.parse_args()
    if not 1 <= args.epochs <= 30:
        parser.error("--epochs must be between 1 and 30")
    try:
        import numpy as np
        import tensorflow as tf
        import sklearn
        from sklearn.model_selection import GroupShuffleSplit
        from sklearn.metrics import (ConfusionMatrixDisplay, accuracy_score, auc,
                                     average_precision_score, classification_report,
                                     confusion_matrix, f1_score, precision_recall_curve,
                                     precision_score, recall_score, roc_auc_score)
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        main(args.epochs)
    except (ImportError, OSError, ValueError, KeyError, RuntimeError) as error:
        print(f"ERROR: {type(error).__name__}: {error}", file=sys.stderr)
        sys.exit(1)
