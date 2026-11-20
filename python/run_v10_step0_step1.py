from __future__ import annotations

import hashlib
import json
import math
import os
import random
import time
from pathlib import Path

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
os.environ.setdefault("TF_ENABLE_ONEDNN_OPTS", "0")

import numpy as np
import tensorflow as tf
from sklearn.metrics import average_precision_score, precision_recall_curve

ROOT = Path(__file__).resolve().parents[1]
MIT_PATH = ROOT / "data/processed/mitbih_nv_250hz.npz"
MIT_SPLIT_PATH = ROOT / "data/processed/mitbih_split_indices.npz"
INC_PATH = ROOT / "data/processed/incart_v4_250hz.npz"
V4_MODEL_PATH = ROOT / "models/v4/ecg_cnn_v4_best.keras"
V6_MODEL_PATH = ROOT / "models/v6/ecg_cnn_v6_best.keras"
V6_CONFIG_PATH = ROOT / "results/cnn_v6/config.json"

OUT_DIR = ROOT / "results/v10_research"
STEP0_DIR = OUT_DIR / "step0_dev_analysis"
STEP1_DIR = OUT_DIR / "step1_5fold_cv"
STEP1_MODELS_DIR = STEP1_DIR / "checkpoints"

SEED = 42
THRESHOLDS = np.round(np.arange(0.05, 0.951, 0.01), 2)
BATCH_SIZE = 128
MAX_EPOCHS = 20
PATIENCE = 5


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_v4_baseline(name: str = "ecg_nv_cnn_v4_baseline") -> tf.keras.Model:
    model = tf.keras.Sequential([
        tf.keras.layers.Input((256, 1), name="ecg_256"),
        tf.keras.layers.Conv1D(8, 5, activation="relu"),
        tf.keras.layers.MaxPooling1D(2),
        tf.keras.layers.Conv1D(16, 5, activation="relu"),
        tf.keras.layers.MaxPooling1D(2),
        tf.keras.layers.GlobalAveragePooling1D(),
        tf.keras.layers.Dense(8, activation="relu"),
        tf.keras.layers.Dense(1, activation="sigmoid"),
    ], name=name)
    if model.count_params() != 849:
        raise RuntimeError(f"V4 parameter mismatch: {model.count_params()}")
    return model


def build_v6_baseline(name: str = "ecg_nv_cnn_v6_baseline") -> tf.keras.Model:
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
    model = tf.keras.Model(inp, out, name=name)
    if model.count_params() != 1969:
        raise RuntimeError(f"V6 parameter mismatch: {model.count_params()}")
    return model


