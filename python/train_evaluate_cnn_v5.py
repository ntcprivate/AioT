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
MIT = ROOT / "data/processed/mitbih_nv_250hz.npz"
MIT_SPLIT = ROOT / "data/processed/mitbih_split_indices.npz"
INCART = ROOT / "data/processed/incart_v4_250hz.npz"
V4_PATH = ROOT / "models/v4/ecg_cnn_v4_best.keras"
MODELS = ROOT / "models/v5"
RESULTS = ROOT / "results/cnn_v5"
BEST = MODELS / "ecg_cnn_v5_best.keras"
SEED = 42
THRESHOLDS = np.round(np.arange(0.05, 0.951, 0.01), 2)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_v5() -> tf.keras.Model:
    inp = tf.keras.layers.Input((256, 1), name="ecg_256")
    # Position-aware central-QRS branch: crop to central 128 samples and keep
    # spatial position through Flatten rather than global averaging.
    center = tf.keras.layers.Cropping1D((64, 64), name="central_qrs_128")(inp)
    center = tf.keras.layers.Conv1D(8, 5, activation="relu", name="qrs_conv5_a")(center)
    center = tf.keras.layers.MaxPooling1D(2, name="qrs_pool_a")(center)
    center = tf.keras.layers.Conv1D(12, 5, activation="relu", name="qrs_conv5_b")(center)
    center = tf.keras.layers.MaxPooling1D(2, name="qrs_pool_b")(center)
    center = tf.keras.layers.Flatten(name="qrs_position_features")(center)
    center = tf.keras.layers.Dense(8, activation="relu", name="qrs_dense")(center)

    # Full-window morphology/context branch with a wider receptive field.
    context = tf.keras.layers.Conv1D(8, 15, activation="relu", name="context_conv15")(inp)
    context = tf.keras.layers.MaxPooling1D(4, name="context_pool")(context)
    context = tf.keras.layers.Conv1D(12, 9, activation="relu", name="context_conv9")(context)
    context = tf.keras.layers.GlobalAveragePooling1D(name="context_gap")(context)
    context = tf.keras.layers.Dense(8, activation="relu", name="context_dense")(context)

    merged = tf.keras.layers.Concatenate(name="multiscale_merge")([center, context])
    merged = tf.keras.layers.Dense(8, activation="relu", name="fusion_dense")(merged)
    out = tf.keras.layers.Dense(1, activation="sigmoid", name="pvc_probability")(merged)
    return tf.keras.Model(inp, out, name="ecg_nv_cnn_v5_multiscale")


def metrics(y, scores, threshold):
    pred = scores >= threshold
    tp = int(np.sum((y == 1) & pred)); tn = int(np.sum((y == 0) & ~pred))
    fp = int(np.sum((y == 0) & pred)); fn = int(np.sum((y == 1) & ~pred))
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"threshold": float(threshold), "precision": precision, "recall": recall, "f1": f1,
            "TP": tp, "TN": tn, "FP": fp, "FN": fn, "confusion_rows_N_V": [[tn, fp], [fn, tp]]}


def select_threshold(y, scores):
    return max((metrics(y, scores, threshold) for threshold in THRESHOLDS),
               key=lambda row: (row["f1"], row["precision"], -row["threshold"]))


class Selector(tf.keras.callbacks.Callback):
    def __init__(self, X, y):
        super().__init__(); self.X = X; self.y = y; self.best_f1 = -1.0; self.best_precision = -1.0
        self.wait = 0; self.rows = []

    def on_epoch_end(self, epoch, logs=None):
        scores = self.model.predict(self.X, batch_size=512, verbose=0).reshape(-1)
        row = select_threshold(self.y, scores); row["epoch"] = epoch + 1; self.rows.append(row)
        improved = row["f1"] > self.best_f1 + 1e-12 or (abs(row["f1"] - self.best_f1) <= 1e-12 and row["precision"] > self.best_precision)
        if improved:
            self.best_f1, self.best_precision, self.wait = row["f1"], row["precision"], 0
            self.model.save(BEST)
        else: self.wait += 1
        print(f" val_f1={row['f1']:.6f} P={row['precision']:.6f} R={row['recall']:.6f} t={row['threshold']:.2f}")
        if self.wait >= 5: self.model.stop_training = True


