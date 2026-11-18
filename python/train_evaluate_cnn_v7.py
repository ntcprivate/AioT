from __future__ import annotations

import hashlib
import json
import math
import os
import random
from pathlib import Path

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
os.environ.setdefault("TF_ENABLE_ONEDNN_OPTS", "0")

import numpy as np
import tensorflow as tf
from sklearn.metrics import average_precision_score


ROOT = Path(__file__).resolve().parents[1]
MIT_PATH = ROOT / "data/processed/mitbih_nv_250hz.npz"
MIT_SPLIT_PATH = ROOT / "data/processed/mitbih_split_indices.npz"
INC_PATH = ROOT / "data/processed/incart_v4_250hz.npz"
V6_CONFIG_PATH = ROOT / "results/cnn_v6/config.json"
V6_EVAL_PATH = ROOT / "results/cnn_v6/evaluation.json"
MODEL_DIR = ROOT / "models/v7"
RESULT_DIR = ROOT / "results/cnn_v7"
BEST = MODEL_DIR / "ecg_cnn_v7_best.keras"
SEED = 42
BATCH_SIZE = 128
MAX_EPOCHS = 25
PATIENCE = 5
THRESHOLDS = np.round(np.arange(0.05, 0.951, 0.01), 2)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_v7() -> tf.keras.Model:
    inp = tf.keras.layers.Input((256, 1), name="ecg_256")

    center = tf.keras.layers.Cropping1D((64, 64), name="central_qrs_128")(inp)
    center = tf.keras.layers.Conv1D(8, 5, activation="relu", name="qrs_conv5_a")(center)
    center = tf.keras.layers.MaxPooling1D(2, name="qrs_pool_a")(center)
    center = tf.keras.layers.Conv1D(12, 5, activation="relu", name="qrs_conv5_b")(center)
    center = tf.keras.layers.MaxPooling1D(2, name="qrs_pool_b")(center)
    center_avg = tf.keras.layers.GlobalAveragePooling1D(name="qrs_gap")(center)
    center_max = tf.keras.layers.GlobalMaxPooling1D(name="qrs_gmp")(center)
    center = tf.keras.layers.Concatenate(name="qrs_aggregate")([center_avg, center_max])
    center = tf.keras.layers.Dense(8, activation="relu", name="qrs_dense")(center)

    context = tf.keras.layers.Conv1D(8, 15, activation="relu", name="context_conv15")(inp)
    context = tf.keras.layers.MaxPooling1D(4, name="context_pool")(context)
    context = tf.keras.layers.Conv1D(12, 9, activation="relu", name="context_conv9")(context)
    context_avg = tf.keras.layers.GlobalAveragePooling1D(name="context_gap")(context)
    context_max = tf.keras.layers.GlobalMaxPooling1D(name="context_gmp")(context)
    context = tf.keras.layers.Concatenate(name="context_aggregate")([context_avg, context_max])
    context = tf.keras.layers.Dense(8, activation="relu", name="context_dense")(context)

    merged = tf.keras.layers.Concatenate(name="multiscale_merge")([center, context])
    merged = tf.keras.layers.Dense(12, activation="relu", name="fusion_dense")(merged)
    out = tf.keras.layers.Dense(1, activation="sigmoid", name="pvc_probability")(merged)
    return tf.keras.Model(inp, out, name="ecg_nv_cnn_v7_gap_gmp")


