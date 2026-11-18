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
CONFIG_PATH = ROOT / "results/cnn_v8/config.json"
RESULT_DIR = ROOT / "results/cnn_v8"
MODEL_DIR = ROOT / "models/v8"
BEST = MODEL_DIR / "ecg_cnn_v8_best.keras"
MIT_PATH = ROOT / "data/processed/mitbih_nv_250hz.npz"
MIT_SPLIT_PATH = ROOT / "data/processed/mitbih_split_indices.npz"
INC_PATH = ROOT / "data/processed/incart_v4_250hz.npz"
V6_CONFIG = ROOT / "results/cnn_v6/config.json"
V7_EVAL = ROOT / "results/cnn_v7/evaluation.json"
V7_TEST_LOCK = ROOT / "results/cnn_v7/final_test/evaluation.lock.json"
SEED, BATCH_SIZE, MAX_EPOCHS, PATIENCE = 42, 128, 25, 5
THRESHOLDS = np.round(np.arange(0.01, 0.9901, 0.005), 3)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_v8() -> tf.keras.Model:
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
    return tf.keras.Model(inp, tf.keras.layers.Dense(1, activation="sigmoid", name="pvc_probability")(merged),
                          name="ecg_nv_cnn_v8")


def metrics(y: np.ndarray, scores: np.ndarray, threshold: float) -> dict:
    pred = scores >= threshold
    tp = int(np.sum((y == 1) & pred)); tn = int(np.sum((y == 0) & ~pred))
    fp = int(np.sum((y == 0) & pred)); fn = int(np.sum((y == 1) & ~pred))
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    normal = int(np.sum(y == 0))
    return {"accuracy": (tp + tn) / len(y), "precision": precision, "recall": recall, "f1": f1,
            "pr_auc": float(average_precision_score(y, scores)), "TP": tp, "FP": fp, "FN": fn, "TN": tn,
            "fp_per_1000_normal": fp * 1000.0 / normal if normal else 0.0, "threshold": float(threshold)}


class TrainSequence(tf.keras.utils.Sequence):
    def __init__(self, x, y, sample_weights):
        super().__init__(); self.x, self.y, self.sample_weights = x, y, sample_weights
        self.epoch = 0; self.order = np.arange(len(y)); self.on_epoch_end()

    def __len__(self):
        return math.ceil(len(self.y) / BATCH_SIZE)

    def __getitem__(self, batch_index):
        indices = self.order[batch_index * BATCH_SIZE:(batch_index + 1) * BATCH_SIZE]
        result = self.x[indices].copy(); rng = np.random.default_rng(SEED + self.epoch * 100_003 + batch_index)
        positions = np.arange(256, dtype=np.float32) / 250.0
        for index in range(len(result)):
            if rng.random() < 0.50:
                shift = int(rng.integers(-4, 5))
                if shift:
                    padded = np.pad(result[index], ((4, 4), (0, 0)), mode="reflect")
                    result[index] = padded[4 - shift:4 - shift + 256]
            if rng.random() < 0.40:
                result[index, :, 0] += rng.normal(0, rng.uniform(0.005, 0.025), 256).astype(np.float32)
            if rng.random() < 0.40:
                amp, freq, phase = rng.uniform(0.01, 0.06), rng.uniform(0.25, 0.70), rng.uniform(0, 2*np.pi)
                result[index, :, 0] += amp * np.sin(2*np.pi*freq*positions + phase)
            mean, std = float(result[index].mean()), float(result[index].std())
            result[index] = (result[index] - mean) / max(std, 1e-8)
        return result.astype(np.float32), self.y[indices], self.sample_weights[indices]

    def on_epoch_end(self):
        self.epoch += 1; self.order = np.random.default_rng(SEED + self.epoch).permutation(len(self.y))


class Selector(tf.keras.callbacks.Callback):
    def __init__(self, x, y):
        super().__init__(); self.x, self.y = x, y; self.best = -1.0; self.best_epoch = 0; self.wait = 0; self.rows = []

    def on_epoch_end(self, epoch, logs=None):
        scores = self.model.predict(self.x, batch_size=512, verbose=0).reshape(-1)
        ap = float(average_precision_score(self.y, scores))
        self.rows.append({"epoch": epoch + 1, "checkpoint_pr_auc": ap, "loss": float((logs or {}).get("loss", np.nan))})
        if ap > self.best + 1e-12:
            self.best, self.best_epoch, self.wait = ap, epoch + 1, 0; self.model.save(BEST)
        else: self.wait += 1
        print(f" checkpoint_pr_auc={ap:.6f}")
        if self.wait >= PATIENCE: self.model.stop_training = True


