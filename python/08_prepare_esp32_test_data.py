"""Prepare real Validation fixtures; --audit-only needs only Python stdlib.

Normal run requires the unchanged project .venv. Never uses Test inference.
"""
import argparse
import ast
import hashlib
import importlib
import json
from pathlib import Path
import shutil
import struct
import sys

ROOT = Path(__file__).resolve().parent.parent
PROJECT = ROOT / "firmware/esp32_tinyml_step8"
MODEL = ROOT / "models/ecg_cnn_int8.tflite"
COMMIT = "6368cd2ddebb72e047509ccbc529afc321e804b9"
BASE = f"https://github.com/espressif/esp-tflite-micro/blob/{COMMIT}/"
EXPECTED_OPS = {"CONV_2D": 3, "EXPAND_DIMS": 1, "FULLY_CONNECTED": 4,
                "LOGISTIC": 2, "MAX_POOL_2D": 2, "MEAN": 2, "RESHAPE": 1}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(name, value):
    path = ROOT / "results" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")


class Flat:
    """Read-only subset of TFLite schema, using bounds-checked scalar reads."""
    def __init__(self, data):
        self.data = data

    def read(self, fmt, pos):
        if pos < 0 or pos + struct.calcsize(fmt) > len(self.data):
            raise ValueError("FlatBuffer offset out of range")
        return struct.unpack_from(fmt, self.data, pos)[0]

    def field(self, table, slot):
        vt = table - self.read("<i", table)
        entry = vt + 4 + slot * 2
        off = self.read("<H", entry) if entry + 2 <= vt + self.read("<H", vt) else 0
        return table + off if off else None

    def scalar(self, table, slot, fmt="<I", default=0):
        pos = self.field(table, slot)
        return self.read(fmt, pos) if pos is not None else default

    def ref(self, table, slot):
        pos = self.field(table, slot)
        return pos + self.read("<I", pos) if pos is not None else None

    def vector(self, table, slot, fmt="<i", tables=False):
        pos = self.ref(table, slot)
        if pos is None:
            return []
        size = 4 if tables else struct.calcsize(fmt)
        count = self.read("<I", pos)
        if count > len(self.data) // size:
            raise ValueError("Invalid vector length")
        start = pos + 4
        return [start + i * 4 + self.read("<I", start + i * 4) if tables
                else self.read(fmt, start + i * size) for i in range(count)]

    def string(self, table, slot):
        pos = self.ref(table, slot)
        if pos is None:
            return ""
        size = self.read("<I", pos)
        if pos + 4 + size > len(self.data):
            raise ValueError("Invalid string")
        return self.data[pos + 4:pos + 4 + size].decode("utf-8")


def flatbuffer_audit():
    # Read enum constants from the installed official generated schema, without
    # importing NumPy/TensorFlow or executing that file.
    source = ROOT / ".venv/Lib/site-packages/tensorflow/lite/python/schema_py_generated.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    enums = {}
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name in {"BuiltinOperator", "TensorType"}:
            enums[node.name] = {ast.literal_eval(a.value): a.targets[0].id for a in node.body
                                if isinstance(a, ast.Assign) and isinstance(a.value, ast.Constant)}
    data = MODEL.read_bytes()
    if data[4:8] != b"TFL3":
        raise ValueError("Invalid TFLite identifier")
    f = Flat(data)
    model = f.read("<I", 0)
    graphs = f.vector(model, 2, tables=True)
    if f.scalar(model, 0) != 3 or len(graphs) != 1:
        raise ValueError("Expected schema 3 / single subgraph")
    graph = graphs[0]
    tensors = []
    for i, table in enumerate(f.vector(graph, 0, tables=True)):
        q = f.ref(table, 4)
        tensors.append({"index": i, "name": f.string(table, 3),
            "shape": f.vector(table, 0), "dtype": enums["TensorType"][f.scalar(table, 1, "<b")],
            "scales": f.vector(q, 2, "<f") if q is not None else [],
            "zero_points": f.vector(q, 3, "<q") if q is not None else [],
            "quantized_dimension": f.scalar(q, 6, "<i") if q is not None else 0})
    codes = f.vector(model, 1, tables=True)
    operators = []
    for table in f.vector(graph, 3, tables=True):
        code = codes[f.scalar(table, 0)]
        number = max(f.scalar(code, 0, "<b"), f.scalar(code, 3, "<i"))
        name = enums["BuiltinOperator"][number]
        if name == "CUSTOM":
            raise ValueError("Custom/Flex operators are not supported by this project")
        operators.append({"name": name, "version": f.scalar(code, 2, "<i", 1),
                          "inputs": f.vector(table, 1), "outputs": f.vector(table, 2)})
    actual = {(op["name"], op["version"]) for op in operators}
    expected = set(EXPECTED_OPS.items())
    if actual != expected:
        raise ValueError(f"Actual operator/version set differs from reviewed firmware: {sorted(actual)}")
    io = {name: tensors[f.vector(graph, slot)[0]] for name, slot in (("input", 1), ("output", 2))}
    for name, shape in (("input", [1, 256, 1]), ("output", [1, 1])):
        if io[name]["shape"] != shape or io[name]["dtype"] != "INT8":
            raise ValueError(f"Unexpected {name} shape/dtype")
    return {"model_sha256": sha(MODEL), "model_bytes": len(data), "schema_version": 3,
            "io": io, "operators": operators, "tensors": tensors}


