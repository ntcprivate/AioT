"""Step 7: compare already converted models on saved Validation samples only.

Run after conversion: .venv/Scripts/python.exe python/07_compare_models.py
07_convert_tinyml.py also invokes this comparison automatically.
"""

import importlib
import json
import sys
import traceback


def metrics(truth, scores, threshold, np):
    from sklearn.metrics import (accuracy_score, average_precision_score,
                                 confusion_matrix, f1_score, precision_score,
                                 recall_score, roc_auc_score)
    prediction = (scores >= threshold).astype(np.int32)
    tn, fp, fn, tp = [int(v) for v in confusion_matrix(truth, prediction, labels=[0, 1]).ravel()]
    return {"accuracy": float(accuracy_score(truth, prediction)),
            "precision": float(precision_score(truth, prediction, zero_division=0)),
            "recall": float(recall_score(truth, prediction, zero_division=0)),
            "specificity": tn / (tn + fp),
            "f1": float(f1_score(truth, prediction, zero_division=0)),
            "TP": tp, "TN": tn, "FP": fp, "FN": fn,
            "roc_auc": float(roc_auc_score(truth, scores)),
            "average_precision": float(average_precision_score(truth, scores))}


def differences(reference, other, threshold, np):
    delta = other.astype(np.float64) - reference.astype(np.float64)
    original, converted = reference >= threshold, other >= threshold
    correlation = (float(np.corrcoef(reference, other)[0, 1])
                   if reference.std() > 0 and other.std() > 0 else None)
    if correlation is not None and not np.isfinite(correlation):
        correlation = None
    return {"mean_absolute_error": float(np.mean(np.abs(delta))),
            "max_absolute_error": float(np.max(np.abs(delta))),
            "rmse": float(np.sqrt(np.mean(delta ** 2))),
            "pearson_correlation": correlation,
            "changed_predictions": int(np.count_nonzero(original != converted)),
            "normal_to_pvc": int(np.count_nonzero(~original & converted)),
            "pvc_to_normal": int(np.count_nonzero(original & ~converted))}


def plots(c, all_metrics, all_scores, sizes, threshold):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    np = c.np
    c.PLOTS.mkdir(parents=True, exist_ok=True)
    names = list(all_metrics)
    fig, ax = plt.subplots(figsize=(11, 5))
    positions = np.arange(4)
    keys = ["precision", "recall", "f1", "accuracy"]
    for i, name in enumerate(names):
        bars = ax.bar(positions + (i - 1) * 0.25, [all_metrics[name][k] for k in keys],
                      width=0.25, label=name)
        ax.bar_label(bars, fmt="%.3f", fontsize=8)
    ax.set_xticks(positions, ["Precision", "Recall", "F1", "Accuracy"])
    ax.set(ylim=(0, 1.12), ylabel="Validation metric",
           title=f"Validation only - fixed threshold {threshold:.2f}")
    ax.legend()
    fig.tight_layout()
    fig.savefig(c.PLOTS / "tinyml_model_comparison.png", dpi=150)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(9, 5))
    bars = ax.bar(list(sizes), [item["KiB"] for item in sizes.values()], color=["gray", "steelblue", "tomato"])
    ax.bar_label(bars, fmt="%.2f KiB", padding=3)
    ax.set(ylabel="File size (KiB)", title="Actual model files (not inference RAM)")
    ax.margins(y=0.2)
    fig.tight_layout()
    fig.savefig(c.PLOTS / "tinyml_size_comparison.png", dpi=150)
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    for ax, name in zip(axes, ["TFLite Float32", "TFLite INT8"]):
        ax.scatter(all_scores["Keras Float32"], all_scores[name], s=5, alpha=0.15)
        ax.plot([0, 1], [0, 1], color="gray", linestyle=":", label="Equal score")
        ax.axvline(threshold, color="red", linestyle="--", label=f"Threshold {threshold:.2f}")
        ax.axhline(threshold, color="red", linestyle="--")
        ax.set(xlabel="Keras sigmoid score", ylabel=f"{name} score", title=f"Validation - {name}")
        ax.legend()
    fig.tight_layout()
    fig.savefig(c.PLOTS / "tinyml_output_difference.png", dpi=150)
    plt.close(fig)