def main() -> None:
    if (RESULTS / "evaluation.json").exists():
        raise RuntimeError("V5 evaluation already exists; refusing to retrain")
    MODELS.mkdir(parents=True, exist_ok=True); RESULTS.mkdir(parents=True, exist_ok=True)
    random.seed(SEED); np.random.seed(SEED); tf.keras.utils.set_random_seed(SEED)
    tf.config.threading.set_inter_op_parallelism_threads(1); tf.config.threading.set_intra_op_parallelism_threads(2)
    tf.config.experimental.enable_op_determinism()

    mit = np.load(MIT); split = np.load(MIT_SPLIT); inc = np.load(INCART)
    mit_train, mit_val = split["train_indices"], split["validation_indices"]
    inc_train = inc["split"] == "train"; inc_val = inc["split"] == "validation"
    X_train = np.concatenate([mit["X"][mit_train], inc["X"][inc_train]])
    y_train = np.concatenate([mit["y"][mit_train], inc["y"][inc_train]]).astype(np.int32)
    X_inc_val, y_inc_val = inc["X"][inc_val], inc["y"][inc_val].astype(np.int32)
    X_mit_val, y_mit_val = mit["X"][mit_val], mit["y"][mit_val].astype(np.int32)
    counts = np.bincount(y_train, minlength=2)
    class_weight = {i: float(len(y_train) / (2 * counts[i])) for i in (0, 1)}

    model = build_v5()
    if model.count_params() >= 10_000: raise RuntimeError(f"V5 too large: {model.count_params()}")
    model.compile(optimizer=tf.keras.optimizers.Adam(0.001), loss="binary_crossentropy")
    selector = Selector(X_inc_val, y_inc_val)
    model.fit(X_train, y_train, epochs=30, batch_size=64, shuffle=True, verbose=2,
              class_weight=class_weight, callbacks=[selector, tf.keras.callbacks.TerminateOnNaN()])
    v5 = tf.keras.models.load_model(BEST, compile=False)
    scores5_inc = v5.predict(X_inc_val, batch_size=512, verbose=0).reshape(-1)
    selected = select_threshold(y_inc_val, scores5_inc); threshold5 = selected["threshold"]
    v4 = tf.keras.models.load_model(V4_PATH, compile=False)
    scores4_inc = v4.predict(X_inc_val, batch_size=512, verbose=0).reshape(-1)
    scores4_mit = v4.predict(X_mit_val, batch_size=512, verbose=0).reshape(-1)
    scores5_mit = v5.predict(X_mit_val, batch_size=512, verbose=0).reshape(-1)
    comparison = {
        "INCART_Validation": {"samples": len(y_inc_val), "N": int(np.sum(y_inc_val == 0)), "V": int(np.sum(y_inc_val == 1)),
                              "V4": metrics(y_inc_val, scores4_inc, 0.88), "V5": metrics(y_inc_val, scores5_inc, threshold5)},
        "MITBIH_Validation": {"samples": len(y_mit_val), "N": int(np.sum(y_mit_val == 0)), "V": int(np.sum(y_mit_val == 1)),
                              "V4": metrics(y_mit_val, scores4_mit, 0.88), "V5": metrics(y_mit_val, scores5_mit, threshold5)},
    }
    inc_gain = comparison["INCART_Validation"]["V5"]["f1"] - comparison["INCART_Validation"]["V4"]["f1"]
    mit_gain = comparison["MITBIH_Validation"]["V5"]["f1"] - comparison["MITBIH_Validation"]["V4"]["f1"]
    recall_drop = comparison["INCART_Validation"]["V4"]["recall"] - comparison["INCART_Validation"]["V5"]["recall"]
    worth_testing = inc_gain >= 0.005 and mit_gain >= -0.01 and recall_drop <= 0.01
    best_row = max(selector.rows, key=lambda row: (row["f1"], row["precision"], -row["threshold"]))
    result = {"seed": SEED, "architecture": "multi-scale central QRS + full-window context",
              "parameters": v5.count_params(), "train_samples": len(y_train), "class_weight": class_weight,
              "selection_dataset": "INCART Validation only", "selected_threshold": threshold5,
              "best_epoch": best_row["epoch"], "epochs_run": len(selector.rows),
              "checkpoint_sha256": sha(BEST), "comparison": comparison,
              "clear_improvement_rule": "INCART F1 gain >=0.5pp, MIT-BIH F1 loss <=1pp, INCART recall loss <=1pp",
              "incart_f1_gain": inc_gain, "mitbih_f1_gain": mit_gain, "incart_recall_drop": recall_drop,
              "worth_independent_testing": worth_testing,
              "test_or_edb_used": False,
              "expected_tflm_ops": ["STRIDED_SLICE", "CONV_2D", "MAX_POOL_2D", "RESHAPE", "MEAN", "FULLY_CONNECTED", "CONCATENATION", "LOGISTIC"],
              "int8_exported": False}
    (RESULTS / "config.json").write_text(json.dumps({"architecture": model.to_json(), "seed": SEED,
        "optimizer": "Adam 0.001", "batch_size": 64, "max_epochs": 30, "patience": 5,
        "class_weight": class_weight, "selection": "INCART Validation max F1, tie precision then lower threshold"}, indent=2) + "\n")
    (RESULTS / "evaluation.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