def compute_metrics(y: np.ndarray, scores: np.ndarray, threshold: float) -> dict:
    y = np.asarray(y, dtype=np.int32)
    scores = np.asarray(scores, dtype=np.float64)
    pred = scores >= threshold
    tp = int(np.sum((y == 1) & pred))
    tn = int(np.sum((y == 0) & ~pred))
    fp = int(np.sum((y == 0) & pred))
    fn = int(np.sum((y == 1) & ~pred))
    n_pos = int(np.sum(y == 1))
    n_neg = int(np.sum(y == 0))
    precision = float(tp / (tp + fp)) if (tp + fp) > 0 else 0.0
    recall = float(tp / (tp + fn)) if (tp + fn) > 0 else 0.0
    f1 = float(2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0
    pr_auc = float(average_precision_score(y, scores)) if (n_pos > 0 and n_neg > 0) else None
    fp_per_1k_n = float(fp * 1000.0 / n_neg) if n_neg > 0 else None
    return {
        "samples": int(len(y)),
        "N": n_neg,
        "V": n_pos,
        "threshold": float(threshold),
        "accuracy": float((tp + tn) / len(y)) if len(y) > 0 else 0.0,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "pr_auc": pr_auc,
        "fp_per_1000_normal": fp_per_1k_n,
        "TP": tp,
        "FP": fp,
        "FN": fn,
        "TN": tn,
        "confusion_rows_N_V": [[tn, fp], [fn, tp]],
    }


def score_distribution_summary(y: np.ndarray, scores: np.ndarray) -> dict:
    out = {}
    for label, key in ((0, "N"), (1, "V")):
        sub = scores[y == label]
        if len(sub) == 0:
            out[key] = {"count": 0}
        else:
            q = np.quantile(sub, [0.05, 0.25, 0.50, 0.75, 0.90, 0.95, 0.99])
            out[key] = {
                "count": int(len(sub)),
                "mean": float(np.mean(sub)),
                "std": float(np.std(sub)),
                "q05": float(q[0]),
                "q25": float(q[1]),
                "median": float(q[2]),
                "q75": float(q[3]),
                "q90": float(q[4]),
                "q95": float(q[5]),
                "q99": float(q[6]),
                "frac_ge_050": float(np.mean(sub >= 0.50)),
                "frac_ge_087": float(np.mean(sub >= 0.87)),
                "frac_ge_088": float(np.mean(sub >= 0.88)),
            }
    return out


def pr_curve_grid(y: np.ndarray, scores: np.ndarray) -> list[dict]:
    grid = [0.10, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80, 0.85, 0.87, 0.88, 0.90, 0.92, 0.95]
    rows = []
    for t in grid:
        m = compute_metrics(y, scores, t)
        rows.append({
            "threshold": t,
            "precision": m["precision"],
            "recall": m["recall"],
            "f1": m["f1"],
            "FP": m["FP"],
            "FN": m["FN"],
            "fp_per_1000_normal": m["fp_per_1000_normal"],
        })
    return rows


def waveform_morphology_stats(x: np.ndarray, y: np.ndarray, scores_v4: np.ndarray, scores_v6: np.ndarray) -> dict:
    """Compute evidence-based waveform morphology metrics on N beats (central QRS vs periphery)."""
    n_mask = y == 0
    if not np.any(n_mask):
        return {}
    xn = x[n_mask, :, 0]
    sv4 = scores_v4[n_mask]
    sv6 = scores_v6[n_mask]
    center = xn[:, 96:160]
    periph = np.concatenate([xn[:, :96], xn[:, 160:]], axis=1)
    center_ptp = np.ptp(center, axis=1)
    periph_std = np.std(periph, axis=1)
    center_min = np.min(center, axis=1)
    center_max = np.max(center, axis=1)
    neg_polarity = np.abs(center_min) > np.abs(center_max)
    argmax_offset = np.abs(np.argmax(np.abs( xn[:, 103:153] ), axis=1) - 25)

    def summarize_mask(mask: np.ndarray) -> dict:
        if not np.any(mask):
            return {"count": 0}
        return {
            "count": int(np.sum(mask)),
            "median_center_ptp": float(np.median(center_ptp[mask])),
            "median_periph_std": float(np.median(periph_std[mask])),
            "neg_polarity_frac": float(np.mean(neg_polarity[mask])),
            "median_center_offset_samples": float(np.median(argmax_offset[mask])),
            "p90_center_offset_samples": float(np.quantile(argmax_offset[mask], 0.90)),
        }

    return {
        "all_N": summarize_mask(np.ones(len(xn), dtype=bool)),
        "v4_FP_at_088": summarize_mask(sv4 >= 0.88),
        "v4_TN_at_088": summarize_mask(sv4 < 0.88),
        "v6_FP_at_087": summarize_mask(sv6 >= 0.87),
        "v6_TN_at_087": summarize_mask(sv6 < 0.87),
    }


def run_step0_dev_analysis(mit_dev_x, mit_dev_y, mit_dev_rec, inc_dev_x, inc_dev_y, inc_dev_pat) -> dict:
    print("=== Running Step 0: Development Analysis (V4 vs V6) ===")
    STEP0_DIR.mkdir(parents=True, exist_ok=True)
    v4 = tf.keras.models.load_model(V4_MODEL_PATH, compile=False)
    v6 = tf.keras.models.load_model(V6_MODEL_PATH, compile=False)
    v6_cfg = json.loads(V6_CONFIG_PATH.read_text(encoding="utf-8"))
    dev_part = v6_cfg["development_partition"]

    mit_v4_scores = v4.predict(mit_dev_x, batch_size=512, verbose=0).reshape(-1)
    mit_v6_scores = v6.predict(mit_dev_x, batch_size=512, verbose=0).reshape(-1)
    inc_v4_scores = v4.predict(inc_dev_x, batch_size=512, verbose=0).reshape(-1)
    inc_v6_scores = v6.predict(inc_dev_x, batch_size=512, verbose=0).reshape(-1)

    mit_per_record = {}
    for rec in sorted(np.unique(mit_dev_rec)):
        m = mit_dev_rec == rec
        role = "checkpoint" if rec in dev_part["MITBIH_checkpoint_records"] else "threshold"
        mit_per_record[rec] = {
            "partition_role_in_v6": role,
            "samples": int(np.sum(m)),
            "N": int(np.sum(mit_dev_y[m] == 0)),
            "V": int(np.sum(mit_dev_y[m] == 1)),
            "V4_at_088": compute_metrics(mit_dev_y[m], mit_v4_scores[m], 0.88),
            "V6_at_087": compute_metrics(mit_dev_y[m], mit_v6_scores[m], 0.87),
            "V4_score_dist": score_distribution_summary(mit_dev_y[m], mit_v4_scores[m]),
            "V6_score_dist": score_distribution_summary(mit_dev_y[m], mit_v6_scores[m]),
            "morphology_N": waveform_morphology_stats(mit_dev_x[m], mit_dev_y[m], mit_v4_scores[m], mit_v6_scores[m]),
        }

    inc_per_patient = {}
    for pat in sorted(np.unique(inc_dev_pat), key=int):
        m = inc_dev_pat == pat
        role = "checkpoint" if pat in dev_part["INCART_checkpoint_patients"] else "threshold"
        inc_per_patient[pat] = {
            "partition_role_in_v6": role,
            "samples": int(np.sum(m)),
            "N": int(np.sum(inc_dev_y[m] == 0)),
            "V": int(np.sum(inc_dev_y[m] == 1)),
            "V4_at_088": compute_metrics(inc_dev_y[m], inc_v4_scores[m], 0.88),
            "V6_at_087": compute_metrics(inc_dev_y[m], inc_v6_scores[m], 0.87),
            "V4_score_dist": score_distribution_summary(inc_dev_y[m], inc_v4_scores[m]),
            "V6_score_dist": score_distribution_summary(inc_dev_y[m], inc_v6_scores[m]),
            "morphology_N": waveform_morphology_stats(inc_dev_x[m], inc_dev_y[m], inc_v4_scores[m], inc_v6_scores[m]),
        }

    analysis = {
        "scope": "Development (Validation) analysis only; no Train predictions called OOF; no Test accessed",
        "models": {
            "V4": {"path": str(V4_MODEL_PATH.relative_to(ROOT)), "sha256": sha256_file(V4_MODEL_PATH), "locked_threshold": 0.88},
            "V6": {"path": str(V6_MODEL_PATH.relative_to(ROOT)), "sha256": sha256_file(V6_MODEL_PATH), "locked_threshold": 0.87},
        },
        "overall_development": {
            "MITBIH": {
                "V4_at_088": compute_metrics(mit_dev_y, mit_v4_scores, 0.88),
                "V6_at_087": compute_metrics(mit_dev_y, mit_v6_scores, 0.87),
                "V4_score_dist": score_distribution_summary(mit_dev_y, mit_v4_scores),
                "V6_score_dist": score_distribution_summary(mit_dev_y, mit_v6_scores),
                "V4_pr_curve_grid": pr_curve_grid(mit_dev_y, mit_v4_scores),
                "V6_pr_curve_grid": pr_curve_grid(mit_dev_y, mit_v6_scores),
                "morphology_N": waveform_morphology_stats(mit_dev_x, mit_dev_y, mit_v4_scores, mit_v6_scores),
            },
            "INCART": {
                "V4_at_088": compute_metrics(inc_dev_y, inc_v4_scores, 0.88),
                "V6_at_087": compute_metrics(inc_dev_y, inc_v6_scores, 0.87),
                "V4_score_dist": score_distribution_summary(inc_dev_y, inc_v4_scores),
                "V6_score_dist": score_distribution_summary(inc_dev_y, inc_v6_scores),
                "V4_pr_curve_grid": pr_curve_grid(inc_dev_y, inc_v4_scores),
                "V6_pr_curve_grid": pr_curve_grid(inc_dev_y, inc_v6_scores),
                "morphology_N": waveform_morphology_stats(inc_dev_x, inc_dev_y, inc_v4_scores, inc_v6_scores),
            },
        },
        "per_record_MITBIH_development": mit_per_record,
        "per_patient_INCART_development": inc_per_patient,
    }
    (STEP0_DIR / "dev_analysis.json").write_text(json.dumps(analysis, indent=2) + "\n", encoding="utf-8")
    return analysis


def build_balanced_5fold_group_splits(
    mit_y: np.ndarray, mit_rec: np.ndarray, inc_y: np.ndarray, inc_pat: np.ndarray, seed: int = SEED
) -> list[dict]:
    """Search deterministic random permutations to partition 38 MIT records and 27 INCART patients into 5 balanced outer folds."""
    rng = np.random.default_rng(seed)
    mit_groups = sorted(np.unique(mit_rec))
    inc_groups = sorted(np.unique(inc_pat), key=int)

    mit_stats = {g: (int(np.sum((mit_rec == g) & (mit_y == 0))), int(np.sum((mit_rec == g) & (mit_y == 1)))) for g in mit_groups}
    inc_stats = {g: (int(np.sum((inc_pat == g) & (inc_y == 0))), int(np.sum((inc_pat == g) & (inc_y == 1)))) for g in inc_groups}

    total_mit_n = sum(v[0] for v in mit_stats.values())
    total_mit_v = sum(v[1] for v in mit_stats.values())
    total_inc_n = sum(v[0] for v in inc_stats.values())
    total_inc_v = sum(v[1] for v in inc_stats.values())

    best_mit_folds = None
    best_mit_score = float("inf")
    for _ in range(25_000):
        perm = list(rng.permutation(mit_groups))
        folds = [perm[i::5] for i in range(5)]
        n_counts = [sum(mit_stats[g][0] for g in f) for f in folds]
        v_counts = [sum(mit_stats[g][1] for g in f) for f in folds]
        if min(v_counts) < 600 or min(n_counts) < 8_000:
            continue
        score = max(abs(v - total_mit_v / 5) / (total_mit_v / 5) for v in v_counts) + 0.5 * max(
            abs(n - total_mit_n / 5) / (total_mit_n / 5) for n in n_counts
        )
        if score < best_mit_score:
            best_mit_score = score
            best_mit_folds = [sorted(f) for f in folds]

    best_inc_folds = None
    best_inc_score = float("inf")
    for _ in range(25_000):
        perm = list(rng.permutation(inc_groups))
        folds = [perm[i::5] for i in range(5)]
        n_counts = [sum(inc_stats[g][0] for g in f) for f in folds]
        v_counts = [sum(inc_stats[g][1] for g in f) for f in folds]
        if min(v_counts) < 2_000 or min(n_counts) < 15_000:
            continue
        score = max(abs(v - total_inc_v / 5) / (total_inc_v / 5) for v in v_counts) + 0.5 * max(
            abs(n - total_inc_n / 5) / (total_inc_n / 5) for n in n_counts
        )
        if score < best_inc_score:
            best_inc_score = score
            best_inc_folds = [sorted(f, key=int) for f in folds]

    if best_mit_folds is None or best_inc_folds is None:
        raise RuntimeError("Failed to find balanced 5-fold group split")

    # Verify strict group disjointness across the 5 outer folds
    assert sum(len(f) for f in best_mit_folds) == len(mit_groups) == len(set().union(*best_mit_folds))
    assert sum(len(f) for f in best_inc_folds) == len(inc_groups) == len(set().union(*best_inc_folds))

    folds_spec = []
    for k in range(5):
        outer_fold = k
        checkpoint_fold = (k + 1) % 5
        threshold_fold = (k + 2) % 5
        fit_folds = [f for f in range(5) if f not in (outer_fold, checkpoint_fold, threshold_fold)]
        folds_spec.append({
            "fold_index": k,
            "outer_eval_fold_id": outer_fold,
            "inner_checkpoint_fold_id": checkpoint_fold,
            "inner_threshold_fold_id": threshold_fold,
            "inner_fit_fold_ids": fit_folds,
            "outer_MITBIH_records": best_mit_folds[outer_fold],
            "outer_INCART_patients": best_inc_folds[outer_fold],
            "checkpoint_MITBIH_records": best_mit_folds[checkpoint_fold],
            "checkpoint_INCART_patients": best_inc_folds[checkpoint_fold],
            "threshold_MITBIH_records": best_mit_folds[threshold_fold],
            "threshold_INCART_patients": best_inc_folds[threshold_fold],
            "fit_MITBIH_records": sorted([g for idx in fit_folds for g in best_mit_folds[idx]]),
            "fit_INCART_patients": sorted([g for idx in fit_folds for g in best_inc_folds[idx]], key=int),
        })
    return folds_spec


class BaselineTrainSequence(tf.keras.utils.Sequence):
    def __init__(self, x: np.ndarray, y: np.ndarray, weights: dict[int, float], seed: int):
        super().__init__()
        self.x = x
        self.y = y
        self.weights = weights
        self.seed = seed
        self.epoch = 0
        self.order = np.arange(len(y))
        self.on_epoch_end()

    def __len__(self) -> int:
        return math.ceil(len(self.y) / BATCH_SIZE)

    def __getitem__(self, batch_index: int):
        indices = self.order[batch_index * BATCH_SIZE:(batch_index + 1) * BATCH_SIZE]
        x = self.x[indices]
        y = self.y[indices]
        sample_weight = np.where(y == 0, self.weights[0], self.weights[1]).astype(np.float32)
        return x, y, sample_weight

    def on_epoch_end(self):
        self.epoch += 1
        self.order = np.random.default_rng(self.seed + self.epoch).permutation(len(self.y))


class CheckpointAPSelector(tf.keras.callbacks.Callback):
    def __init__(self, x: np.ndarray, y: np.ndarray, path: Path):
        super().__init__()
        self.x = x
        self.y = y
        self.path = path
        self.best_ap = -1.0
        self.best_epoch = 0
        self.wait = 0
        self.history: list[dict] = []

    def on_epoch_end(self, epoch, logs=None):
        scores = self.model.predict(self.x, batch_size=512, verbose=0).reshape(-1)
        ap = float(average_precision_score(self.y, scores))
        loss = float((logs or {}).get("loss", np.nan))
        self.history.append({"epoch": epoch + 1, "checkpoint_pr_auc": ap, "loss": loss})
        if ap > self.best_ap + 1e-12:
            self.best_ap = ap
            self.best_epoch = epoch + 1
            self.wait = 0
            self.model.save(self.path)
        else:
            self.wait += 1
        if self.wait >= PATIENCE:
            self.model.stop_training = True


def select_threshold_on_cal_fold(y: np.ndarray, scores: np.ndarray) -> dict:
    return max(
        (compute_metrics(y, scores, float(t)) for t in THRESHOLDS),
        key=lambda row: (row["f1"], row["precision"], -row["threshold"]),
    )


def summarize_across_folds(fold_rows: list[dict], dataset_key: str) -> dict:
    metrics_keys = ["precision", "recall", "f1", "pr_auc", "fp_per_1000_normal", "accuracy"]
    summary = {}
    for mk in metrics_keys:
        vals = np.array([r[dataset_key][mk] for r in fold_rows], dtype=np.float64)
        summary[mk] = {
            "mean": float(np.mean(vals)),
            "std": float(np.std(vals, ddof=0)),
            "min": float(np.min(vals)),
            "max": float(np.max(vals)),
            "per_fold": [float(v) for v in vals],
        }
    f1s = [r[dataset_key]["f1"] for r in fold_rows]
    worst_idx = int(np.argmin(f1s))
    summary["worst_fold_by_f1"] = {
        "fold_index": worst_idx,
        "f1": float(f1s[worst_idx]),
        "precision": float(fold_rows[worst_idx][dataset_key]["precision"]),
        "recall": float(fold_rows[worst_idx][dataset_key]["recall"]),
        "fp_per_1000_normal": float(fold_rows[worst_idx][dataset_key]["fp_per_1000_normal"]),
        "FP": int(fold_rows[worst_idx][dataset_key]["FP"]),
        "FN": int(fold_rows[worst_idx][dataset_key]["FN"]),
    }
    summary["total_TP"] = int(sum(r[dataset_key]["TP"] for r in fold_rows))
    summary["total_FP"] = int(sum(r[dataset_key]["FP"] for r in fold_rows))
    summary["total_FN"] = int(sum(r[dataset_key]["FN"] for r in fold_rows))
    summary["total_TN"] = int(sum(r[dataset_key]["TN"] for r in fold_rows))
    tp, fp, fn, tn = summary["total_TP"], summary["total_FP"], summary["total_FN"], summary["total_TN"]
    p_pool = tp / (tp + fp) if (tp + fp) else 0.0
    r_pool = tp / (tp + fn) if (tp + fn) else 0.0
    f1_pool = 2 * p_pool * r_pool / (p_pool + r_pool) if (p_pool + r_pool) else 0.0
    summary["pooled_micro"] = {
        "precision": float(p_pool),
        "recall": float(r_pool),
        "f1": float(f1_pool),
        "fp_per_1000_normal": float(fp * 1000.0 / (tn + fp)) if (tn + fp) else 0.0,
    }
    return summary


def main() -> None:
    t0 = time.time()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    STEP1_DIR.mkdir(parents=True, exist_ok=True)
    STEP1_MODELS_DIR.mkdir(parents=True, exist_ok=True)

    tf.config.threading.set_inter_op_parallelism_threads(1)
    tf.config.threading.set_intra_op_parallelism_threads(2)
    tf.config.experimental.enable_op_determinism()

    mit = np.load(MIT_PATH)
    mit_split = np.load(MIT_SPLIT_PATH)
    inc = np.load(INC_PATH)

    # STRICT TEST GUARD: Only load train and validation splits
    mit_train_idx = mit_split["train_indices"]
    mit_val_idx = mit_split["validation_indices"]
    mit_test_idx = mit_split["test_indices"]
    assert len( np.intersect1d(mit_train_idx, mit_test_idx) ) == 0
    assert len( np.intersect1d(mit_val_idx, mit_test_idx) ) == 0

    inc_split_str = inc["split"].astype(str)
    inc_train_mask = inc_split_str == "train"
    inc_val_mask = inc_split_str == "validation"
    assert not np.any(inc_split_str[inc_train_mask | inc_val_mask] == "test")

    # Step 0: Development analysis on original Validation sets
    step0_result = run_step0_dev_analysis(
        mit["X"][mit_val_idx], mit["y"][mit_val_idx].astype(np.int32), mit["record_ids"][mit_val_idx].astype(str),
        inc["X"][inc_val_mask], inc["y"][inc_val_mask].astype(np.int32), inc["patient_ids"][inc_val_mask].astype(str),
    )

    # Combine Train + Validation for Step 1 5-Fold Group CV
    mit_tv_idx = np.concatenate([mit_train_idx, mit_val_idx])
    mit_x = mit["X"][mit_tv_idx]
    mit_y = mit["y"][mit_tv_idx].astype(np.int32)
    mit_rec = mit["record_ids"][mit_tv_idx].astype(str)

    inc_tv_mask = inc_train_mask | inc_val_mask
    inc_x = inc["X"][inc_tv_mask]
    inc_y = inc["y"][inc_tv_mask].astype(np.int32)
    inc_pat = inc["patient_ids"][inc_tv_mask].astype(str)

    folds_spec = build_balanced_5fold_group_splits(mit_y, mit_rec, inc_y, inc_pat, seed=SEED)
    (STEP1_DIR / "folds_split.json").write_text(json.dumps(folds_spec, indent=2) + "\n", encoding="utf-8")

    architectures = {
        "V4": build_v4_baseline,
        "V6": build_v6_baseline,
    }

    cv_results = {
        "protocol": {
            "seed": SEED,
            "outer_folds": 5,
            "split_design": "3 folds Fit / 1 fold Checkpoint Selection (PR-AUC) / 1 fold Threshold Calibration (max F1) / 1 Outer Fold Evaluation",
            "batch_size": BATCH_SIZE,
            "max_epochs": MAX_EPOCHS,
            "patience": PATIENCE,
            "optimizer": "Adam(0.001)",
            "loss": "binary_crossentropy",
            "augmentation": False,
            "test_accessed": False,
            "third_party_datasets_used": False,
        },
        "models": {},
    }

    for arch_name, builder in architectures.items():
        print(f"\n=== Running 5-Fold Group CV for {arch_name} ===")
        fold_evals = []
        for fold_info in folds_spec:
            k = fold_info["fold_index"]
            fold_cache_path = STEP1_DIR / f"fold_{arch_name.lower()}_{k}.json"
            ckpt_path = STEP1_MODELS_DIR / f"{arch_name.lower()}_fold{k}_best.keras"
            if fold_cache_path.exists() and ckpt_path.exists():
                cached_row = json.loads(fold_cache_path.read_text(encoding="utf-8"))
                if cached_row.get("checkpoint_sha256") == sha256_file(ckpt_path) and "MITBIH" in cached_row and "INCART" in cached_row:
                    print(f" [{arch_name} Fold {k}] Resumed from valid cached result & checkpoint.")
                    fold_evals.append(cached_row)
                    continue
            f_t0 = time.time()
            fit_mit_mask = np.isin(mit_rec, fold_info["fit_MITBIH_records"])
            cp_mit_mask = np.isin(mit_rec, fold_info["checkpoint_MITBIH_records"])
            th_mit_mask = np.isin(mit_rec, fold_info["threshold_MITBIH_records"])
            out_mit_mask = np.isin(mit_rec, fold_info["outer_MITBIH_records"])

            fit_inc_mask = np.isin(inc_pat, fold_info["fit_INCART_patients"])
            cp_inc_mask = np.isin(inc_pat, fold_info["checkpoint_INCART_patients"])
            th_inc_mask = np.isin(inc_pat, fold_info["threshold_INCART_patients"])
            out_inc_mask = np.isin(inc_pat, fold_info["outer_INCART_patients"])

            # Verify strict disjointness inside fold k
            assert not np.any(fit_mit_mask & out_mit_mask) and not np.any(cp_mit_mask & out_mit_mask) and not np.any(th_mit_mask & out_mit_mask)
            assert not np.any(fit_inc_mask & out_inc_mask) and not np.any(cp_inc_mask & out_inc_mask) and not np.any(th_inc_mask & out_inc_mask)

            x_fit = np.concatenate([mit_x[fit_mit_mask], inc_x[fit_inc_mask]])
            y_fit = np.concatenate([mit_y[fit_mit_mask], inc_y[fit_inc_mask]])
            counts = np.bincount(y_fit, minlength=2)
            class_weight = {i: float(len(y_fit) / (2 * counts[i])) for i in (0, 1)}

            x_cp = np.concatenate([mit_x[cp_mit_mask], inc_x[cp_inc_mask]])
            y_cp = np.concatenate([mit_y[cp_mit_mask], inc_y[cp_inc_mask]])

            x_th = np.concatenate([mit_x[th_mit_mask], inc_x[th_inc_mask]])
            y_th = np.concatenate([mit_y[th_mit_mask], inc_y[th_inc_mask]])

            tf.keras.backend.clear_session()
            fold_seed = SEED + k * 1000
            random.seed(fold_seed)
            np.random.seed(fold_seed)
            tf.keras.utils.set_random_seed(fold_seed)

            model = builder(f"{arch_name.lower()}_fold{k}")
            model.compile(optimizer=tf.keras.optimizers.Adam(0.001), loss="binary_crossentropy")
            ckpt_path = STEP1_MODELS_DIR / f"{arch_name.lower()}_fold{k}_best.keras"
            selector = CheckpointAPSelector(x_cp, y_cp, ckpt_path)
            seq = BaselineTrainSequence(x_fit, y_fit, class_weight, seed=fold_seed)

            model.fit(
                seq,
                epochs=MAX_EPOCHS,
                verbose=0,
                callbacks=[selector, tf.keras.callbacks.TerminateOnNaN()],
            )

            best_model = tf.keras.models.load_model(ckpt_path, compile=False)
            th_scores = best_model.predict(x_th, batch_size=512, verbose=0).reshape(-1)
            th_selected = select_threshold_on_cal_fold(y_th, th_scores)
            locked_t = th_selected["threshold"]

            # Outer fold evaluation (MIT-BIH and INCART separately + combined)
            out_mit_scores = best_model.predict(mit_x[out_mit_mask], batch_size=512, verbose=0).reshape(-1)
            out_inc_scores = best_model.predict(inc_x[out_inc_mask], batch_size=512, verbose=0).reshape(-1)
            out_comb_y = np.concatenate([mit_y[out_mit_mask], inc_y[out_inc_mask]])
            out_comb_scores = np.concatenate([out_mit_scores, out_inc_scores])

            mit_metrics = compute_metrics(mit_y[out_mit_mask], out_mit_scores, locked_t)
            inc_metrics = compute_metrics(inc_y[out_inc_mask], out_inc_scores, locked_t)
            comb_metrics = compute_metrics(out_comb_y, out_comb_scores, locked_t)

            # Per-group breakdown in outer fold to identify worst records/patients
            outer_mit_per_rec = {}
            for r in fold_info["outer_MITBIH_records"]:
                rm = mit_rec[out_mit_mask] == r
                outer_mit_per_rec[r] = compute_metrics(mit_y[out_mit_mask][rm], out_mit_scores[rm], locked_t)

            outer_inc_per_pat = {}
            for p in fold_info["outer_INCART_patients"]:
                pm = inc_pat[out_inc_mask] == p
                outer_inc_per_pat[p] = compute_metrics(inc_y[out_inc_mask][pm], out_inc_scores[pm], locked_t)

            elapsed = time.time() - f_t0
            print(
                f" [{arch_name} Fold {k}] ({elapsed:.1f}s) best_ep={selector.best_epoch}/{len(selector.history)} "
                f"cp_PR_AUC={selector.best_ap:.4f} cal_t={locked_t:.2f} | "
                f"MIT F1={100*mit_metrics['f1']:.2f}% (P={100*mit_metrics['precision']:.2f}%, R={100*mit_metrics['recall']:.2f}%, FP/1kN={mit_metrics['fp_per_1000_normal']:.2f}) | "
                f"INC F1={100*inc_metrics['f1']:.2f}% (P={100*inc_metrics['precision']:.2f}%, R={100*inc_metrics['recall']:.2f}%, FP/1kN={inc_metrics['fp_per_1000_normal']:.2f})"
            )

            fold_evals.append({
            fold_row = {
                "fold_index": k,
                "seed": fold_seed,
                "fit_samples": int(len(y_fit)),
                "class_weight": class_weight,
                "best_epoch": selector.best_epoch,
                "epochs_run": len(selector.history),
                "checkpoint_pr_auc": selector.best_ap,
                "calibrated_threshold": locked_t,
                "threshold_calibration_metrics": th_selected,
                "checkpoint_sha256": sha256_file(ckpt_path),
                "MITBIH": mit_metrics,
                "INCART": inc_metrics,
                "combined": comb_metrics,
                "outer_MITBIH_per_record": outer_mit_per_rec,
                "outer_INCART_per_patient": outer_inc_per_pat,
            })
            }
            fold_cache_path.write_text(json.dumps(fold_row, indent=2) + "\n", encoding="utf-8")
            fold_evals.append(fold_row)

        cv_results["models"][arch_name] = {
            "parameters": int(builder().count_params()),
            "folds": fold_evals,
            "summary": {
                "MITBIH": summarize_across_folds(fold_evals, "MITBIH"),
                "INCART": summarize_across_folds(fold_evals, "INCART"),
                "combined": summarize_across_folds(fold_evals, "combined"),
                "calibrated_thresholds": [r["calibrated_threshold"] for r in fold_evals],
            },
        }

    cv_results["total_runtime_seconds"] = float(time.time() - t0)
    (STEP1_DIR / "cv_evaluation.json").write_text(json.dumps(cv_results, indent=2) + "\n", encoding="utf-8")
    print(f"\nCompleted Step 0 and Step 1 in {cv_results['total_runtime_seconds']:.1f}s.")


if __name__ == "__main__":
    main()