def group_weights(y: np.ndarray, groups: np.ndarray) -> np.ndarray:
    result = np.ones(len(y), dtype=np.float64)
    for label in (0, 1):
        mask = y == label; unique, counts = np.unique(groups[mask], return_counts=True)
        mapping = {group: 1.0 / math.sqrt(int(count)) for group, count in zip(unique, counts)}
        raw = np.asarray([mapping[group] for group in groups[mask]], dtype=np.float64)
        result[mask] = raw / raw.mean()
    return result


def choose_threshold(y_combined, scores_combined, y_inc, scores_inc, y_mit, scores_mit):
    rows = []
    for threshold in THRESHOLDS:
        combined = metrics(y_combined, scores_combined, float(threshold))
        inc = metrics(y_inc, scores_inc, float(threshold)); mit = metrics(y_mit, scores_mit, float(threshold))
        combined["INCART_recall"] = inc["recall"]; combined["MITBIH_recall"] = mit["recall"]
        combined["eligible"] = combined["recall"] >= 0.95 and inc["recall"] >= 0.90 and mit["recall"] >= 0.90
        rows.append(combined)
    eligible = [row for row in rows if row["eligible"]]
    pool = eligible or rows
    selected = max(pool, key=lambda row: (row["f1"], row["precision"], row["threshold"]))
    selected["fallback_used"] = not bool(eligible)
    return selected


