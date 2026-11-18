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
V4_PATH = ROOT / "models/v4/ecg_cnn_v4_best.keras"
V5_PATH = ROOT / "models/v5/ecg_cnn_v5_best.keras"
MODEL_DIR = ROOT / "models/v6"
RESULT_DIR = ROOT / "results/cnn_v6"
SEED = 42
THRESHOLDS = np.round(np.arange(0.05, 0.951, 0.01), 2)
BATCH_SIZE = 128
MAX_EPOCHS = 20
PATIENCE = 5


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_flatten_reference() -> tf.keras.Model:
    inp = tf.keras.layers.Input((256, 1), name="ecg_256")
    center = tf.keras.layers.Cropping1D((64, 64))(inp)
    center = tf.keras.layers.Conv1D(8, 5, activation="relu")(center)
    center = tf.keras.layers.MaxPooling1D(2)(center)
    center = tf.keras.layers.Conv1D(12, 5, activation="relu")(center)
    center = tf.keras.layers.MaxPooling1D(2)(center)
    center = tf.keras.layers.Flatten()(center)
    center = tf.keras.layers.Dense(8, activation="relu")(center)
    context = tf.keras.layers.Conv1D(8, 15, activation="relu")(inp)
    context = tf.keras.layers.MaxPooling1D(4)(context)
    context = tf.keras.layers.Conv1D(12, 9, activation="relu")(context)
    context = tf.keras.layers.GlobalAveragePooling1D()(context)
    context = tf.keras.layers.Dense(8, activation="relu")(context)
    merged = tf.keras.layers.Concatenate()([center, context])
    merged = tf.keras.layers.Dense(8, activation="relu")(merged)
    return tf.keras.Model(inp, tf.keras.layers.Dense(1, activation="sigmoid")(merged), name="v5_flatten_ablation")


def build_pooling_v6() -> tf.keras.Model:
    inp = tf.keras.layers.Input((256, 1), name="ecg_256")
    center = tf.keras.layers.Cropping1D((64, 64), name="central_qrs_128")(inp)
    center = tf.keras.layers.Conv1D(8, 5, activation="relu", name="qrs_conv5_a")(center)
    center = tf.keras.layers.MaxPooling1D(2, name="qrs_pool_a")(center)
    center = tf.keras.layers.Conv1D(12, 5, activation="relu", name="qrs_conv5_b")(center)
    center = tf.keras.layers.MaxPooling1D(2, name="qrs_pool_b")(center)
    center = tf.keras.layers.GlobalAveragePooling1D(name="qrs_gap")(center)
    center = tf.keras.layers.Dense(8, activation="relu", name="qrs_dense")(center)

    context = tf.keras.layers.Conv1D(8, 15, activation="relu", name="context_conv15")(inp)
    context = tf.keras.layers.MaxPooling1D(4, name="context_pool")(context)
    context = tf.keras.layers.Conv1D(12, 9, activation="relu", name="context_conv9")(context)
    context = tf.keras.layers.GlobalAveragePooling1D(name="context_gap")(context)
    context = tf.keras.layers.Dense(8, activation="relu", name="context_dense")(context)

    merged = tf.keras.layers.Concatenate(name="multiscale_merge")([center, context])
    merged = tf.keras.layers.Dense(12, activation="relu", name="fusion_dense")(merged)
    out = tf.keras.layers.Dense(1, activation="sigmoid", name="pvc_probability")(merged)
    return tf.keras.Model(inp, out, name="ecg_nv_cnn_v6_pooling")


