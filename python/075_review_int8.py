"""Step 7.5: exploratory INT8 threshold review using saved Validation only.

Run: .venv/Scripts/python.exe python/075_review_int8.py
Only the four Step 7.5 outputs are written. No training or Test inference.
Threshold ties refer to the finite candidate grid documented in the JSON.
"""

from fractions import Fraction
import csv
import importlib
import json
import sys
import traceback


REFERENCE_THRESHOLD = 0.52  # Requested comparison, not an official config update.
OUTPUT_NAMES = ("int8_threshold_review.csv", "int8_record_review.csv",
                "int8_threshold_recommendation.json")


def counts_metrics(threshold, tp, tn, fp, fn):
    def divide(a, b, empty=0.0):
        return a / b if b else empty
    return {"threshold": float(threshold),
            "accuracy": divide(tp + tn, tp + tn + fp + fn),
            "precision": divide(tp, tp + fp),
            "recall": divide(tp, tp + fn, None),
            "f1": divide(2 * tp, 2 * tp + fp + fn),
            "specificity": divide(tn, tn + fp, None),
            "TP": tp, "TN": tn, "FP": fp, "FN": fn}


def choose_candidate(rows):
    valid = [row for row in rows if row["TP"] + row["FN"] > 0
             and 10 * row["TP"] >= 9 * (row["TP"] + row["FN"])]
    if not valid:
        return None
    # Rational arithmetic prevents floating-point errors in F1/precision ties.
    return max(valid, key=lambda r: (
        Fraction(2 * r["TP"], 2 * r["TP"] + r["FP"] + r["FN"]),
        Fraction(r["TP"], r["TP"] + r["FP"]), -r["threshold"]))


def evaluate(truth, scores, threshold, np):
    positive = scores >= threshold
    return counts_metrics(threshold,
        int(np.count_nonzero(positive & (truth == 1))),
        int(np.count_nonzero(~positive & (truth == 0))),
        int(np.count_nonzero(positive & (truth == 0))),
        int(np.count_nonzero(~positive & (truth == 1))))