def audit_and_copy():
    audit = flatbuffer_audit()
    dest = PROJECT / "main/model/ecg_cnn_int8.tflite"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and sha(dest) != sha(MODEL):
        raise ValueError("Existing embedded model differs; refusing to overwrite")
    if not dest.exists():
        shutil.copyfile(MODEL, dest)
    assert sha(dest) == sha(MODEL)
    methods = {"CONV_2D": "AddConv2D", "EXPAND_DIMS": "AddExpandDims",
               "FULLY_CONNECTED": "AddFullyConnected", "LOGISTIC": "AddLogistic",
               "MAX_POOL_2D": "AddMaxPool2D", "MEAN": "AddMean", "RESHAPE": "AddReshape"}
    kernels = {"CONV_2D": "esp_nn/conv.cc", "FULLY_CONNECTED": "esp_nn/fully_connected.cc",
               "LOGISTIC": "esp_nn/logistic.cc", "MAX_POOL_2D": "esp_nn/pooling.cc",
               "MEAN": "esp_nn/reduce.cc", "RESHAPE": "reshape.cc", "EXPAND_DIMS": "expand_dims.cc"}
    report_path = ROOT / "results/esp32_operator_compatibility.json"
    previous = json.loads(report_path.read_text(encoding="utf-8")) if report_path.is_file() else {}
    preserved = {key: previous[key] for key in ("pinned_source_evidence", "source_review_note")
                 if key in previous and previous.get("source_commit") == COMMIT}
    save("esp32_operator_compatibility.json", {
        **preserved,
        "component": "espressif/esp-tflite-micro", "version": "1.4.2", "source_commit": COMMIT,
        "status": "NEEDS_VERIFICATION", "flatbuffer": audit,
        "resolver_api_source": BASE + "tensorflow/lite/micro/micro_mutable_op_resolver.h",
        "operators": [{"name": name, "version": version, "registration": methods[name],
            "registration_api_checked": True, "kernel_source": BASE + "tensorflow/lite/micro/kernels/" + kernels[name],
            "status": "NEEDS_VERIFICATION",
            "reason": "Registration API checked at pinned commit; exact INT8 shape/quantization constraints and operator-version behavior require AllocateTensors/Invoke on this target."}
            for name, version in sorted(EXPECTED_OPS.items())]})
    return audit


