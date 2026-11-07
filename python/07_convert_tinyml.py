"""Step 7: convert the existing CNN and run Validation-only comparisons.

Run: .venv/Scripts/python.exe python/07_convert_tinyml.py
No training, Test inference, threshold tuning or ESP32 firmware operations.
"""

from collections import Counter
import hashlib
import importlib
import json
from pathlib import Path
import sys
import traceback

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data/processed/mitbih_nv_250hz.npz"
SPLIT = DATA.with_name("mitbih_split_indices.npz")
THRESHOLD_FILE = ROOT / "results/optimized_threshold.json"
KERAS = ROOT / "models/ecg_cnn_best.keras"
FLOAT = KERAS.with_name("ecg_cnn_float32.tflite")
INT8 = KERAS.with_name("ecg_cnn_int8.tflite")
REPORT = ROOT / "results/tinyml_conversion_report.json"
SUMMARY = REPORT.with_name("tinyml_conversion_summary.txt")
PLOTS = ROOT / "plots"
SEED = 42


def dependencies():
    global np, tf, schema
    import numpy as np
    import tensorflow as tf
    # Bundled schema exposes the actual FlatBuffer operator versions/tensors.
    from tensorflow.lite.python import schema_py_generated as schema


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_report(report):
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False),
                      encoding="utf-8")


def load_inputs():
    config = json.loads(THRESHOLD_FILE.read_text(encoding="utf-8"))
    threshold = config.get("selected_threshold")
    if isinstance(threshold, bool) or not isinstance(threshold, (int, float)):
        raise ValueError("optimized_threshold.json: selected_threshold must be numeric")
    if not np.isfinite(threshold) or not 0 < threshold < 1:
        raise ValueError("Invalid selected_threshold; no hardcoded fallback")
    with np.load(DATA, allow_pickle=False) as saved:
        X, y, raw_ids = saved["X"], saved["y"], saved["record_ids"]
    if (y.ndim != 1 or X.shape != (len(y), 256, 1) or raw_ids.shape != y.shape
            or X.dtype != np.float32 or y.dtype != np.int32):
        raise ValueError("Expected X float32 (N,256,1), y int32 (N,), record_ids (N,)")
    if not len(y) or not np.isfinite(X).all() or not np.isin(y, [0, 1]).all():
        raise ValueError("Empty dataset, NaN/Inf, or labels outside 0/1")
    if raw_ids.dtype.kind not in "USiu":
        raise ValueError("Invalid record_ids dtype")
    ids = raw_ids.astype("U")
    if any(len(r) != 3 or not r.isdigit() for r in np.unique(ids)):
        raise ValueError("Expected three-digit MIT-BIH record IDs")
    hashes = {"dataset_sha256": sha256(DATA), "split_sha256": sha256(SPLIT),
              "model_sha256": sha256(KERAS)}
    for key, actual in hashes.items():
        if config.get(key) and config[key] != actual:
            raise ValueError(f"{key} differs from threshold provenance")
    with np.load(SPLIT, allow_pickle=False) as saved:
        print("Actual split keys:", saved.files)
        parts = {name: saved[f"{name}_indices"] for name in ("train", "validation", "test")}
        if ("dataset_sha256" in saved.files
                and saved["dataset_sha256"].item() != hashes["dataset_sha256"]):
            raise ValueError("Split dataset fingerprint mismatch")
    for name, index in parts.items():
        if (index.ndim != 1 or index.dtype.kind not in "iu" or not len(index)
                or np.any(index < 0) or np.any(index >= len(y))
                or len(np.unique(index)) != len(index)):
            raise ValueError(f"Invalid {name} sample indices")
        if set(np.unique(y[index])) != {0, 1}:
            raise ValueError(f"{name} must contain both N and V")
    if not np.array_equal(np.sort(np.concatenate(list(parts.values()))), np.arange(len(y))):
        raise ValueError("Saved splits do not partition the dataset exactly once")
    groups = np.asarray(["patient_201_202" if r in {"201", "202"} else f"record_{r}" for r in ids])
    for i, a in enumerate(parts):
        for b in list(parts)[i + 1:]:
            if (set(ids[parts[a]]) & set(ids[parts[b]])
                    or set(groups[parts[a]]) & set(groups[parts[b]])):
                raise ValueError(f"Record/known patient overlap: {a}/{b}")
    return X, y, ids, parts, float(threshold), hashes