def write_csv(path, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def difference(reference, other, threshold, np):
    original, converted = reference >= threshold, other >= threshold
    delta = reference.astype(np.float64) - other
    near = (np.abs(reference - threshold) <= 0.02) | (np.abs(other - threshold) <= 0.02)
    flip = original != converted
    corr = (float(np.corrcoef(reference, other)[0, 1])
            if reference.std() > 0 and other.std() > 0 else None)
    return {"threshold": float(threshold), "mean_absolute_error": float(np.mean(np.abs(delta))),
            "max_absolute_error": float(np.max(np.abs(delta))),
            "rmse": float(np.sqrt(np.mean(delta ** 2))),
            "pearson_correlation": corr if corr is not None and np.isfinite(corr) else None,
            "changed_labels": int(np.count_nonzero(flip)),
            "float_normal_to_int8_pvc": int(np.count_nonzero(~original & converted)),
            "float_pvc_to_int8_normal": int(np.count_nonzero(original & ~converted)),
            "near_threshold_definition": "Either model score within 0.02 of threshold",
            "near_threshold_samples": int(np.count_nonzero(near)),
            "changed_labels_near_threshold": int(np.count_nonzero(flip & near))}


def int8_scores(c, X_validation):
    """Keep raw INT8 codes and dequantize into float64 without rounding the grid."""
    np = c.np
    instance, inp, out, info = c.interpreter(c.INT8, integer=True)
    raw = np.empty(len(X_validation), dtype=np.int8)
    clipped = 0
    for i, beat in enumerate(X_validation):
        q = np.rint(beat[np.newaxis, ...].astype(np.float64) / info["input_scale"]) + info["input_zero_point"]
        clipped += int(np.count_nonzero((q < -128) | (q > 127)))
        instance.set_tensor(inp["index"], np.clip(q, -128, 127).astype(np.int8))
        instance.invoke()
        raw[i] = instance.get_tensor(out["index"])[0, 0]
        if (i + 1) % 2000 == 0:
            print(f"INT8 Validation: {i + 1}/{len(X_validation)}", flush=True)
    scores = (raw.astype(np.int32) - info["output_zero_point"]) * info["output_scale"]
    c.check_scores(scores, len(X_validation))
    info.update(input_clipped_values=clipped, input_clipped_fraction=clipped / X_validation.size,
                rounding="Vectorized np.rint, ties to even; clip [-128,127]",
                score_reconstruction="(raw_int8 - output_zero_point) * output_scale in float64")
    return scores, raw, info


def plot_review(path, rows, baseline, selected, stability, np):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 3, figsize=(17, 5))
    thresholds = [r["threshold"] for r in rows]
    for key in ("precision", "recall", "f1"):
        axes[0].step(thresholds, [r[key] for r in rows], where="pre", label=key)
    axes[0].axhline(0.9, color="gray", linestyle=":", label="Recall target 0.90")
    axes[0].set(ylabel="Metric", ylim=(0, 1.05))
    for key in ("FP", "FN"):
        axes[1].step(thresholds, [r[key] for r in rows], where="pre", label=key)
    axes[1].set_ylabel("Number of beats")
    if stability:
        for key in ("precision", "recall", "f1"):
            axes[2].plot([r["threshold"] for r in stability], [r[key] for r in stability],
                         marker=".", label=key)
        axes[2].axhline(0.9, color="gray", linestyle=":")
        axes[2].set(title="Local threshold sensitivity", ylabel="Metric")
    else:
        axes[2].text(0.5, 0.5, "No candidate meets recall criterion", ha="center",
                     transform=axes[2].transAxes)
    for ax in axes:
        ax.axvline(baseline, color="gray", linestyle=":", label=f"Reference {baseline:.2f}")
        if selected is not None:
            ax.axvline(selected, color="black", linestyle="--", label=f"Candidate {selected:.6f}")
        ax.set_xlabel("Dequantized score threshold")
        ax.grid(alpha=0.3)
        ax.legend(fontsize=8)
    fig.suptitle("INT8 Validation threshold review - exploratory, not independent evaluation")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def main():
    c = importlib.import_module("07_convert_tinyml")
    c.dependencies()
    np = c.np
    # Reuse read-only shape, label, saved-index, record/group and hash checks.
    X, y, ids, parts, official_threshold, hashes = c.load_inputs()
    results = c.ROOT / "results"
    protected_paths = {c.DATA, c.SPLIT, c.THRESHOLD_FILE}
    protected_paths.update(c.ROOT.joinpath("models").glob("*.keras"))
    protected_paths.update(c.ROOT.joinpath("models").glob("*.tflite"))
    protected_paths.update(p for p in results.iterdir() if p.is_file() and p.name not in OUTPUT_NAMES)
    before = {str(path): c.sha256(path) for path in protected_paths}
    conversion = json.loads(c.REPORT.read_text(encoding="utf-8"))
    for key, actual in hashes.items():
        if conversion.get(key) != actual:
            raise ValueError(f"Conversion provenance mismatch: {key}")
    actual_int8_hash = c.sha256(c.INT8)
    if conversion.get("model_file_sizes", {}).get(c.INT8.name, {}).get("sha256") != actual_int8_hash:
        raise ValueError("INT8 model differs from Step 7 report")
    c.inspect_flatbuffer(c.INT8, int8=True)
    validation_indices = parts["validation"]
    X_validation, truth, record_ids = X[validation_indices], y[validation_indices], ids[validation_indices]
    scores, raw_codes, quantization = int8_scores(c, X_validation)
    float_model = c.load_keras()
    float_scores = float_model.predict(X_validation, batch_size=64, verbose=0)
    if float_scores.shape != (len(truth), 1):
        raise ValueError("Unexpected CNN Float32 output shape")
    float_scores = float_scores[:, 0].astype(np.float64)
    c.check_scores(float_scores, len(truth))

    # All representable output-code cutoffs in [0,1], plus endpoints and baselines.
    # With >=, these cover every distinct decision pattern of the INT8 scores.
    levels = (np.arange(-128, 128, dtype=np.int32) - quantization["output_zero_point"]) * quantization["output_scale"]
    candidates = sorted(set(levels[(levels >= 0) & (levels <= 1)].tolist()
                            + [0.0, 1.0, official_threshold, REFERENCE_THRESHOLD]))
    rows = [evaluate(truth, scores, t, np) for t in candidates]
    selected = choose_candidate(rows)
    baseline = evaluate(truth, scores, REFERENCE_THRESHOLD, np)
    official = evaluate(truth, scores, official_threshold, np)
    for row in rows:
        row["meets_recall_90"] = 10 * row["TP"] >= 9 * (row["TP"] + row["FN"])
        row["is_selected"] = selected is not None and row["threshold"] == selected["threshold"]
    # The selected dict is also in rows; use metric keys explicitly below.
    selected_threshold = selected["threshold"] if selected else None
    stability = []
    if selected:
        offsets = [i * quantization["output_scale"] for i in range(-3, 4)] + [-0.01, -0.005, -0.001, 0, 0.001, 0.005, 0.01]
        nearby = sorted({float(np.clip(selected_threshold + delta, 0, 1)) for delta in offsets})
        stability = [evaluate(truth, scores, t, np) for t in nearby]
    scenarios = {"reference_0.52": REFERENCE_THRESHOLD}
    if official_threshold != REFERENCE_THRESHOLD:
        scenarios["official_config"] = official_threshold
    if selected:
        scenarios["candidate"] = selected_threshold
    record_rows = []
    for record_id in np.unique(record_ids):
        mask = record_ids == record_id
        for name, threshold in scenarios.items():
            row = {"record_id": str(record_id), "scenario": name,
                   "samples": int(np.count_nonzero(mask)),
                   "N": int(np.count_nonzero(truth[mask] == 0)),
                   "V": int(np.count_nonzero(truth[mask] == 1)),
                   **evaluate(truth[mask], scores[mask], threshold, np)}
            row["false_positive_rate"] = row["FP"] / row["N"] if row["N"] else None
            record_rows.append(row)
    record_rankings = {scenario: sorted([r for r in record_rows if r["scenario"] == scenario],
                                        key=lambda r: (-r["FP"], r["record_id"])) for scenario in scenarios}
    model_differences = {}
    for name, threshold in scenarios.items():
        model_differences[name] = {
            **difference(float_scores, scores, threshold, np),
            "keras_metrics": evaluate(truth, float_scores, threshold, np),
            "int8_metrics": evaluate(truth, scores, threshold, np)}
    distance = np.abs(scores - (selected_threshold if selected else official_threshold))
    nearest = np.argsort(distance, kind="stable")[:25]
    nearest_details = [{"dataset_index": int(validation_indices[i]), "record_id": str(record_ids[i]),
                        "label": int(truth[i]), "int8_raw_code": int(raw_codes[i]),
                        "int8_score": float(scores[i]), "keras_score": float(float_scores[i])} for i in nearest]
    metric_keys = ("accuracy", "precision", "recall", "f1", "specificity", "TP", "TN", "FP", "FN")
    delta = {k: selected[k] - baseline[k] for k in metric_keys} if selected else None
    stability_summary = {"status": "DESCRIPTIVE_ONLY", "nearby_threshold_metrics": stability,
                         "note": "Quantized scores create stepwise decisions. Perturbations are sensitivity checks, not independent or statistical robustness evidence."}
    if stability:
        stability_summary.update(
            ranges={k: {"min": min(r[k] for r in stability), "max": max(r[k] for r in stability)}
                    for k in ("precision", "recall", "f1", "FP", "FN")},
            nearby_thresholds_below_recall_90=sum(10 * r["TP"] < 9 * (r["TP"] + r["FN"]) for r in stability))
    # Verify the current read-only workflow has not changed any earlier artifact.
    for path, digest in before.items():
        if c.sha256(c.ROOT / path) != digest:
            raise ValueError(f"Protected input/result changed during review: {path}")
    recommendation = {
        "status": "EXPLORATORY_CANDIDATE" if selected else "NO_FEASIBLE_CANDIDATE",
        "official_threshold_unchanged": official_threshold,
        "reference_threshold": REFERENCE_THRESHOLD, "candidate_threshold": selected_threshold,
        "selection_rule": "Validation recall >=90%; highest F1, then precision, then smallest enumerated threshold",
        "candidate_grid": "Every dequantized INT8 output level in [0,1], endpoints 0/1, configured threshold and requested 0.52 reference; comparison scores >= threshold",
        "candidate_count": len(rows), "quantization": quantization,
        "validation_samples": len(truth), "validation_records": sorted(set(record_ids)),
        "validation_N": int(np.count_nonzero(truth == 0)), "validation_V": int(np.count_nonzero(truth == 1)),
        "reference_metrics": baseline, "official_config_metrics": official,
        "candidate_metrics": selected, "candidate_minus_reference": delta,
        "record_rankings_by_false_positives": record_rankings,
        "record_metric_note": "Recall=None if a record has no PVC; specificity=None if no Normal; undefined precision/F1 reported as zero. FP counts and FPR should both be inspected.",
        "local_stability": stability_summary, "keras_vs_int8": model_differences,
        "nearest_25_samples_to_candidate_or_official": nearest_details,
        "source_paths": {"keras": str(c.KERAS), "int8": str(c.INT8), "dataset": str(c.DATA), "split": str(c.SPLIT)},
        "provenance": {**hashes, "int8_sha256": actual_int8_hash, "threshold_config_sha256": before[str(c.THRESHOLD_FILE)]},
        "protected_artifact_hashes_unchanged": True,
        "test_inference_performed": False, "training_performed": False,
        "limitations": ["Validation was reused in Steps 6, 6.5 and 7; threshold selection here is exploratory and optimistically biased.",
                        "No claim of improvement on previously exposed Test or real ECG; no Test inference here.",
                        "Record 201/202 linked; remaining record IDs are proxies, not independently verified patient identities.",
                        "No automatic threshold deployment. Official optimized_threshold.json is unchanged.",
                        "Sigmoid/dequantized scores are not automatically calibrated probabilities.",
                        "Raising precision may increase missed PVC; maximizing F1 subject to recall does not guarantee fewer false alarms than 0.52."]}
    results.mkdir(parents=True, exist_ok=True)
    c.PLOTS.mkdir(parents=True, exist_ok=True)
    write_csv(results / OUTPUT_NAMES[0], rows)
    write_csv(results / OUTPUT_NAMES[1], record_rows)
    plot_path = c.PLOTS / "int8_threshold_tradeoff.png"
    plot_review(plot_path, rows, REFERENCE_THRESHOLD, selected_threshold, stability, np)
    (results / OUTPUT_NAMES[2]).write_text(json.dumps(recommendation, ensure_ascii=False,
                                                    indent=2, allow_nan=False), encoding="utf-8")
    print(f"\nValidation only: {len(truth)} beats; official threshold={official_threshold:.6f}")
    print(f"{'metric':16s} {'reference 0.52':>16s} {'candidate':>16s} {'change':>16s}")
    for key in metric_keys:
        print(f"{key:16s} {baseline[key]:16.6f} " +
              (f"{selected[key]:16.6f} {delta[key]:16.6f}" if selected else "no feasible candidate"))
    if selected:
        print(f"Candidate threshold: {selected_threshold:.9f}; recall >=90% satisfied.")
        for key, label in (("FP", "False alarms"), ("FN", "Missed PVC")):
            amount = delta[key]
            print(f"{label}: {'increased' if amount > 0 else 'decreased' if amount < 0 else 'unchanged'} by {abs(amount)} versus 0.52")
    else:
        print("No enumerated threshold satisfies recall >=90%. No candidate selected; no automatic fallback.")
    print("\nPer-record INT8 results:")
    print(f"{'record':8s} {'scenario':18s} {'precision':>10s} {'recall':>10s} {'FP':>7s} {'FN':>7s}")
    for row in record_rows:
        recall = f"{row['recall']:.6f}" if row["recall"] is not None else "N/A"
        print(f"{row['record_id']:8s} {row['scenario']:18s} {row['precision']:10.6f} {recall:>10s} {row['FP']:7d} {row['FN']:7d}")
    for name, ranking in record_rankings.items():
        print(f"Most FP ({name}):", [(r["record_id"], r["FP"], r["false_positive_rate"]) for r in ranking[:3]])
    print("Stability:", json.dumps(stability_summary, indent=2))
    print("Float32/INT8 differences:", json.dumps(model_differences, indent=2))
    print("Exploratory Validation review only. Old artifacts and official threshold unchanged; no Test inference.")
    for path in [results / name for name in OUTPUT_NAMES] + [plot_path]:
        if not path.is_file() or not path.stat().st_size:
            raise OSError(f"Missing or empty output: {path}")
        print("Saved:", path)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        print("Step 7.5 incomplete; no Python/.venv repair or threshold replacement attempted.", file=sys.stderr)
        sys.exit(1)