class TrainSequence(tf.keras.utils.Sequence):
    def __init__(self, x: np.ndarray, y: np.ndarray, weights: dict[int, float], augment: bool):
        super().__init__()
        self.x, self.y, self.weights, self.augment = x, y, weights, augment
        self.epoch = 0
        self.order = np.arange(len(y))
        self.on_epoch_end()

    def __len__(self) -> int:
        return math.ceil(len(self.y) / BATCH_SIZE)

    @staticmethod
    def augment_batch(batch: np.ndarray, rng: np.random.Generator) -> np.ndarray:
        result = batch.copy()
        positions = np.arange(256, dtype=np.float32)
        qrs_mask = np.exp(-0.5 * ((positions - 128.0) / 32.0) ** 2)[:, None]
        for i in range(len(result)):
            if rng.random() < 0.70:
                shift = int(rng.integers(-6, 7))
                if shift:
                    padded = np.pad(result[i], ((6, 6), (0, 0)), mode="reflect")
                    start = 6 - shift
                    result[i] = padded[start:start + 256]
            if rng.random() < 0.70:
                relative_gain = float(rng.uniform(0.85, 1.15))
                result[i] *= 1.0 + (relative_gain - 1.0) * qrs_mask
            if rng.random() < 0.12:
                result[i] *= -1.0
            mean = float(result[i].mean())
            std = float(result[i].std())
            result[i] = (result[i] - mean) / max(std, 1e-8)
        return result.astype(np.float32)

    def __getitem__(self, batch_index: int):
        indices = self.order[batch_index * BATCH_SIZE:(batch_index + 1) * BATCH_SIZE]
        x = self.x[indices]
        if self.augment:
            rng = np.random.default_rng(SEED + self.epoch * 100_003 + batch_index)
            x = self.augment_batch(x, rng)
        y = self.y[indices]
        sample_weight = np.where(y == 0, self.weights[0], self.weights[1]).astype(np.float32)
        return x, y, sample_weight

    def on_epoch_end(self):
        self.epoch += 1
        self.order = np.random.default_rng(SEED + self.epoch).permutation(len(self.y))


class APSelector(tf.keras.callbacks.Callback):
    def __init__(self, x: np.ndarray, y: np.ndarray, path: Path):
        super().__init__()
        self.x, self.y, self.path = x, y, path
        self.best_ap, self.best_epoch, self.wait = -1.0, 0, 0
        self.rows: list[dict[str, float | int]] = []

    def on_epoch_end(self, epoch, logs=None):
        scores = self.model.predict(self.x, batch_size=512, verbose=0).reshape(-1)
        ap = float(average_precision_score(self.y, scores))
        row = {"epoch": epoch + 1, "checkpoint_pr_auc": ap, "loss": float((logs or {}).get("loss", np.nan))}
        self.rows.append(row)
        if ap > self.best_ap + 1e-12:
            self.best_ap, self.best_epoch, self.wait = ap, epoch + 1, 0
            self.model.save(self.path)
        else:
            self.wait += 1
        print(f" checkpoint_pr_auc={ap:.6f}")
        if self.wait >= PATIENCE:
            self.model.stop_training = True


def metrics(y: np.ndarray, scores: np.ndarray, threshold: float) -> dict[str, float | int | list]:
    pred = scores >= threshold
    tp = int(np.sum((y == 1) & pred)); tn = int(np.sum((y == 0) & ~pred))
    fp = int(np.sum((y == 0) & pred)); fn = int(np.sum((y == 1) & ~pred))
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"threshold": float(threshold), "precision": precision, "recall": recall, "f1": f1,
            "TP": tp, "TN": tn, "FP": fp, "FN": fn, "confusion_rows_N_V": [[tn, fp], [fn, tp]]}


def select_threshold(y: np.ndarray, scores: np.ndarray) -> dict[str, float | int | list]:
    return max((metrics(y, scores, float(t)) for t in THRESHOLDS),
               key=lambda row: (row["f1"], row["precision"], -row["threshold"]))


def group_partition(groups: np.ndarray, checkpoint_fraction: float = 0.60) -> tuple[set[str], set[str]]:
    unique = sorted(set(map(str, groups)), key=lambda group: hashlib.sha256(f"{SEED}:{group}".encode()).hexdigest())
    cut = max(1, min(len(unique) - 1, int(math.ceil(len(unique) * checkpoint_fraction))))
    return set(unique[:cut]), set(unique[cut:])