def load_keras():
    model = tf.keras.models.load_model(KERAS, compile=False)
    if (model.count_params() != 849 or tuple(model.input_shape) != (None, 256, 1)
            or tuple(model.output_shape) != (None, 1)):
        raise ValueError("Source model must have 849 parameters and shapes (None,256,1)/(None,1)")
    if getattr(model.layers[-1].activation, "__name__", "") != "sigmoid":
        raise ValueError("Expected sigmoid output")
    return model


def check_scores(scores, count):
    if scores.shape != (count,) or not np.isfinite(scores).all():
        raise ValueError("Wrong prediction count/shape or nonfinite scores")
    if np.any((scores < -1e-6) | (scores > 1 + 1e-6)):
        raise ValueError("Sigmoid/dequantized scores outside [0,1]")


def representative_indices(X, y, ids, train, size=600):
    """Train-only strata: record, class and within-stratum peak-to-peak quartile.

    One observed sample per stratum when possible, then proportional random
    coverage of remaining Train samples. No transforms or synthetic signals.
    """
    size = min(size, len(train))
    if size < 2:
        raise ValueError("Insufficient Train calibration data")
    rng = np.random.default_rng(SEED)
    buckets = []
    amplitudes = np.ptp(X[train, :, 0], axis=1)
    for record_id in np.unique(ids[train]):
        for label in (0, 1):
            local = np.flatnonzero((ids[train] == record_id) & (y[train] == label))
            if not len(local):
                continue
            bins = np.searchsorted(np.quantile(amplitudes[local], [0.25, 0.5, 0.75]),
                                   amplitudes[local], side="right")
            for bin_id in np.unique(bins):
                buckets.append(train[local[bins == bin_id]])
    if len(buckets) > size:
        raise ValueError("Representative size too small to cover all Train strata")
    chosen = [int(rng.choice(bucket)) for bucket in buckets]
    remaining = np.setdiff1d(train, chosen)
    chosen.extend(rng.choice(remaining, size=size - len(chosen), replace=False).tolist())
    result = np.asarray(chosen, dtype=np.int64)
    rng.shuffle(result)
    if set(np.unique(y[result])) != {0, 1} or not np.isin(result, train).all():
        raise ValueError("Calibration must contain both classes and only Train indices")
    return result


def enum_names(enum):
    return {value: name for name, value in vars(enum).items()
            if isinstance(value, int) and not name.startswith("_")}