def prepare():
    audit = audit_and_copy()
    c = importlib.import_module("07_convert_tinyml")
    c.dependencies()
    np = c.np
    X, y, ids, parts, threshold, hashes = c.load_inputs()
    if threshold != 0.52:
        raise ValueError("Step 8 requires the official threshold to remain 0.52")
    validation = parts["validation"]
    instance, inp, out, info = c.interpreter(c.INT8, True)
    scores, codes = [], []
    for number, index in enumerate(validation):
        q = np.clip(np.rint(X[index:index+1].astype(np.float64) / info["input_scale"])
                    + info["input_zero_point"], -128, 127).astype(np.int8)
        instance.set_tensor(inp["index"], q)
        instance.invoke()
        code = int(instance.get_tensor(out["index"])[0, 0])
        codes.append(code)
        scores.append((code - info["output_zero_point"]) * info["output_scale"])
        if (number + 1) % 2000 == 0:
            print(f"Validation fixture selection: {number + 1}/{len(validation)}", flush=True)
    scores = np.asarray(scores)
    c.check_scores(scores, len(validation))
    predicted = scores >= threshold
    rng = np.random.default_rng(42)
    chosen = []
    def add(value):
        if int(value) not in chosen:
            chosen.append(int(value))
    for label in (0, 1):
        for prediction in (False, True):
            eligible = np.flatnonzero((y[validation] == label) & (predicted == prediction))
            if len(eligible):
                add(rng.choice(eligible))
    for value in np.argsort(np.abs(scores - threshold), kind="stable")[:2]:
        add(value)
    for value in rng.permutation(len(validation)):
        if len(chosen) >= 12:
            break
        add(value)
    samples, payload = [], bytearray()
    for sample_id, local in enumerate(chosen):
        index = int(validation[local])
        q = np.clip(np.rint(X[index].astype(np.float64) / info["input_scale"])
                    + info["input_zero_point"], -128, 127).astype(np.int8)
        payload.extend(q.tobytes(order="C"))
        samples.append({"sample_id": sample_id, "dataset_index": index, "record_id": str(ids[index]),
                        "true_label": int(y[index]), "python_output_int8": codes[local],
                        "python_score": float(scores[local]), "python_predicted": int(predicted[local])})
    test_dir = PROJECT / "main/test_data"
    test_dir.mkdir(parents=True, exist_ok=True)
    binary = test_dir / "ecg_test_samples_int8.bin"
    binary.write_bytes(payload)
    sample_sha = sha(binary)
    lines = ["// Generated from real saved Validation data. Do not edit.", "#pragma once",
             "#include <cstdint>", "#include <cstddef>",
             f"constexpr size_t kSampleCount = {len(samples)};", "constexpr size_t kSamplesPerBeat = 256;",
             f"constexpr size_t kModelBytes = {audit['model_bytes']};", "constexpr float kThreshold = 0.52f;",
             f"constexpr float kInputScale = {info['input_scale']:.17g}f;",
             f"constexpr int kInputZero = {info['input_zero_point']};",
             f"constexpr float kOutputScale = {info['output_scale']:.17g}f;",
             f"constexpr int kOutputZero = {info['output_zero_point']};",
             f'constexpr char kModelSha[] = "{audit["model_sha256"]}";',
             f'constexpr char kSamplesSha[] = "{sample_sha}";',
             "struct Golden { int dataset_index; const char* record; int label; int output; float score; int predicted; };",
             "constexpr Golden kGolden[kSampleCount] = {"]
    for item in samples:
        lines.append(f'  {{{item["dataset_index"]}, "{item["record_id"]}", {item["true_label"]}, {item["python_output_int8"]}, {item["python_score"]:.9f}f, {item["python_predicted"]}}},')
    lines.append("};\n")
    (test_dir / "ecg_test_metadata.h").write_text("\n".join(lines), encoding="utf-8")
    save("esp32_golden_outputs.json", {"status": "PYTHON_GOLDEN_CREATED_HARDWARE_NOT_TESTED",
         "seed": 42, "source": "Validation only", "threshold": threshold, "model_sha256": sha(MODEL),
         "samples_sha256": sample_sha, "sample_count": len(samples), "bytes_per_sample": 256,
         "layout": "Consecutive 256 signed INT8 bytes per sample, row-major (1,256,1); no multi-byte fields or endianness conversion",
         "selection": "Seeded label/prediction coverage, two nearest-threshold samples, random fill; not threshold selection",
         "quantization": info, "samples": samples, "input_binary": str(binary), "provenance": hashes})
    assert binary.stat().st_size == 256 * len(samples)
    print(f"Prepared {len(samples)} real Validation samples; model SHA verified. No ESP32 execution.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit-only", action="store_true")
    args = parser.parse_args()
    try:
        if args.audit_only:
            print(json.dumps(audit_and_copy()["io"], indent=2))
        else:
            prepare()
    except Exception as error:
        print(f"ERROR: {type(error).__name__}: {error}", file=sys.stderr)
        sys.exit(1)
