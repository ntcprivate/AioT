from __future__ import annotations

import hashlib
import json
import os
import random
import time
from pathlib import Path

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
os.environ.setdefault("TF_ENABLE_ONEDNN_OPTS", "0")

import numpy as np
import tensorflow as tf

from run_v10_step0_step1 import (
    BaselineTrainSequence,
    CheckpointAPSelector,
    compute_metrics,
    select_threshold_on_cal_fold,
    sha256_file,
    summarize_across_folds,
)


ROOT = Path(__file__).resolve().parents[1]
MIT_PATH = ROOT / "data/processed/mitbih_nv_250hz.npz"
MIT_SPLIT_PATH = ROOT / "data/processed/mitbih_split_indices.npz"
INC_PATH = ROOT / "data/processed/incart_v4_250hz.npz"
STEP1_DIR = ROOT / "results/v10_research/step1_5fold_cv"
STEP2_DIR = ROOT / "results/v10_research/step2"
CKPT_DIR = STEP2_DIR / "checkpoints"
SEED = 42
MAX_EPOCHS = 20


def build_v10a(name: str = "ecg_nv_cnn_v10a") -> tf.keras.Model:
    inp = tf.keras.layers.Input((256, 1), name="ecg_256")
    center = tf.keras.layers.Cropping1D((64, 64), name="central_qrs_128")(inp)
    center = tf.keras.layers.Conv1D(8, 5, activation="relu", name="qrs_conv5_a")(center)
    center = tf.keras.layers.MaxPooling1D(2, name="qrs_pool_a")(center)
    center = tf.keras.layers.Conv1D(12, 5, activation="relu", name="qrs_conv5_b")(center)
    center = tf.keras.layers.SpatialDropout1D(0.1, name="qrs_spatial_dropout")(center)
    center = tf.keras.layers.MaxPooling1D(2, name="qrs_pool_b")(center)
    center = tf.keras.layers.GlobalAveragePooling1D(name="qrs_gap")(center)
    center = tf.keras.layers.Dense(8, activation="relu", name="qrs_dense")(center)

    context = tf.keras.layers.Conv1D(8, 15, activation="relu", name="context_conv15")(inp)
    context = tf.keras.layers.MaxPooling1D(4, name="context_pool")(context)
    context = tf.keras.layers.Conv1D(12, 9, activation="relu", name="context_conv9")(context)
    context = tf.keras.layers.SpatialDropout1D(0.1, name="context_spatial_dropout")(context)
    context = tf.keras.layers.GlobalAveragePooling1D(name="context_gap")(context)
    context = tf.keras.layers.Dense(8, activation="relu", name="context_dense")(context)

    merged = tf.keras.layers.Concatenate(name="multiscale_merge")([center, context])
    merged = tf.keras.layers.Dense(12, activation="relu", name="fusion_dense")(merged)
    out = tf.keras.layers.Dense(1, activation="sigmoid", name="pvc_probability")(merged)
    model = tf.keras.Model(inp, out, name=name)
    if model.count_params() != 1969:
        raise RuntimeError(f"V10-A parameter contract failed: {model.count_params()}")
    return model


def load_tv_data():
    mit = np.load(MIT_PATH)
    split = np.load(MIT_SPLIT_PATH)
    inc = np.load(INC_PATH)
    mit_idx = np.concatenate([split["train_indices"], split["validation_indices"]])
    inc_mask = np.isin(inc["split"].astype(str), ["train", "validation"])
    return (
        mit["X"][mit_idx], mit["y"][mit_idx].astype(np.int32), mit["record_ids"][mit_idx].astype(str),
        inc["X"][inc_mask], inc["y"][inc_mask].astype(np.int32), inc["patient_ids"][inc_mask].astype(str),
    )


def valid_cached(row: dict, checkpoint: Path, fold_index: int) -> bool:
    return (
        row.get("fold_index") == fold_index
        and checkpoint.exists()
        and row.get("checkpoint_sha256") == sha256_file(checkpoint)
        and all(key in row for key in ("MITBIH", "INCART", "combined"))
    )


