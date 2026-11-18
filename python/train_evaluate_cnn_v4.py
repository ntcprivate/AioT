from __future__ import annotations

import hashlib
import json
import os
import random
from pathlib import Path

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
os.environ.setdefault("TF_ENABLE_ONEDNN_OPTS", "0")
import numpy as np
import tensorflow as tf

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/processed/incart_v4_250hz.npz"
MIT = ROOT / "data/processed/mitbih_nv_250hz.npz"
MIT_SPLIT = ROOT / "data/processed/mitbih_split_indices.npz"
MODELS = ROOT / "models/v4"
RESULTS = ROOT / "results/cnn_v4"
BEST = MODELS / "ecg_cnn_v4_best.keras"
LOCK = RESULTS / "test_evaluation.lock.json"
SEED = 42
THRESHOLDS = np.round(np.arange(0.05, 0.951, 0.01), 2)


def model_v1_architecture() -> tf.keras.Model:
    return tf.keras.Sequential([
        tf.keras.layers.Input((256, 1)),
        tf.keras.layers.Conv1D(8, 5, activation="relu"),
        tf.keras.layers.MaxPooling1D(2),
        tf.keras.layers.Conv1D(16, 5, activation="relu"),
        tf.keras.layers.MaxPooling1D(2),
        tf.keras.layers.GlobalAveragePooling1D(),
        tf.keras.layers.Dense(8, activation="relu"),
        tf.keras.layers.Dense(1, activation="sigmoid"),
    ], name="ecg_nv_cnn_v4")


def metrics(y: np.ndarray, scores: np.ndarray, threshold: float) -> dict:
    pred = scores >= threshold
    tp = int(np.sum((y == 1) & pred)); tn = int(np.sum((y == 0) & ~pred))
    fp = int(np.sum((y == 0) & pred)); fn = int(np.sum((y == 1) & ~pred))
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"threshold": float(threshold), "precision": precision, "recall": recall, "f1": f1,
            "TP": tp, "TN": tn, "FP": fp, "FN": fn,
            "confusion_rows_N_V": [[tn, fp], [fn, tp]]}


def best_threshold(y: np.ndarray, scores: np.ndarray) -> dict:
    rows = [metrics(y, scores, float(t)) for t in THRESHOLDS]
    return max(rows, key=lambda row: (row["f1"], row["precision"], -row["threshold"]))


class ValidationSelector(tf.keras.callbacks.Callback):
    def __init__(self, X: np.ndarray, y: np.ndarray):
        super().__init__(); self.X = X; self.y = y; self.best = -1.0; self.wait = 0; self.rows = []

    def on_epoch_end(self, epoch, logs=None):
        scores = self.model.predict(self.X, batch_size=256, verbose=0).reshape(-1)
        row = best_threshold(self.y, scores); row["epoch"] = epoch + 1; self.rows.append(row)
        if row["f1"] > self.best + 1e-12:
            self.best = row["f1"]; self.wait = 0; self.model.save(BEST)
        else:
            self.wait += 1
        print(f" val_pvc_f1={row['f1']:.6f} P={row['precision']:.6f} R={row['recall']:.6f} t={row['threshold']:.2f}")
        if self.wait >= 5: self.model.stop_training = True


