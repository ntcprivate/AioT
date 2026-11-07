"""Verify a real, single-boot ESP32 serial log against generated golden data.

Usage: python python/08_verify_esp32_output.py --log results/esp32_serial.log
No sample data, golden predictions or hardware measurements are fabricated.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import statistics
import sys

ROOT = Path(__file__).resolve().parent.parent


def fields(line):
    return dict(re.findall(r"([a-zA-Z0-9_]+)=([^\s]+)", line))


def latency_stats(values):
    if not values:
        return None
    ordered = sorted(values)
    return {"count": len(values), "min_us": min(values), "mean_us": statistics.mean(values),
            "median_us": statistics.median(values), "p95_us": ordered[math.ceil(0.95 * len(values)) - 1],
            "max_us": max(values), "scope": "Invoke only; ADC/filtering/beat detection/serial excluded"}


def verify(log_path):
    text = log_path.read_text(encoding="utf-8-sig", errors="replace")
    golden = json.loads((ROOT / "results/esp32_golden_outputs.json").read_text(encoding="utf-8"))
    lines = text.splitlines()
    if sum("ECG_BOOT " in line for line in lines) != 1:
        raise ValueError("Capture exactly one boot/run; multiple/no ECG_BOOT markers found")
    result_lines = [fields(line) for line in lines if "ECG_RESULT " in line]
    hash_lines = [fields(line) for line in lines if "ECG_HASH " in line]
    errors = [line for line in lines if "ECG_ERROR " in line]
    expected_hashes = {"model": golden["model_sha256"], "samples": golden["samples_sha256"]}
    hashes_ok = all(sum(row.get("kind") == kind and row.get("sha256") == digest
                        and row.get("status") == "PASS" for row in hash_lines) == 1
                    for kind, digest in expected_hashes.items())
    actual_model_hash = hashlib.sha256((ROOT / "models/ecg_cnn_int8.tflite").read_bytes()).hexdigest()
    if actual_model_hash != golden["model_sha256"]:
        raise ValueError("Current source model no longer matches golden outputs")
    input_file = ROOT / "firmware/esp32_tinyml_step8/main/test_data/ecg_test_samples_int8.bin"
    if hashlib.sha256(input_file.read_bytes()).hexdigest() != golden["samples_sha256"]:
        raise ValueError("Current input fixture no longer matches golden outputs")
    observed = {}
    for row in result_lines:
        sample_id = int(row["sample_id"])
        if sample_id in observed:
            raise ValueError(f"Duplicate sample result: {sample_id}")
        observed[sample_id] = row
    expected_ids = {s["sample_id"] for s in golden["samples"]}
    if set(observed) - expected_ids:
        raise ValueError("Unexpected sample IDs in serial log")
    comparisons = []
    scale = golden["quantization"]["output_scale"]
    zero = golden["quantization"]["output_zero_point"]
    threshold = golden["threshold"]
    for sample in golden["samples"]:
        row = observed.get(sample["sample_id"])
        if row is None:
            comparisons.append({"sample_id": sample["sample_id"], "status": "FAILED", "reason": "Missing result"})
            continue
        code = int(row["output_int8"])
        score = (code - zero) * scale
        score_logged = float(row["score"])
        metadata_ok = (int(row["dataset_index"]) == sample["dataset_index"]
                       and row["record"] == sample["record_id"] and int(row["true"]) == sample["true_label"]
                       and int(row["python_int8"]) == sample["python_output_int8"])
        bytes_ok = row.get("input_match") == "1" and hashes_ok
        stable = row.get("stable") == "1"
        values_ok = (-128 <= code <= 127 and math.isfinite(score_logged)
                     and abs(score_logged - score) < 1e-6 and int(row["predicted"]) == int(score >= threshold))
        label_ok = int(score >= threshold) == sample["python_predicted"]
        lsb = abs(code - sample["python_output_int8"])
        lsb_ok = int(row["lsb"]) == lsb
        status = "FAILED" if not all((metadata_ok, bytes_ok, stable, values_ok, label_ok, lsb_ok)) else "NEEDS_REVIEW" if lsb else "EXACT_MATCH"
        comparisons.append({**sample, "esp32_output_int8": code, "esp32_score": score,
                            "esp32_predicted": int(score >= threshold), "lsb_difference": lsb,
                            "absolute_score_difference": abs(score - sample["python_score"]),
                            "metadata_match": metadata_ok, "input_bytes_match": bytes_ok,
                            "class_match": label_ok, "repeats_stable": stable, "logged_score_valid": values_ok,
                            "near_threshold": abs(sample["python_score"] - threshold) <= 2 * scale,
                            "status": status})
    timings, timing_ids = [], set()
    per_sample_timings = {sample_id: [] for sample_id in expected_ids}
    for line in lines:
        if "ECG_TIME " not in line:
            continue
        row = fields(line)
        key = (int(row["sample_id"]), int(row["run"]))
        value = int(row["latency_us"])
        if key in timing_ids or key[0] not in expected_ids or key[1] < 0 or value < 0:
            raise ValueError("Duplicate or invalid latency measurement")
        timing_ids.add(key)
        timings.append(value)
        per_sample_timings[key[0]].append(value)
    done = [fields(line) for line in lines if "ECG_DONE " in line]
    complete = len(done) == 1 and int(done[0].get("samples", -1)) == len(expected_ids)
    enough_timings = all(30 <= len(v) <= 100 for v in per_sample_timings.values())
    exact = sum(row["status"] == "EXACT_MATCH" for row in comparisons)
    failed = sum(row["status"] == "FAILED" for row in comparisons)
    status = "FAILED" if errors or failed or not complete or not hashes_ok or not enough_timings else "EXACT_MATCH" if exact == len(expected_ids) else "NEEDS_REVIEW"
    report = {"status": status, "hardware_log_path": str(log_path.resolve()),
              "hardware_log_sha256": hashlib.sha256(log_path.read_bytes()).hexdigest(),
              "evidence_scope": "User-supplied hardware serial log; log origin cannot be independently authenticated by this parser",
              "samples_expected": len(expected_ids), "samples_observed": len(observed),
              "exact_outputs": exact, "matching_classes": sum(bool(r.get("class_match")) for r in comparisons),
              "hashes_verified_from_log": hashes_ok, "completed_marker": complete,
              "errors": errors, "comparisons": comparisons, "latency": latency_stats(timings),
              "per_sample_latency": {str(i): latency_stats(v) for i, v in per_sample_timings.items()},
              "heap_logs": [fields(line) for line in lines if "ECG_HEAP " in line],
              "arena_logs": [fields(line) for line in lines if "ECG_ARENA " in line],
              "boot": [fields(line) for line in lines if "ECG_BOOT " in line],
              "configuration": [fields(line) for line in lines if "ECG_CONFIG " in line],
              "kernel_difference_note": "Nonzero LSB differences may reflect kernel rounding/implementation differences; not automatically accepted. Class disagreement is FAILED. No threshold adjustment."}
    dest = ROOT / "results/esp32_inference_comparison.json"
    dest.write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    step8_path = ROOT / "results/esp32_step8_report.json"
    if step8_path.is_file():
        step8 = json.loads(step8_path.read_text(encoding="utf-8"))
        step8["hardware_status"] = "HARDWARE_LOG_REVIEWED"
        step8["statuses"]["INFERENCE_PASSED"] = bool(
            complete and not errors and hashes_ok and enough_timings
            and len(observed) == len(expected_ids)
            and all(r.get("input_bytes_match") and r.get("logged_score_valid")
                    and r.get("repeats_stable") for r in comparisons))
        step8["statuses"]["PYTHON_MATCH_PASSED"] = status == "EXACT_MATCH"
        step8["runtime"] = {"latency": report["latency"], "arena": report["arena_logs"],
                           "heap": report["heap_logs"], "boot": report["boot"], "configuration": report["configuration"]}
        step8["inference"] = {key: report[key] for key in ("status", "samples_expected", "samples_observed", "exact_outputs", "matching_classes")}
        step8["comparison_report"] = str(dest)
        step8_path.write_text(json.dumps(step8, indent=2, ensure_ascii=False), encoding="utf-8")
        (ROOT / "results/esp32_step8_summary.txt").write_text(
            f"Step 8: real hardware log reviewed. Result: {status}\n"
            f"Samples: {len(observed)}/{len(expected_ids)}; exact outputs: {exact}\n"
            f"Class matches: {report['matching_classes']}; threshold unchanged: {threshold}\n"
            f"Build status: {step8['statuses']['BUILD_PASSED']}; flash status: {step8['statuses']['FLASH_PASSED']}\n"
            "Build/flash command evidence is separate from runtime serial evidence.\n"
            "See esp32_inference_comparison.json for measured latency/heap and all differences.\n",
            encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return status


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", type=Path, required=True)
    args = parser.parse_args()
    try:
        sys.exit(0 if verify(args.log) == "EXACT_MATCH" else 2)
    except (OSError, ValueError, KeyError) as error:
        print(f"ERROR: {error}. No PASS report created.", file=sys.stderr)
        sys.exit(1)
