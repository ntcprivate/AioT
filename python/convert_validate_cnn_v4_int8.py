from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
os.environ.setdefault("TF_ENABLE_ONEDNN_OPTS", "0")
import numpy as np
import tensorflow as tf

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/processed/incart_v4_250hz.npz"
MIT = ROOT / "data/processed/mitbih_nv_250hz.npz"
MIT_SPLIT = ROOT / "data/processed/mitbih_split_indices.npz"
KERAS = ROOT / "models/v4/ecg_cnn_v4_best.keras"
INT8 = ROOT / "models/v4/ecg_cnn_v4_int8.tflite"
RESULTS = ROOT / "results/cnn_v4"
REPORT = RESULTS / "int8_conversion.json"
HOST = ROOT / "results/cnn_v4/v4_tflm_host.exe"
THRESHOLD = 0.88
SEED = 42


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def metric(y, scores):
    p = scores >= THRESHOLD
    tp = int(np.sum((y == 1) & p)); tn = int(np.sum((y == 0) & ~p))
    fp = int(np.sum((y == 0) & p)); fn = int(np.sum((y == 1) & ~p))
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"threshold": THRESHOLD, "precision": precision, "recall": recall, "f1": f1,
            "TP": tp, "TN": tn, "FP": fp, "FN": fn,
            "confusion_rows_N_V": [[tn, fp], [fn, tp]]}


def interpreter(path: Path):
    obj = tf.lite.Interpreter(model_path=str(path), num_threads=1,
        experimental_op_resolver_type=tf.lite.experimental.OpResolverType.BUILTIN_WITHOUT_DEFAULT_DELEGATES)
    obj.allocate_tensors()
    return obj