def inspect_flatbuffer(path, int8=False):
    content = path.read_bytes()
    if len(content) < 8 or content[4:8] != b"TFL3":
        raise ValueError(f"Not a TFLite FlatBuffer: {path}")
    model = schema.Model.GetRootAsModel(content, 0)
    if model.Version() != 3:
        raise ValueError(f"Unexpected TFLite schema version {model.Version()}")
    if model.SubgraphsLength() != 1:
        raise ValueError("This CNN audit expects one subgraph")
    graph = model.Subgraphs(0)
    op_names, type_names = enum_names(schema.BuiltinOperator), enum_names(schema.TensorType)
    tensors = []
    for i in range(graph.TensorsLength()):
        tensor = graph.Tensors(i)
        dtype = type_names.get(tensor.Type(), f"UNKNOWN_{tensor.Type()}")
        shape = [tensor.Shape(j) for j in range(tensor.ShapeLength())]
        q = tensor.Quantization()
        scales = [q.Scale(j) for j in range(q.ScaleLength())] if q else []
        zeros = [q.ZeroPoint(j) for j in range(q.ZeroPointLength())] if q else []
        if scales and (not np.isfinite(scales).all() or any(s <= 0 for s in scales)):
            raise ValueError(f"Invalid quantization scales: tensor {i}")
        if len(scales) != len(zeros):
            raise ValueError(f"Quantization scale/zero-point length mismatch: tensor {i}")
        dimension = q.QuantizedDimension() if q else 0
        if len(scales) > 1 and (dimension < 0 or dimension >= len(shape)
                                or len(scales) != shape[dimension]):
            raise ValueError(f"Invalid per-channel quantization: tensor {i}")
        if dtype == "INT8" and (not scales or any(z < -128 or z > 127 for z in zeros)):
            raise ValueError(f"Invalid INT8 tensor quantization: tensor {i}")
        if dtype == "INT32" and scales and any(z != 0 for z in zeros):
            raise ValueError(f"Nonzero INT32 bias zero point: tensor {i}")
        if int8 and dtype not in {"INT8", "INT32", "INT64", "BOOL"}:
            raise ValueError(f"Non-integer/unsupported tensor {i}: {dtype}; refusing hybrid model")
        buffer_bytes = model.Buffers(tensor.Buffer()).DataLength()
        widths = {"INT8": 1, "INT32": 4, "INT64": 8, "BOOL": 1, "FLOAT32": 4}
        tensors.append({"index": i, "name": tensor.Name().decode("utf-8", errors="replace"),
                        "shape": shape, "dtype": dtype, "buffer_index": tensor.Buffer(),
                        "constant_buffer_bytes": buffer_bytes,
                        "logical_tensor_bytes": int(np.prod(shape)) * widths.get(dtype, 0),
                        "scales": scales, "zero_points": zeros, "quantized_dimension": dimension})
    operators = []
    for i in range(graph.OperatorsLength()):
        operator = graph.Operators(i)
        code = model.OperatorCodes(operator.OpcodeIndex())
        builtin = max(code.BuiltinCode(), code.DeprecatedBuiltinCode())
        name = op_names.get(builtin, f"UNKNOWN_{builtin}")
        if name == "CUSTOM" or code.CustomCode() or name.startswith(("Flex", "UNKNOWN")):
            raise ValueError(f"Custom/Flex/unknown op not permitted: {name}")
        if code.Version() < 1:
            raise ValueError(f"Invalid operator version for {name}: {code.Version()}")
        operators.append({"index": i, "name": name, "version": code.Version(),
                          "inputs": [operator.Inputs(j) for j in range(operator.InputsLength())],
                          "outputs": [operator.Outputs(j) for j in range(operator.OutputsLength())],
                          "tflm_status": "NEEDS_VERIFICATION"})
    buffers = {t["buffer_index"]: t["constant_buffer_bytes"] for t in tensors}
    weight_buffers, bias_buffers = set(), set()
    for operator in operators:
        if operator["name"] in {"CONV_2D", "DEPTHWISE_CONV_2D", "FULLY_CONNECTED"}:
            for position, destination in ((1, weight_buffers), (2, bias_buffers)):
                if len(operator["inputs"]) > position and operator["inputs"][position] >= 0:
                    destination.add(tensors[operator["inputs"][position]]["buffer_index"])
    return {"schema_version": model.Version(), "operators": operators, "tensors": tensors,
            "input_indices": [graph.Inputs(i) for i in range(graph.InputsLength())],
            "output_indices": [graph.Outputs(i) for i in range(graph.OutputsLength())],
            "constant_tensor_buffer_bytes": sum(buffers.values()),
            "learned_weight_buffer_bytes": sum(buffers[index] for index in weight_buffers),
            "bias_buffer_bytes": sum(buffers[index] for index in bias_buffers),
            "memory_note": "Constant tensor buffers include weights, biases and shape constants; not total file size or tensor arena."}