def run():
    c = importlib.import_module("07_convert_tinyml")
    c.dependencies()
    np = c.np
    X, y, ids, parts, threshold, hashes = c.load_inputs()
    report = json.loads(c.REPORT.read_text(encoding="utf-8"))
    for key, value in hashes.items():
        if report.get(key) != value:
            raise ValueError(f"Conversion report provenance mismatch: {key}")
    if (report.get("threshold_sha256") != c.sha256(c.THRESHOLD_FILE)
            or report.get("original_threshold") != threshold):
        raise ValueError("Threshold config differs from conversion report")
    sizes = c.file_sizes()
    for name, details in sizes.items():
        previous = report.get("model_file_sizes", {}).get(name, {})
        if previous.get("sha256") != details["sha256"]:
            raise ValueError(f"Converted file differs from report: {name}")
    representative = np.asarray(report["representative_dataset"]["indices"])
    if (representative.ndim != 1 or representative.dtype.kind not in "iu"
            or not len(representative) or len(np.unique(representative)) != len(representative)
            or not np.isin(representative, parts["train"]).all()
            or set(np.unique(y[representative])) != {0, 1}):
        raise ValueError("Reported calibration indices are not valid Train-only samples")
    report["float32_flatbuffer"] = c.inspect_flatbuffer(c.FLOAT)
    report["int8_flatbuffer"] = c.inspect_flatbuffer(c.INT8, int8=True)
    model = c.load_keras()
    validation_indices = parts["validation"]
    X_validation, truth = X[validation_indices], y[validation_indices]
    # No Test data is passed to any inference function.
    keras_scores = model.predict(X_validation, batch_size=64, verbose=0)
    if keras_scores.shape != (len(truth), 1):
        raise ValueError("Unexpected Keras prediction shape")
    keras_scores = keras_scores[:, 0]
    c.check_scores(keras_scores, len(truth))
    float_scores, float_info = c.predict_tflite(c.FLOAT, X_validation, integer=False)
    int8_scores, int8_info = c.predict_tflite(c.INT8, X_validation, integer=True)
    all_scores = {"Keras Float32": keras_scores, "TFLite Float32": float_scores, "TFLite INT8": int8_scores}
    all_metrics = {name: metrics(truth, scores, threshold, np) for name, scores in all_scores.items()}
    output_differences = {name: differences(keras_scores, scores, threshold, np)
                          for name, scores in all_scores.items() if name != "Keras Float32"}
    output_differences["INT8 versus TFLite Float32"] = differences(float_scores, int8_scores, threshold, np)
    # Near-threshold width is descriptive only; it does not tune the threshold.
    near = np.flatnonzero(np.abs(keras_scores - threshold) <= 0.05)
    nearest = np.argsort(np.abs(keras_scores - threshold), kind="stable")[:20]
    flips = np.flatnonzero((keras_scores >= threshold) != (int8_scores >= threshold))
    def sample_details(local):
        return {"dataset_index": int(validation_indices[local]), "record_id": str(ids[validation_indices[local]]),
                "label": int(truth[local]),
                "scores": {name: float(scores[local]) for name, scores in all_scores.items()}}
    near_analysis = {"keras_threshold_distance": 0.05, "count": len(near),
                     "int8_label_flips_near_threshold": int(np.count_nonzero(
                         (keras_scores[near] >= threshold) != (int8_scores[near] >= threshold))),
                     "nearest_20_samples": [sample_details(i) for i in nearest],
                     "first_20_int8_label_flips": [sample_details(i) for i in flips[:20]]}
    quality_delta = {key: all_metrics["TFLite INT8"][key] - all_metrics["Keras Float32"][key]
                     for key in ("precision", "recall", "f1", "accuracy")}
    warnings = []
    if all_metrics["TFLite INT8"]["recall"] < 0.9:
        warnings.append("INT8 Validation recall < 90%; review before hardware testing. Threshold is unchanged.")
    for key in ("precision", "recall", "f1"):
        if quality_delta[key] < -0.01:
            warnings.append(f"INT8 {key} dropped by more than 1 percentage point (descriptive warning criterion).")
    if output_differences["TFLite Float32"]["max_absolute_error"] > 1e-5:
        warnings.append("Float32 conversion max score difference > 1e-5; inspect conversion separately from INT8 quantization.")
    if int8_info["validation_input_clipped_values"]:
        warnings.append("Some Validation input values saturate INT8 range; clipping statistics are recorded. No recalibration using Validation performed.")
    sizes = c.file_sizes()
    reduction = 100 * (1 - sizes[c.INT8.name]["bytes"] / sizes[c.FLOAT.name]["bytes"])
    plots(c, all_metrics, all_scores, sizes, threshold)
    if c.sha256(c.KERAS) != hashes["model_sha256"]:
        raise ValueError("Source Keras model changed during comparison")
    report.update(status="CONVERSION_AND_VALIDATION_COMPLETED", model_file_sizes=sizes,
                  float32_io=float_info, int8_io=int8_info,
                  validation_samples=len(truth), validation_N=int(np.count_nonzero(truth == 0)),
                  validation_V=int(np.count_nonzero(truth == 1)),
                  validation_metrics=all_metrics, output_difference_metrics=output_differences,
                  near_threshold_analysis=near_analysis, int8_minus_keras_metrics=quality_delta,
                  size_reduction_float32_tflite_to_int8_percent=reduction,
                  warnings=warnings, quality_warning_drop_absolute=0.01,
                  evaluation_note="Validation comparison only; Validation previously selected the threshold. Not a new independent Test assessment.",
                  memory_note="File bytes include FlatBuffer metadata/weights/constants. Logical tensor bytes exclude lifetime reuse, scratch buffers, alignment, kernels and firmware; do not infer tensor arena or ESP32 RAM from them.")
    report.pop("error", None)
    report.pop("failed_stage", None)
    c.write_report(report)
    op_list = sorted({f"{op['name']} v{op['version']}" for op in report["int8_flatbuffer"]["operators"]})
    summary = ["Step 7: conversion and desktop Validation comparison completed.",
               f"Source CNN parameters: {model.count_params()}",
               f"Threshold: {threshold:.2f} (unchanged, read from optimized_threshold.json)",
               f"INT8 size: {sizes[c.INT8.name]['bytes']} bytes ({sizes[c.INT8.name]['KiB']:.2f} KiB)",
               f"File-size reduction versus TFLite Float32: {reduction:.2f}%",
               f"INT8 learned weight buffers: {report['int8_flatbuffer']['learned_weight_buffer_bytes']} bytes; bias buffers: {report['int8_flatbuffer']['bias_buffer_bytes']} bytes (not the whole file or RAM)",
               "Validation only; no Test inference, calibration or selection.",
               "Model                     Accuracy  Precision Recall    F1"]
    for name, values in all_metrics.items():
        summary.append(f"{name:25s} {values['accuracy']:.6f}  {values['precision']:.6f}  {values['recall']:.6f}  {values['f1']:.6f}")
    summary.extend(["Actual INT8 operators: " + ", ".join(op_list),
                    "TFLM/esp-tflite-micro: NEEDS_VERIFICATION for pinned kernel/operator versions.",
                    "ESP32 tensor arena, RAM, latency and firmware flash: NOT MEASURED.",
                    "Smaller files do not establish better PVC detection.",
                    "Step 8 readiness: desktop checks completed; hardware measurements and kernel compatibility still required."
                    if not warnings else "Step 8 readiness: review warnings before any hardware experiment; no automatic changes made."])
    summary.extend("WARNING: " + warning for warning in warnings)
    c.SUMMARY.write_text("\n".join(summary) + "\n", encoding="utf-8")
    outputs = [c.FLOAT, c.INT8, c.REPORT, c.SUMMARY] + [c.PLOTS / name for name in (
        "tinyml_model_comparison.png", "tinyml_size_comparison.png", "tinyml_output_difference.png")]
    for path in outputs:
        if not path.is_file() or not path.stat().st_size:
            raise OSError(f"Missing or empty output: {path}")
    print("\n".join(summary))
    print("\nIO quantization:", json.dumps(int8_info, indent=2))
    print("\nOutput differences:", json.dumps(output_differences, indent=2))
    for name, values in sizes.items():
        print(f"{name}: {values['bytes']} bytes / {values['KB']:.3f} KB / {values['KiB']:.3f} KiB")
    for path in outputs:
        print("Verified output:", path)


if __name__ == "__main__":
    try:
        run()
    except Exception:
        traceback.print_exc()
        print("Comparison incomplete; existing outputs may be partial or from an earlier run.", file=sys.stderr)
        sys.exit(1)