class TrainSequence(tf.keras.utils.Sequence):
    def __init__(self, x: np.ndarray, y: np.ndarray, weights: dict[int, float]):
        super().__init__(); self.x, self.y, self.weights = x, y, weights
        self.epoch = 0; self.order = np.arange(len(y)); self.on_epoch_end()

    def __len__(self) -> int:
        return math.ceil(len(self.y) / BATCH_SIZE)

    def __getitem__(self, batch_index: int):
        indices = self.order[batch_index * BATCH_SIZE:(batch_index + 1) * BATCH_SIZE]
        result = self.x[indices].copy()
        rng = np.random.default_rng(SEED + self.epoch * 100_003 + batch_index)
        positions = np.arange(256, dtype=np.float32) / 250.0
        for index in range(len(result)):
            if rng.random() < 0.60:
                shift = int(rng.integers(-4, 5))
                if shift:
                    padded = np.pad(result[index], ((4, 4), (0, 0)), mode="reflect")
                    result[index] = padded[4 - shift:4 - shift + 256]
            if rng.random() < 0.50:
                result[index, :, 0] += rng.normal(0.0, rng.uniform(0.005, 0.03), 256).astype(np.float32)
            if rng.random() < 0.50:
                amplitude = float(rng.uniform(0.01, 0.08))
                frequency = float(rng.uniform(0.25, 0.70))
                phase = float(rng.uniform(0.0, 2.0 * np.pi))
                result[index, :, 0] += amplitude * np.sin(2.0 * np.pi * frequency * positions + phase)
            mean, std = float(result[index].mean()), float(result[index].std())
            result[index] = (result[index] - mean) / max(std, 1e-8)
        labels = self.y[indices]
        sample_weight = np.where(labels == 0, self.weights[0], self.weights[1]).astype(np.float32)
        return result.astype(np.float32), labels, sample_weight

    def on_epoch_end(self):
        self.epoch += 1
        self.order = np.random.default_rng(SEED + self.epoch).permutation(len(self.y))


class PRSelector(tf.keras.callbacks.Callback):
    def __init__(self, x: np.ndarray, y: np.ndarray):
        super().__init__(); self.x, self.y = x, y
        self.best, self.best_epoch, self.wait = -1.0, 0, 0
        self.history: list[dict[str, float | int]] = []

    def on_epoch_end(self, epoch, logs=None):
        scores = self.model.predict(self.x, batch_size=512, verbose=0).reshape(-1)
        pr_auc = float(average_precision_score(self.y, scores))
        self.history.append({"epoch": epoch + 1, "checkpoint_pr_auc": pr_auc,
                             "loss": float((logs or {}).get("loss", np.nan))})
        if pr_auc > self.best + 1e-12:
            self.best, self.best_epoch, self.wait = pr_auc, epoch + 1, 0
            self.model.save(BEST)
        else:
            self.wait += 1
        print(f" checkpoint_pr_auc={pr_auc:.6f}")
        if self.wait >= PATIENCE:
            self.model.stop_training = True


def metrics(y: np.ndarray, scores: np.ndarray, threshold: float) -> dict:
    prediction = scores >= threshold
    tp = int(np.sum((y == 1) & prediction)); tn = int(np.sum((y == 0) & ~prediction))
    fp = int(np.sum((y == 0) & prediction)); fn = int(np.sum((y == 1) & ~prediction))
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    normal = int(np.sum(y == 0))
    return {"accuracy": (tp + tn) / len(y), "precision": precision, "recall": recall, "f1": f1,
            "pr_auc": float(average_precision_score(y, scores)), "TP": tp, "FP": fp, "FN": fn, "TN": tn,
            "fp_per_1000_normal": fp * 1000.0 / normal if normal else 0.0,
            "confusion_rows_N_V": [[tn, fp], [fn, tp]], "threshold": float(threshold)}


def threshold_metrics(y: np.ndarray, scores: np.ndarray, threshold: float) -> dict:
    row = metrics(y, scores, threshold)
    return row


def select_threshold(y: np.ndarray, scores: np.ndarray) -> dict:
    return max((threshold_metrics(y, scores, float(threshold)) for threshold in THRESHOLDS),
               key=lambda row: (row["f1"], row["precision"], -row["threshold"]))