def io_quantization(detail):
    q = detail["quantization_parameters"]
    scales, zeros = q["scales"], q["zero_points"]
    if (len(scales) != 1 or len(zeros) != 1 or not np.isfinite(scales).all()
            or scales[0] <= 0 or not -128 <= int(zeros[0]) <= 127):
        raise ValueError("Expected valid per-tensor INT8 IO quantization")
    return float(scales[0]), int(zeros[0])


def interpreter(path, integer):
    instance = tf.lite.Interpreter(model_path=str(path), num_threads=1,
        experimental_op_resolver_type=tf.lite.experimental.OpResolverType.BUILTIN_WITHOUT_DEFAULT_DELEGATES)
    instance.allocate_tensors()
    inputs, outputs = instance.get_input_details(), instance.get_output_details()
    if len(inputs) != 1 or len(outputs) != 1:
        raise ValueError("Expected one input and one output")
    a, b = inputs[0], outputs[0]
    dtype = np.int8 if integer else np.float32
    if (tuple(a["shape"]) != (1, 256, 1) or tuple(b["shape"]) != (1, 1)
            or a["dtype"] != dtype or b["dtype"] != dtype):
        raise ValueError(f"Unexpected TFLite IO shape/dtype: {a}, {b}")
    info = {"input_shape": a["shape"].tolist(), "output_shape": b["shape"].tolist(),
            "input_dtype": np.dtype(a["dtype"]).name, "output_dtype": np.dtype(b["dtype"]).name}
    if integer:
        si, zi = io_quantization(a)
        so, zo = io_quantization(b)
        info.update(input_scale=si, input_zero_point=zi, output_scale=so, output_zero_point=zo)
    return instance, a, b, info


def predict_tflite(path, X_validation, integer):
    instance, a, b, info = interpreter(path, integer)
    scores = np.empty(len(X_validation), dtype=np.float32)
    clipped = 0
    for i, beat in enumerate(X_validation):
        value = beat[np.newaxis, ...]
        if integer:
            # np.rint is vectorized round-to-nearest, ties-to-even.
            q = np.rint(value.astype(np.float64) / info["input_scale"]) + info["input_zero_point"]
            clipped += int(np.count_nonzero((q < -128) | (q > 127)))
            value = np.clip(q, -128, 127).astype(np.int8)
        instance.set_tensor(a["index"], value)
        instance.invoke()
        result = instance.get_tensor(b["index"])
        scores[i] = ((int(result[0, 0]) - info["output_zero_point"]) * info["output_scale"]
                     if integer else float(result[0, 0]))
        if (i + 1) % 2000 == 0:
            print(f"{path.name}: {i + 1}/{len(X_validation)}", flush=True)
    check_scores(scores, len(X_validation))
    if integer:
        info["validation_input_clipped_values"] = clipped
        info["validation_input_clipped_fraction"] = clipped / X_validation.size
    return scores, info


def file_sizes():
    return {path.name: {"bytes": path.stat().st_size, "KB": path.stat().st_size / 1000,
                        "KiB": path.stat().st_size / 1024, "sha256": sha256(path)}
            for path in (KERAS, FLOAT, INT8)}