def train_candidate(name: str, builder, augment: bool, x_train, y_train, weights, x_checkpoint, y_checkpoint):
    tf.keras.backend.clear_session()
    random.seed(SEED); np.random.seed(SEED); tf.keras.utils.set_random_seed(SEED)
    model = builder()
    if model.count_params() >= 10_000:
        raise RuntimeError(f"{name} exceeds parameter budget: {model.count_params()}")
    model.compile(optimizer=tf.keras.optimizers.Adam(0.001), loss="binary_crossentropy")
    checkpoint = MODEL_DIR / f"ablation_{name}.keras"
    selector = APSelector(x_checkpoint, y_checkpoint, checkpoint)
    sequence = TrainSequence(x_train, y_train, weights, augment)
    model.fit(sequence, epochs=MAX_EPOCHS, verbose=2,
              callbacks=[selector, tf.keras.callbacks.TerminateOnNaN()])
    return {"name": name, "augment": augment, "parameters": model.count_params(),
            "checkpoint": str(checkpoint.relative_to(ROOT)), "best_epoch": selector.best_epoch,
            "epochs_run": len(selector.rows), "checkpoint_pr_auc": selector.best_ap,
            "history": selector.rows}


def main() -> None:
    if RESULT_DIR.exists() or MODEL_DIR.exists():
        raise RuntimeError("V6 output already exists; refusing to overwrite or retrain")
    MODEL_DIR.mkdir(parents=True); RESULT_DIR.mkdir(parents=True)
    tf.config.threading.set_inter_op_parallelism_threads(1)
    tf.config.threading.set_intra_op_parallelism_threads(2)
    tf.config.experimental.enable_op_determinism()

    mit = np.load(MIT_PATH); mit_split = np.load(MIT_SPLIT_PATH); inc = np.load(INC_PATH)
    mit_train_idx = mit_split["train_indices"]; mit_dev_idx = mit_split["validation_indices"]
    inc_train_mask = inc["split"].astype(str) == "train"
    inc_dev_mask = inc["split"].astype(str) == "validation"
    if np.any(inc["split"][inc_dev_mask].astype(str) == "test"):
        raise RuntimeError("Test leakage guard failed")

    x_train = np.concatenate([mit["X"][mit_train_idx], inc["X"][inc_train_mask]])
    y_train = np.concatenate([mit["y"][mit_train_idx], inc["y"][inc_train_mask]]).astype(np.int32)
    counts = np.bincount(y_train, minlength=2)
    weights = {i: float(len(y_train) / (2 * counts[i])) for i in (0, 1)}

    inc_dev_x, inc_dev_y = inc["X"][inc_dev_mask], inc["y"][inc_dev_mask].astype(np.int32)
    inc_dev_groups = inc["patient_ids"][inc_dev_mask].astype(str)
    mit_dev_x, mit_dev_y = mit["X"][mit_dev_idx], mit["y"][mit_dev_idx].astype(np.int32)
    mit_dev_groups = mit["record_ids"][mit_dev_idx].astype(str)
    inc_checkpoint_groups, inc_threshold_groups = group_partition(inc_dev_groups)
    mit_checkpoint_groups, mit_threshold_groups = group_partition(mit_dev_groups)
    inc_checkpoint = np.isin(inc_dev_groups, list(inc_checkpoint_groups)); inc_threshold = ~inc_checkpoint
    mit_checkpoint = np.isin(mit_dev_groups, list(mit_checkpoint_groups)); mit_threshold = ~mit_checkpoint
    x_checkpoint = np.concatenate([inc_dev_x[inc_checkpoint], mit_dev_x[mit_checkpoint]])
    y_checkpoint = np.concatenate([inc_dev_y[inc_checkpoint], mit_dev_y[mit_checkpoint]])
    x_threshold = np.concatenate([inc_dev_x[inc_threshold], mit_dev_x[mit_threshold]])
    y_threshold = np.concatenate([inc_dev_y[inc_threshold], mit_dev_y[mit_threshold]])
    for label, values in (("checkpoint", y_checkpoint), ("threshold", y_threshold)):
        if set(np.unique(values)) != {0, 1}:
            raise RuntimeError(f"Both classes required in {label} development subset")

    candidates = [
        train_candidate("flatten_no_aug", build_flatten_reference, False, x_train, y_train, weights, x_checkpoint, y_checkpoint),
        train_candidate("pool_no_aug", build_pooling_v6, False, x_train, y_train, weights, x_checkpoint, y_checkpoint),
        train_candidate("pool_aug", build_pooling_v6, True, x_train, y_train, weights, x_checkpoint, y_checkpoint),
    ]
    # Flatten is an ablation reference only. Final V6 is selected between the two pooling variants on checkpoint PR-AUC.
    selected_candidate = max(candidates[1:], key=lambda row: row["checkpoint_pr_auc"])
    selected_path = ROOT / selected_candidate["checkpoint"]
    final_path = MODEL_DIR / "ecg_cnn_v6_best.keras"
    final_path.write_bytes(selected_path.read_bytes())
    v6 = tf.keras.models.load_model(final_path, compile=False)
    threshold_scores = v6.predict(x_threshold, batch_size=512, verbose=0).reshape(-1)
    selected_threshold = select_threshold(y_threshold, threshold_scores)

    v4 = tf.keras.models.load_model(V4_PATH, compile=False)
    v5 = tf.keras.models.load_model(V5_PATH, compile=False)
    models = {"V4": (v4, 0.88), "V5": (v5, 0.33), "V6": (v6, selected_threshold["threshold"])}
    subsets = {
        "checkpoint_combined": (x_checkpoint, y_checkpoint),
        "threshold_combined": (x_threshold, y_threshold),
        "checkpoint_INCART": (inc_dev_x[inc_checkpoint], inc_dev_y[inc_checkpoint]),
        "threshold_INCART": (inc_dev_x[inc_threshold], inc_dev_y[inc_threshold]),
        "checkpoint_MITBIH": (mit_dev_x[mit_checkpoint], mit_dev_y[mit_checkpoint]),
        "threshold_MITBIH": (mit_dev_x[mit_threshold], mit_dev_y[mit_threshold]),
    }
    comparison: dict[str, object] = {}
    for subset_name, (x, y) in subsets.items():
        comparison[subset_name] = {"samples": int(len(y)), "N": int(np.sum(y == 0)), "V": int(np.sum(y == 1))}
        for model_name, (model, threshold) in models.items():
            scores = model.predict(x, batch_size=512, verbose=0).reshape(-1)
            comparison[subset_name][model_name] = metrics(y, scores, threshold)

    config = {
        "seed": SEED, "train_samples": int(len(y_train)), "class_weight": weights,
        "development_partition": {
            "method": "fixed SHA256(seed:group), 60% checkpoint / 40% threshold; no waveform or output selection",
            "INCART_checkpoint_patients": sorted(inc_checkpoint_groups, key=int),
            "INCART_threshold_patients": sorted(inc_threshold_groups, key=int),
            "MITBIH_checkpoint_records": sorted(mit_checkpoint_groups),
            "MITBIH_threshold_records": sorted(mit_threshold_groups),
        },
        "augmentation": {"shift_samples": [-6, 6], "shift_probability": 0.70,
                         "central_relative_gain": [0.85, 1.15], "gain_probability": 0.70,
                         "polarity_inversion_probability": 0.12, "renormalize_after": True},
        "checkpoint_selection": "maximum PR-AUC on checkpoint-only groups",
        "threshold_selection": "maximum PVC F1 on disjoint threshold-only groups; tie precision then lower threshold",
        "test_samples_selected_for_training_selection_or_evaluation": False,
    }
    result = {
        "architecture": "central QRS + full-window context; GlobalAveragePooling in both branches; no Flatten",
        "parameters": int(v6.count_params()), "selected_variant": selected_candidate["name"],
        "selected_threshold": selected_threshold["threshold"], "threshold_selection_metrics": selected_threshold,
        "checkpoint_sha256": sha256(final_path), "candidates": candidates, "comparison": comparison,
        "independent_test_claim": False,
        "recommendation_rule": "development evidence only; independent new patient-level dataset required",
    }
    (RESULT_DIR / "config.json").write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    (RESULT_DIR / "evaluation.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"selected_variant": result["selected_variant"], "parameters": result["parameters"],
                      "threshold": result["selected_threshold"], "comparison": comparison}, indent=2))


if __name__ == "__main__":
    main()