def main() -> None:
    inc = np.load(DATA); mit = np.load(MIT); mit_split = np.load(MIT_SPLIT)
    inc_train = np.flatnonzero(inc["split"] == "train")
    val = np.flatnonzero(inc["split"] == "validation")
    X_val = inc["X"][val]; y_val = inc["y"][val]
    model = tf.keras.models.load_model(KERAS, compile=False)
    if model.count_params() != 849: raise RuntimeError("V4 is not the frozen V1 architecture")

    # Fixed, balanced calibration indices from Train only (MIT Train + INCART Train).
    mit_train = mit_split["train_indices"]
    sources = [(mit["X"][mit_train], mit["y"][mit_train]), (inc["X"][inc_train], inc["y"][inc_train])]
    X_train = np.concatenate([item[0] for item in sources]); y_train = np.concatenate([item[1] for item in sources])
    rng = np.random.default_rng(SEED)
    calibration = np.concatenate([rng.choice(np.flatnonzero(y_train == label), 500, replace=False) for label in (0, 1)])
    rng.shuffle(calibration)

    def representative():
        for index in calibration:
            yield [X_train[index:index + 1].astype(np.float32)]

    converter = tf.lite.TFLiteConverter.from_keras_model(model)
    converter.optimizations = [tf.lite.Optimize.DEFAULT]
    converter.representative_dataset = representative
    converter.target_spec.supported_ops = [tf.lite.OpsSet.TFLITE_BUILTINS_INT8]
    converter.inference_input_type = tf.int8
    converter.inference_output_type = tf.int8
    INT8.write_bytes(converter.convert())

    lite = interpreter(INT8)
    inp, out = lite.get_input_details()[0], lite.get_output_details()[0]
    if inp["dtype"] != np.int8 or out["dtype"] != np.int8: raise RuntimeError("Not full INT8 IO")
    in_scale, in_zero = inp["quantization"]; out_scale, out_zero = out["quantization"]
    if in_scale <= 0 or out_scale <= 0: raise RuntimeError("Invalid quantization parameters")
    tensor_types = {np.dtype(t["dtype"]).name for t in lite.get_tensor_details() if t["name"]}
    operators = [op["op_name"] for op in lite._get_ops_details()]

    fp32 = model.predict(X_val, batch_size=256, verbose=0).reshape(-1).astype(np.float32)
    int8_scores = np.empty(len(X_val), np.float32); python_codes = np.empty(len(X_val), np.int8)
    q_inputs = np.empty_like(X_val, dtype=np.int8); clipped = 0
    for index, beat in enumerate(X_val):
        raw = np.rint(beat.astype(np.float64) / in_scale) + in_zero
        clipped += int(np.count_nonzero((raw < -128) | (raw > 127)))
        q = np.clip(raw, -128, 127).astype(np.int8)
        q_inputs[index] = q
        lite.set_tensor(inp["index"], q[None, ...]); lite.invoke()
        code = int(lite.get_tensor(out["index"])[0, 0]); python_codes[index] = code
        int8_scores[index] = (code - out_zero) * out_scale

    q_path = RESULTS / "v4_validation_inputs_int8.bin"
    py_path = RESULTS / "v4_validation_python_codes.bin"
    host_path = RESULTS / "v4_validation_tflm_host_codes.bin"
    q_inputs.tofile(q_path); python_codes.tofile(py_path)
    proc = subprocess.run([str(HOST), str(INT8), str(q_path), str(host_path)],
                          capture_output=True, text=True)
    host_codes = np.fromfile(host_path, dtype=np.int8) if proc.returncode == 0 and host_path.exists() else np.array([], np.int8)
    mismatch = np.flatnonzero(host_codes != python_codes) if host_codes.size == python_codes.size else np.arange(len(python_codes))
    delta = np.abs(fp32 - int8_scores)
    result = {
        "source_model": str(KERAS.relative_to(ROOT)), "source_sha256": sha(KERAS),
        "int8_model": str(INT8.relative_to(ROOT)), "int8_sha256": sha(INT8),
        "bytes": INT8.stat().st_size, "parameters": model.count_params(),
        "calibration": {"source": "MIT-BIH Train + INCART Train only", "samples": len(calibration),
                        "N": 500, "V": 500, "seed": SEED},
        "io": {"input_dtype": np.dtype(inp["dtype"]).name, "output_dtype": np.dtype(out["dtype"]).name,
               "input_scale": float(in_scale), "input_zero": int(in_zero),
               "output_scale": float(out_scale), "output_zero": int(out_zero)},
        "operators": operators, "tensor_dtypes": sorted(tensor_types),
        "validation": {"samples": len(y_val), "FP32": metric(y_val, fp32), "INT8": metric(y_val, int8_scores),
                       "score_mae": float(delta.mean()), "score_max_abs": float(delta.max()),
                       "score_p99_abs": float(np.percentile(delta, 99)),
                       "class_changes_at_0_88": int(np.sum((fp32 >= THRESHOLD) != (int8_scores >= THRESHOLD))),
                       "input_clipped_values": clipped, "input_values": int(X_val.size)},
        "host_parity": {"executable": str(HOST.relative_to(ROOT)), "return_code": proc.returncode,
                        "samples": len(python_codes), "exact_code_matches": int(len(python_codes) - len(mismatch)),
                        "mismatches": int(len(mismatch)), "max_code_delta": int(np.max(np.abs(host_codes.astype(np.int16) - python_codes.astype(np.int16)))) if not len(mismatch) == len(python_codes) else None,
                        "adapter": "V1 Conv/FC single-rounding host adapter exercised with V4 model; not assumed",
                        "stderr": proc.stderr[-1000:]},
        "esp32_compatibility": {"graph_matches_v1_operator_set": set(operators).issubset({"EXPAND_DIMS", "CONV_2D", "RESHAPE", "MAX_POOL_2D", "MEAN", "FULLY_CONNECTED", "LOGISTIC"}),
                                "resolver_operators": ["CONV_2D", "EXPAND_DIMS", "FULLY_CONNECTED", "LOGISTIC", "MAX_POOL_2D", "MEAN", "RESHAPE"],
                                "v1_measured_arena_used_bytes": 6124,
                                "v4_estimated_arena_used_bytes": 6124,
                                "estimate_basis": "identical quantized graph, tensor shapes and dtypes; must confirm AllocateTensors in a future firmware build",
                                "current_firmware_arena_allocated_bytes": 65536,
                                "firmware_modified": False, "board_tested": False},
    }
    REPORT.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