def main() -> None:
    if MODEL_DIR.exists() or RESULT_DIR.exists():
        raise RuntimeError("V7 artifacts already exist; refusing to overwrite or retrain")
    MODEL_DIR.mkdir(parents=True); RESULT_DIR.mkdir(parents=True)
    random.seed(SEED); np.random.seed(SEED); tf.keras.utils.set_random_seed(SEED)
    tf.config.threading.set_inter_op_parallelism_threads(1)
    tf.config.threading.set_intra_op_parallelism_threads(2)
    tf.config.experimental.enable_op_determinism()

    v6_config = json.loads(V6_CONFIG_PATH.read_text(encoding="utf-8"))
    groups = v6_config["development_partition"]
    inc_checkpoint_groups = set(groups["INCART_checkpoint_patients"])
    inc_threshold_groups = set(groups["INCART_threshold_patients"])
    mit_checkpoint_groups = set(groups["MITBIH_checkpoint_records"])
    mit_threshold_groups = set(groups["MITBIH_threshold_records"])

    mit = np.load(MIT_PATH); split = np.load(MIT_SPLIT_PATH); inc = np.load(INC_PATH)
    mit_train = split["train_indices"]; mit_dev = split["validation_indices"]
    inc_train = inc["split"].astype(str) == "train"; inc_dev = inc["split"].astype(str) == "validation"
    x_train = np.concatenate([mit["X"][mit_train], inc["X"][inc_train]])
    y_train = np.concatenate([mit["y"][mit_train], inc["y"][inc_train]]).astype(np.int32)
    counts = np.bincount(y_train, minlength=2)
    weights = {index: float(len(y_train) / (2 * counts[index])) for index in (0, 1)}

    inc_x, inc_y = inc["X"][inc_dev], inc["y"][inc_dev].astype(np.int32)
    inc_groups = inc["patient_ids"][inc_dev].astype(str)
    mit_x, mit_y = mit["X"][mit_dev], mit["y"][mit_dev].astype(np.int32)
    mit_groups = mit["record_ids"][mit_dev].astype(str)
    inc_cp = np.isin(inc_groups, list(inc_checkpoint_groups)); inc_th = np.isin(inc_groups, list(inc_threshold_groups))
    mit_cp = np.isin(mit_groups, list(mit_checkpoint_groups)); mit_th = np.isin(mit_groups, list(mit_threshold_groups))
    if np.any(inc_cp & inc_th) or np.any(mit_cp & mit_th) or not np.all(inc_cp | inc_th) or not np.all(mit_cp | mit_th):
        raise RuntimeError("Development group partition integrity failed")
    x_checkpoint = np.concatenate([inc_x[inc_cp], mit_x[mit_cp]])
    y_checkpoint = np.concatenate([inc_y[inc_cp], mit_y[mit_cp]])
    x_threshold = np.concatenate([inc_x[inc_th], mit_x[mit_th]])
    y_threshold = np.concatenate([inc_y[inc_th], mit_y[mit_th]])

    model = build_v7()
    if model.count_params() >= 5_000:
        raise RuntimeError(f"V7 parameter budget exceeded: {model.count_params()}")
    model.compile(optimizer=tf.keras.optimizers.Adam(0.001), loss="binary_crossentropy")
    selector = PRSelector(x_checkpoint, y_checkpoint)
    model.fit(TrainSequence(x_train, y_train, weights), epochs=MAX_EPOCHS, verbose=2,
              callbacks=[selector, tf.keras.callbacks.TerminateOnNaN()])
    model = tf.keras.models.load_model(BEST, compile=False)
    threshold_scores = model.predict(x_threshold, batch_size=512, verbose=0).reshape(-1)
    selected = select_threshold(y_threshold, threshold_scores)
    threshold = selected["threshold"]

    subsets = {
        "checkpoint_combined": (x_checkpoint, y_checkpoint),
        "threshold_combined": (x_threshold, y_threshold),
        "checkpoint_INCART": (inc_x[inc_cp], inc_y[inc_cp]),
        "threshold_INCART": (inc_x[inc_th], inc_y[inc_th]),
        "checkpoint_MITBIH": (mit_x[mit_cp], mit_y[mit_cp]),
        "threshold_MITBIH": (mit_x[mit_th], mit_y[mit_th]),
    }
    evaluation = {}
    for name, (x, y) in subsets.items():
        scores = model.predict(x, batch_size=512, verbose=0).reshape(-1)
        evaluation[name] = {"samples": int(len(y)), "N": int(np.sum(y == 0)), "V": int(np.sum(y == 1)),
                            "V7": metrics(y, scores, threshold)}

    prior = json.loads(V6_EVAL_PATH.read_text(encoding="utf-8"))["comparison"]
    comparable = {}
    for name in subsets:
        comparable[name] = {model_name: prior[name][model_name] for model_name in ("V4", "V5", "V6")}
        comparable[name]["V7"] = evaluation[name]["V7"]

    config = {
        "seed": SEED, "architecture": "dual branch central-QRS/full-window; GAP+GMP; no Flatten",
        "parameters": int(model.count_params()), "train_samples": int(len(y_train)), "class_weight": weights,
        "batch_size": BATCH_SIZE, "max_epochs": MAX_EPOCHS, "patience": PATIENCE,
        "augmentation": {"center_shift_samples": [-4, 4], "shift_probability": 0.60,
                         "gaussian_noise_sigma": [0.005, 0.03], "noise_probability": 0.50,
                         "baseline_wander_amplitude": [0.01, 0.08], "baseline_wander_hz": [0.25, 0.70],
                         "baseline_probability": 0.50, "polarity_inversion": False,
                         "zscore_after_augmentation": True},
        "development_partition": groups,
        "checkpoint_selection": "maximum PR-AUC on checkpoint-only groups",
        "threshold_selection": "maximum PVC F1 on disjoint threshold-only groups; tie precision then lower threshold",
        "test_samples_selected_or_evaluated": False,
    }
    result = {
        "parameters": int(model.count_params()), "threshold": threshold, "best_epoch": selector.best_epoch,
        "epochs_run": len(selector.history), "checkpoint_pr_auc_best": selector.best,
        "checkpoint_sha256": sha256(BEST), "threshold_selection": selected,
        "evaluation": evaluation, "comparison_same_development_partitions": comparable,
        "checkpoint_history": selector.history, "checkpoint_and_threshold_locked": True,
        "test_used": False,
    }
    (RESULT_DIR / "config.json").write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    (RESULT_DIR / "evaluation.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    def pct(value: float) -> str:
        return f"{100 * value:.4f}%"
    lines = ["# CNN V7 FP32", "", f"Parameters: {model.count_params():,}. Threshold: {threshold:.2f}.",
             f"Best epoch: {selector.best_epoch}; checkpoint PR-AUC: {selector.best:.6f}.", ""]
    for subset_name in ("checkpoint_INCART", "threshold_INCART", "checkpoint_MITBIH", "threshold_MITBIH"):
        lines += [f"## {subset_name}", "", "| Model | Precision | Recall | F1 | FP | FN |",
                  "|---|---:|---:|---:|---:|---:|"]
        for model_name in ("V4", "V5", "V6", "V7"):
            row = comparable[subset_name][model_name]
            lines.append(f"| {model_name} | {pct(row['precision'])} | {pct(row['recall'])} | {pct(row['f1'])} | {row['FP']} | {row['FN']} |")
        lines.append("")
    lines += ["No Test split or third-party dataset was used. Checkpoint and threshold are locked."]
    (RESULT_DIR / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (RESULT_DIR / "locked.json").write_text(json.dumps({"locked": True, "threshold": threshold,
        "checkpoint_sha256": sha256(BEST), "test_used": False}, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"parameters": model.count_params(), "threshold": threshold, "best_epoch": selector.best_epoch,
                      "epochs_run": len(selector.history), "evaluation": evaluation}, indent=2))


if __name__ == "__main__":
    main()