def main():
    if MODEL_DIR.exists() or (RESULT_DIR / "evaluation.json").exists():
        raise RuntimeError("V8 training artifacts already exist; refusing to retrain")
    design_hash = sha256(CONFIG_PATH)
    v7_lock = json.loads(V7_TEST_LOCK.read_text(encoding="utf-8"))
    if v7_lock["v8_design_sha256_before_v7_test"] != design_hash:
        raise RuntimeError("V8 design changed after V7 Test")
    MODEL_DIR.mkdir(parents=True)
    random.seed(SEED); np.random.seed(SEED); tf.keras.utils.set_random_seed(SEED)
    tf.config.threading.set_inter_op_parallelism_threads(1); tf.config.threading.set_intra_op_parallelism_threads(2)
    tf.config.experimental.enable_op_determinism()

    mit = np.load(MIT_PATH); split = np.load(MIT_SPLIT_PATH); inc = np.load(INC_PATH)
    mit_train = split["train_indices"]; mit_dev = split["validation_indices"]
    inc_train = inc["split"].astype(str) == "train"; inc_dev = inc["split"].astype(str) == "validation"
    x_train = np.concatenate([mit["X"][mit_train], inc["X"][inc_train]])
    y_train = np.concatenate([mit["y"][mit_train], inc["y"][inc_train]]).astype(np.int32)
    groups_train = np.concatenate([np.char.add("MIT:", mit["record_ids"][mit_train].astype(str)),
                                   np.char.add("INC:", inc["patient_ids"][inc_train].astype(str))])
    class_counts = np.bincount(y_train, minlength=2)
    class_weight = np.asarray([len(y_train)/(2*class_counts[label]) for label in y_train], dtype=np.float64)
    balance_weight = group_weights(y_train, groups_train)
    miner = tf.keras.models.load_model(ROOT / "models/v6/ecg_cnn_v6_best.keras", compile=False)
    miner_scores = miner.predict(x_train, batch_size=512, verbose=0).reshape(-1)
    hard_negative = (y_train == 0) & (miner_scores >= 0.50)
    sample_weight = class_weight * balance_weight * np.where(hard_negative, 1.5, 1.0)
    sample_weight = np.minimum(sample_weight, 8.0).astype(np.float32)
    del miner, miner_scores

    partition = json.loads(V6_CONFIG.read_text(encoding="utf-8"))["development_partition"]
    inc_x, inc_y, inc_group = inc["X"][inc_dev], inc["y"][inc_dev].astype(np.int32), inc["patient_ids"][inc_dev].astype(str)
    mit_x, mit_y, mit_group = mit["X"][mit_dev], mit["y"][mit_dev].astype(np.int32), mit["record_ids"][mit_dev].astype(str)
    inc_cp = np.isin(inc_group, partition["INCART_checkpoint_patients"]); inc_th = np.isin(inc_group, partition["INCART_threshold_patients"])
    mit_cp = np.isin(mit_group, partition["MITBIH_checkpoint_records"]); mit_th = np.isin(mit_group, partition["MITBIH_threshold_records"])
    x_cp = np.concatenate([inc_x[inc_cp], mit_x[mit_cp]]); y_cp = np.concatenate([inc_y[inc_cp], mit_y[mit_cp]])
    x_th = np.concatenate([inc_x[inc_th], mit_x[mit_th]]); y_th = np.concatenate([inc_y[inc_th], mit_y[mit_th]])

    model = build_v8()
    if model.count_params() != 1969: raise RuntimeError(f"V8 parameter contract failed: {model.count_params()}")
    model.compile(optimizer=tf.keras.optimizers.Adam(0.001), loss="binary_crossentropy")
    selector = Selector(x_cp, y_cp)
    model.fit(TrainSequence(x_train, y_train, sample_weight), epochs=MAX_EPOCHS, verbose=2,
              callbacks=[selector, tf.keras.callbacks.TerminateOnNaN()])
    model = tf.keras.models.load_model(BEST, compile=False)
    scores_inc_th = model.predict(inc_x[inc_th], batch_size=512, verbose=0).reshape(-1)
    scores_mit_th = model.predict(mit_x[mit_th], batch_size=512, verbose=0).reshape(-1)
    scores_th = np.concatenate([scores_inc_th, scores_mit_th])
    selected = choose_threshold(y_th, scores_th, inc_y[inc_th], scores_inc_th, mit_y[mit_th], scores_mit_th)
    threshold = selected["threshold"]

    subsets = {"checkpoint_INCART": (inc_x[inc_cp], inc_y[inc_cp]), "threshold_INCART": (inc_x[inc_th], inc_y[inc_th]),
               "checkpoint_MITBIH": (mit_x[mit_cp], mit_y[mit_cp]), "threshold_MITBIH": (mit_x[mit_th], mit_y[mit_th]),
               "checkpoint_combined": (x_cp, y_cp), "threshold_combined": (x_th, y_th)}
    scores8 = {name: model.predict(x, batch_size=512, verbose=0).reshape(-1) for name, (x, _) in subsets.items()}
    prior = json.loads(V7_EVAL.read_text(encoding="utf-8"))["comparison_same_development_partitions"]
    model_paths = {"V4": ROOT/"models/v4/ecg_cnn_v4_best.keras", "V5": ROOT/"models/v5/ecg_cnn_v5_best.keras",
                   "V6": ROOT/"models/v6/ecg_cnn_v6_best.keras", "V7": ROOT/"models/v7/ecg_cnn_v7_best.keras"}
    old_models = {name: tf.keras.models.load_model(path, compile=False) for name, path in model_paths.items()}
    comparison = {}
    for subset_name, (x, y) in subsets.items():
        comparison[subset_name] = {}
        for name in ("V4", "V5", "V6", "V7"):
            row = dict(prior[subset_name][name])
            old_scores = old_models[name].predict(x, batch_size=512, verbose=0).reshape(-1)
            row["pr_auc"] = float(average_precision_score(y, old_scores))
            row["fp_per_1000_normal"] = row["FP"] * 1000.0 / int(np.sum(y == 0))
            row["accuracy"] = (row["TP"] + row["TN"]) / len(y)
            comparison[subset_name][name] = row
        comparison[subset_name]["V8"] = metrics(y, scores8[subset_name], threshold)

    result = {"architecture": "V6 dual branch GAP", "parameters": model.count_params(), "threshold": threshold,
              "best_epoch": selector.best_epoch, "epochs_run": len(selector.rows), "checkpoint_pr_auc_best": selector.best,
              "checkpoint_sha256": sha256(BEST), "design_sha256": design_hash,
              "hard_negative_train_N": int(np.sum(hard_negative)), "threshold_selection": selected,
              "comparison_same_development_partitions": comparison, "checkpoint_history": selector.rows,
              "test_used": False, "checkpoint_and_threshold_locked": True}
    (RESULT_DIR / "evaluation.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    lines = ["# CNN V8 FP32", "", f"Parameters: {model.count_params():,}; threshold: {threshold:.3f}; hard-negative Train N: {np.sum(hard_negative):,}.", ""]
    for subset in ("checkpoint_INCART", "threshold_INCART", "checkpoint_MITBIH", "threshold_MITBIH"):
        lines += [f"## {subset}", "", "| Model | Precision | Recall | F1 | FP | FN |", "|---|---:|---:|---:|---:|---:|"]
        for name in ("V4","V5","V6","V7","V8"):
            row=comparison[subset][name]; lines.append(f"| {name} | {100*row['precision']:.4f}% | {100*row['recall']:.4f}% | {100*row['f1']:.4f}% | {row['FP']} | {row['FN']} |")
        lines.append("")
    lines += ["No Test dataset was used. Checkpoint and threshold are locked."]
    (RESULT_DIR / "report.md").write_text("\n".join(lines)+"\n", encoding="utf-8")
    (RESULT_DIR / "locked.json").write_text(json.dumps({"locked":True,"threshold":threshold,"checkpoint_sha256":sha256(BEST),"test_used":False},indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"parameters":model.count_params(),"threshold":threshold,"best_epoch":selector.best_epoch,
                      "hard_negative_train_N":int(np.sum(hard_negative)),"comparison":comparison},indent=2))


if __name__ == "__main__": main()
