"""Step-1 protocol reused unchanged; only central-branch normalization differs."""
import os
os.environ["TF_ENABLE_ONEDNN_OPTS"] = "0"
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
import json
import numpy as np
import tensorflow as tf
import run_v10_step2_v10a as runner


@tf.keras.utils.register_keras_serializable(package="ECG")
class CentralZScore(tf.keras.layers.Layer):
    def call(self, x):
        mean = tf.reduce_mean(x, axis=1, keepdims=True)
        std = tf.sqrt(tf.reduce_mean(tf.square(x - mean), axis=1, keepdims=True))
        return tf.where(std > 1e-8, (x - mean) / tf.maximum(std, 1e-8), tf.zeros_like(x))


def build(name="v10b"):
    from run_v10_step0_step1 import build_v6_baseline
    base = build_v6_baseline(name)
    def clone(layer):
        if isinstance(layer, tf.keras.layers.Cropping1D):
            return tf.keras.Sequential([
                tf.keras.layers.Cropping1D.from_config(layer.get_config()), CentralZScore()
            ], name="central_crop_zscore")
        return layer.__class__.from_config(layer.get_config())
    model = tf.keras.models.clone_model(base, clone_function=clone)
    assert model.count_params() == 1969
    return model


if __name__ == "__main__":
    runner.STEP2_DIR = runner.ROOT / "results/v10_research/step3_consistent_runtime"
    runner.CKPT_DIR = runner.STEP2_DIR / "checkpoints"
    runner.STEP2_DIR.mkdir(parents=True, exist_ok=True)
    metadata = {"tensorflow": tf.__version__, "numpy": np.__version__,
                "TF_ENABLE_ONEDNN_OPTS": os.environ["TF_ENABLE_ONEDNN_OPTS"],
                "folds_sha256": runner.sha256_file(runner.STEP1_DIR / "folds_split.json"),
                "baseline_runtime_evidence": "Step1 and Step2 set oneDNN=0 before importing TensorFlow; historical effective environment not recorded, so retrospective verification is limited"}
    (runner.STEP2_DIR / "runtime.json").write_text(json.dumps(metadata, indent=2))
    runner.build_v10a = build
    runner.main()
    # Preserve runner's metric schema; explicitly identify this experiment.
    path = runner.STEP2_DIR / "evaluation.json"
    result = json.loads(path.read_text())
    result["V10-B"] = result.pop("V10-A")
    result["protocol"]["architecture"] = "V6; central crop z-score epsilon=1e-8; context full-window z-score"
    result["protocol"]["adaptive_evaluation_limit"] = "Outer CV previously inspected to motivate V10-B; not independent confirmation"
    path.write_text(json.dumps(result, indent=2))
    (runner.STEP2_DIR / "config.json").write_text(json.dumps(result["protocol"], indent=2))