def per_patient(y, scores, patients, threshold):
    return {pid: metrics(y[patients == pid], scores[patients == pid], threshold)
            for pid in sorted(set(patients), key=int)}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    if LOCK.exists():
        raise RuntimeError(f"Independent Test already evaluated; refusing to rerun: {LOCK}")
    random.seed(SEED); np.random.seed(SEED); tf.keras.utils.set_random_seed(SEED)
    tf.config.threading.set_inter_op_parallelism_threads(1)
    tf.config.threading.set_intra_op_parallelism_threads(2)
    tf.config.experimental.enable_op_determinism()
    MODELS.mkdir(parents=True, exist_ok=True); RESULTS.mkdir(parents=True, exist_ok=True)

    inc = np.load(DATA); mit = np.load(MIT); split = np.load(MIT_SPLIT)
    train_mask = inc["split"] == "train"; val_mask = inc["split"] == "validation"; test_mask = inc["split"] == "test"
    mit_train = split["train_indices"]
    X_train = np.concatenate([mit["X"][mit_train], inc["X"][train_mask]])
    y_train = np.concatenate([mit["y"][mit_train], inc["y"][train_mask]]).astype(np.int32)
    X_val, y_val = inc["X"][val_mask], inc["y"][val_mask].astype(np.int32)
    counts = np.bincount(y_train, minlength=2)
    class_weight = {i: float(len(y_train) / (2 * counts[i])) for i in (0, 1)}

    model = model_v1_architecture()
    if model.count_params() != 849: raise RuntimeError("V1 architecture parameter mismatch")
    model.compile(optimizer=tf.keras.optimizers.Adam(0.001), loss="binary_crossentropy")
    selector = ValidationSelector(X_val, y_val)
    model.fit(X_train, y_train, epochs=30, batch_size=64, shuffle=True, verbose=2,
              class_weight=class_weight, callbacks=[selector, tf.keras.callbacks.TerminateOnNaN()])
    model = tf.keras.models.load_model(BEST, compile=False)
    val_scores = model.predict(X_val, batch_size=256, verbose=0).reshape(-1)
    selected = best_threshold(y_val, val_scores)
    selected_epoch = max(selector.rows, key=lambda row: (row["f1"], row["precision"], -row["threshold"]))["epoch"]
    frozen = {"seed": SEED, "architecture": "V1 849 parameters", "train_samples": int(len(y_train)),
              "mit_train_samples": int(len(mit_train)), "incart_train_samples": int(train_mask.sum()),
              "incart_validation_samples": int(val_mask.sum()), "class_weight": class_weight,
              "best_epoch": selected_epoch, "epochs_run": len(selector.rows),
              "selection": "max INCART Validation PVC F1; tie precision then lower threshold",
              "selected_threshold": selected["threshold"], "validation": selected,
              "test_used_for_selection": False, "model_sha256": sha(BEST)}
    (RESULTS / "selection.json").write_text(json.dumps(frozen, indent=2) + "\n")

    # The only Test inference block.  Threshold and checkpoint are already frozen above.
    X_test, y_test = inc["X"][test_mask], inc["y"][test_mask].astype(np.int32)
    patients = inc["patient_ids"][test_mask]
    v1 = tf.keras.models.load_model(ROOT / "models/ecg_cnn_best.keras", compile=False)
    v1_scores = v1.predict(X_test, batch_size=256, verbose=0).reshape(-1)
    v4_scores = model.predict(X_test, batch_size=256, verbose=0).reshape(-1)
    result = {
        "scope": "single locked evaluation on patient-disjoint INCART Test",
        "samples": int(len(y_test)), "N": int(np.sum(y_test == 0)), "V": int(np.sum(y_test == 1)),
        "V1": {"overall": metrics(y_test, v1_scores, 0.52),
               "per_patient": per_patient(y_test, v1_scores, patients, 0.52)},
        "V4": {"overall": metrics(y_test, v4_scores, selected["threshold"]),
               "per_patient": per_patient(y_test, v4_scores, patients, selected["threshold"])},
    }
    result["V4_better_f1"] = result["V4"]["overall"]["f1"] > result["V1"]["overall"]["f1"]
    (RESULTS / "test_evaluation.json").write_text(json.dumps(result, indent=2) + "\n")
    LOCK.write_text(json.dumps({"locked": True, "model_sha256": sha(BEST),
                                "threshold": selected["threshold"], "test_samples": len(y_test)}, indent=2) + "\n")
    print(json.dumps({"selection": frozen, "test": result}, indent=2))


if __name__ == "__main__":
    main()