def main() -> None:
    started = time.time()
    STEP2_DIR.mkdir(parents=True, exist_ok=True)
    CKPT_DIR.mkdir(parents=True, exist_ok=True)
    tf.config.threading.set_inter_op_parallelism_threads(1)
    tf.config.threading.set_intra_op_parallelism_threads(2)
    tf.config.experimental.enable_op_determinism()

    folds = json.loads((STEP1_DIR / "folds_split.json").read_text(encoding="utf-8"))
    step1 = json.loads((STEP1_DIR / "cv_evaluation.json").read_text(encoding="utf-8"))
    mit_x, mit_y, mit_g, inc_x, inc_y, inc_g = load_tv_data()
    fold_rows = []

    for spec in folds:
        k = int(spec["fold_index"])
        cache = STEP2_DIR / f"fold_v10a_{k}.json"
        checkpoint = CKPT_DIR / f"v10a_fold{k}_best.keras"
        if cache.exists():
            row = json.loads(cache.read_text(encoding="utf-8"))
            if valid_cached(row, checkpoint, k):
                print(f"[V10-A fold {k}] valid cache; skipped")
                fold_rows.append(row)
                continue

        masks = {}
        for role, key in (("fit", "fit"), ("cp", "checkpoint"), ("th", "threshold"), ("out", "outer")):
            masks[(role, "mit")] = np.isin(mit_g, spec[f"{key}_MITBIH_records"])
            masks[(role, "inc")] = np.isin(inc_g, spec[f"{key}_INCART_patients"])
        for dataset in ("mit", "inc"):
            role_masks = [masks[(role, dataset)] for role in ("fit", "cp", "th", "out")]
            for i in range(4):
                for j in range(i + 1, 4):
                    if np.any(role_masks[i] & role_masks[j]):
                        raise RuntimeError(f"Fold {k}: group leakage in {dataset}")

        x_fit = np.concatenate([mit_x[masks[("fit", "mit")]], inc_x[masks[("fit", "inc")]]])
        y_fit = np.concatenate([mit_y[masks[("fit", "mit")]], inc_y[masks[("fit", "inc")]]])
        x_cp = np.concatenate([mit_x[masks[("cp", "mit")]], inc_x[masks[("cp", "inc")]]])
        y_cp = np.concatenate([mit_y[masks[("cp", "mit")]], inc_y[masks[("cp", "inc")]]])
        x_th = np.concatenate([mit_x[masks[("th", "mit")]], inc_x[masks[("th", "inc")]]])
        y_th = np.concatenate([mit_y[masks[("th", "mit")]], inc_y[masks[("th", "inc")]]])
        counts = np.bincount(y_fit, minlength=2)
        class_weight = {i: float(len(y_fit) / (2 * counts[i])) for i in (0, 1)}

        fold_seed = SEED + k * 1000
        tf.keras.backend.clear_session()
        random.seed(fold_seed); np.random.seed(fold_seed); tf.keras.utils.set_random_seed(fold_seed)
        model = build_v10a(f"v10a_fold{k}")
        model.compile(optimizer=tf.keras.optimizers.Adam(0.001), loss="binary_crossentropy")
        selector = CheckpointAPSelector(x_cp, y_cp, checkpoint)
        model.fit(
            BaselineTrainSequence(x_fit, y_fit, class_weight, seed=fold_seed),
            epochs=MAX_EPOCHS, verbose=0,
            callbacks=[selector, tf.keras.callbacks.TerminateOnNaN()],
        )
        best = tf.keras.models.load_model(checkpoint, compile=False)
        th_scores = best.predict(x_th, batch_size=512, verbose=0).reshape(-1)
        threshold_row = select_threshold_on_cal_fold(y_th, th_scores)
        threshold = threshold_row["threshold"]
        mit_out = masks[("out", "mit")]; inc_out = masks[("out", "inc")]
        mit_scores = best.predict(mit_x[mit_out], batch_size=512, verbose=0).reshape(-1)
        inc_scores = best.predict(inc_x[inc_out], batch_size=512, verbose=0).reshape(-1)
        combined_y = np.concatenate([mit_y[mit_out], inc_y[inc_out]])
        combined_scores = np.concatenate([mit_scores, inc_scores])
        row = {
            "fold_index": k, "seed": fold_seed, "fit_samples": int(len(y_fit)),
            "class_weight": class_weight, "best_epoch": selector.best_epoch,
            "epochs_run": len(selector.history), "checkpoint_pr_auc": selector.best_ap,
            "calibrated_threshold": threshold, "threshold_calibration_metrics": threshold_row,
            "checkpoint_sha256": sha256_file(checkpoint),
            "MITBIH": compute_metrics(mit_y[mit_out], mit_scores, threshold),
            "INCART": compute_metrics(inc_y[inc_out], inc_scores, threshold),
            "combined": compute_metrics(combined_y, combined_scores, threshold),
        }
        cache.write_text(json.dumps(row, indent=2) + "\n", encoding="utf-8")
        fold_rows.append(row)
        print(f"[V10-A fold {k}] completed; best_epoch={selector.best_epoch}, threshold={threshold:.2f}")

    result = {
        "protocol": {
            "seed": SEED, "architecture": "V6 + SpatialDropout1D(0.1) after final Conv1D in both branches",
            "parameters": 1969, "outer_folds": 5,
            "split_source": str((STEP1_DIR / "folds_split.json").relative_to(ROOT)),
            "checkpoint_selection": "PR-AUC on disjoint checkpoint fold",
            "threshold_selection": "max F1 on disjoint calibration fold",
            "fit_folds": 2, "augmentation": False, "test_accessed": False,
        },
        "V10-A": {"folds": fold_rows, "summary": {
            "MITBIH": summarize_across_folds(fold_rows, "MITBIH"),
            "INCART": summarize_across_folds(fold_rows, "INCART"),
            "combined": summarize_across_folds(fold_rows, "combined"),
            "calibrated_thresholds": [r["calibrated_threshold"] for r in fold_rows],
        }},
        "V6_step1": step1["models"]["V6"]["summary"],
        "runtime_seconds_this_invocation": time.time() - started,
    }
    (STEP2_DIR / "evaluation.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    (STEP2_DIR / "config.json").write_text(json.dumps(result["protocol"], indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