def main():
    dependencies()
    X, y, ids, parts, threshold, hashes = load_inputs()
    model = load_keras()
    probe = np.asarray(model(X[parts["validation"][:1]], training=False)).reshape(-1)
    check_scores(probe, 1)
    representative = representative_indices(X, y, ids, parts["train"])
    counts = dict(Counter(int(value) for value in y[representative]))
    print(f"Representative dataset: {len(representative)} Train beats; N/V={counts}")
    KERAS.parent.mkdir(parents=True, exist_ok=True)
    stage = "float32 conversion"
    report = {"status": "IN_PROGRESS", "tensorflow_version": tf.__version__,
              "source_model": str(KERAS), **hashes,
              "model_parameter_count": model.count_params(),
              "input_shape": list(model.input_shape), "output_shape": list(model.output_shape),
              "class_mapping": {"0": "Normal", "1": "PVC"},
              "original_threshold": threshold, "threshold_source": str(THRESHOLD_FILE),
              "threshold_sha256": sha256(THRESHOLD_FILE),
              "preprocessing": {"sampling_rate_hz": 250, "source_rate_hz": 360,
                                "resample_ratio": "25/36", "window": [128, 128],
                                "normalization": "per-beat z-score, denominator=max(std,1e-8)",
                                "new_transforms": False},
              "representative_dataset": {"size": len(representative), "class_counts": counts,
                  "seed": SEED, "source": "Train only", "indices": representative.tolist(),
                  "records": sorted(set(ids[representative])),
                  "method": "record/class/Train peak-to-peak quartile coverage, then random remaining Train samples; morphology coverage is a proxy, not guaranteed"},
              "test_inference_performed": False,
              "quantization_settings": {"optimization": "DEFAULT", "ops": "TFLITE_BUILTINS_INT8",
                                        "input": "int8", "output": "int8", "float_fallback": False},
              "tflm_compatibility": {"status": "NEEDS_VERIFICATION",
                  "reason": "No pinned local esp-tflite-micro/TFLM kernel build or ESP32 execution verified. Desktop success cannot certify operator versions or hardware compatibility.",
                  "sources": ["https://github.com/espressif/esp-tflite-micro",
                              "https://github.com/tensorflow/tflite-micro",
                              "https://github.com/tensorflow/tflite-micro/blob/main/tensorflow/lite/micro/micro_mutable_op_resolver.h"]},
              "esp32_measurements": {"tensor_arena": "NOT_MEASURED", "inference_ram": "NOT_MEASURED",
                                     "latency": "NOT_MEASURED", "firmware_flash": "NOT_MEASURED"}}
    try:
        converter = tf.lite.TFLiteConverter.from_keras_model(model)
        converter.target_spec.supported_ops = [tf.lite.OpsSet.TFLITE_BUILTINS]
        FLOAT.write_bytes(converter.convert())
        report["float32_flatbuffer"] = inspect_flatbuffer(FLOAT)
        interpreter(FLOAT, False)
        stage = "fully INT8 conversion"
        converter = tf.lite.TFLiteConverter.from_keras_model(model)
        converter.optimizations = [tf.lite.Optimize.DEFAULT]
        def representative_dataset():
            for index in representative:
                yield [X[index:index + 1].astype(np.float32, copy=False)]
        converter.representative_dataset = representative_dataset
        converter.target_spec.supported_ops = [tf.lite.OpsSet.TFLITE_BUILTINS_INT8]
        converter.inference_input_type = tf.int8
        converter.inference_output_type = tf.int8
        INT8.write_bytes(converter.convert())
        report["int8_flatbuffer"] = inspect_flatbuffer(INT8, int8=True)
        _, _, _, report["int8_io"] = interpreter(INT8, True)
        if sha256(KERAS) != hashes["model_sha256"]:
            raise ValueError("Source Keras file changed")
        report["model_file_sizes"] = file_sizes()
        report["status"] = "CONVERTED_VALIDATION_PENDING"
        write_report(report)
        stage = "Validation comparison"
        comparison = importlib.import_module("07_compare_models")
        comparison.run()
    except Exception as error:
        report.update(status="FAILED_OR_PARTIAL", failed_stage=stage,
                      error=f"{type(error).__name__}: {error}")
        write_report(report)
        SUMMARY.write_text(f"Step 7 incomplete. Stage: {stage}\n{type(error).__name__}: {error}\n"
                           "Files from earlier stages may exist; do not treat them as verified outputs.\n",
                           encoding="utf-8")
        raise


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        print("Step 7 did not finish. No environment repair or model fallback attempted.", file=sys.stderr)
        sys.exit(1)
