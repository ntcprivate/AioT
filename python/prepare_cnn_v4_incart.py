from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import wfdb
from scipy.signal import resample_poly

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "files"
SPLIT = ROOT / "data/processed/incart_patient_split_v4.json"
OUT = ROOT / "data/processed/incart_v4_250hz.npz"
REPORT = ROOT / "results/cnn_v4/preprocessing.json"
EPS = 1e-8


def main() -> None:
    split = json.loads(SPLIT.read_text())
    record_split = {r: name for name in ("train", "validation", "test") for r in split[name]["records"]}
    patient_by_record = {r: str(pid) for name in ("train", "validation", "test")
                         for pid in split[name]["patient_ids"]
                         for r in split[name]["records"] if False}
    # Patient IDs are authoritative in current headers, not inferred from record numbers.
    patient_by_record = {}
    for record in record_split:
        for line in (SOURCE / f"{record}.hea").read_text(encoding="ascii").splitlines():
            if line.lower().startswith("# patient "):
                patient_by_record[record] = line.split()[-1]
                break
        if record not in patient_by_record:
            raise RuntimeError(f"Missing patient ID in {record}.hea")

    xs, ys, records, patients, splits, centers = [], [], [], [], [], []
    per_record, offsets = [], []
    for record in sorted(record_split):
        header = wfdb.rdheader(str(SOURCE / record))
        lead_names = [name.strip().upper() for name in header.sig_name]
        if header.fs != 257 or lead_names.count("II") != 1:
            raise RuntimeError(f"Unexpected source contract for {record}: fs={header.fs}, leads={lead_names}")
        signal = wfdb.rdrecord(str(SOURCE / record), channels=[lead_names.index("II")],
                               physical=True, return_res=32).p_signal[:, 0]
        ann = wfdb.rdann(str(SOURCE / record), "atr")
        resampled = resample_poly(signal, 250, 257).astype(np.float32)
        if not np.isfinite(resampled).all():
            raise RuntimeError(f"NaN/Inf after resampling {record}")
        kept = rejected_boundary = rejected_numeric = 0
        n_count = v_count = 0
        for source_center, symbol in zip(ann.sample, ann.symbol):
            if symbol not in {"N", "V"}:
                continue
            center = int(np.floor(int(source_center) * 250 / 257 + 0.5))
            if center < 128 or center + 128 > len(resampled):
                rejected_boundary += 1
                continue
            beat = resampled[center - 128:center + 128].astype(np.float64)
            std = float(beat.std())
            if not np.isfinite(beat).all() or not np.isfinite(std) or std <= EPS:
                rejected_numeric += 1
                continue
            normalized = ((beat - beat.mean()) / std).astype(np.float32)
            if not np.isfinite(normalized).all() or normalized.shape != (256,):
                rejected_numeric += 1
                continue
            # Minimal centering/morphology screen on the normalized central +/-100 ms.
            region = normalized[103:154]
            offsets.append(int(np.argmax(np.abs(region))) + 103 - 128)
            xs.append(normalized[:, None]); ys.append(0 if symbol == "N" else 1)
            records.append(record); patients.append(patient_by_record[record])
            splits.append(record_split[record]); centers.append(center)
            kept += 1; n_count += symbol == "N"; v_count += symbol == "V"
        per_record.append({"record": record, "patient": patient_by_record[record],
                           "split": record_split[record], "kept": kept, "N": int(n_count),
                           "V": int(v_count), "boundary_rejected": rejected_boundary,
                           "numeric_rejected": rejected_numeric})

    X = np.stack(xs).astype(np.float32)
    y = np.asarray(ys, dtype=np.int32)
    record_ids = np.asarray(records, dtype="U3")
    patient_ids = np.asarray(patients, dtype="U2")
    split_names = np.asarray(splits, dtype="U10")
    centers_250hz = np.asarray(centers, dtype=np.int64)
    offset = np.asarray(offsets)
    if X.shape[1:] != (256, 1) or not np.isfinite(X).all() or set(np.unique(y)) != {0, 1}:
        raise RuntimeError("Final dataset contract failed")
    p95 = float(np.percentile(np.abs(offset), 95))
    if abs(float(np.median(offset))) > 3 or p95 > 20:
        raise RuntimeError(f"Important annotation centering problem: median={np.median(offset)}, p95={p95}")
    np.savez_compressed(OUT, X=X, y=y, record_ids=record_ids, patient_ids=patient_ids,
                        split=split_names, centers_250hz=centers_250hz)
    counts = {name: {"samples": int(np.sum(split_names == name)),
                     "N": int(np.sum((split_names == name) & (y == 0))),
                     "V": int(np.sum((split_names == name) & (y == 1)))}
              for name in ("train", "validation", "test")}
    result = {"source": "files/ current headers", "lead": "II", "source_hz": 257,
              "target_hz": 250, "resample_poly": [250, 257], "window": 256,
              "normalization": "per-window z-score float64 calculation -> float32",
              "annotation_mapping": "floor(sample*250/257 + 0.5)", "counts": counts,
              "nan_or_inf": False, "offset_median_samples_250hz": float(np.median(offset)),
              "offset_p95_absolute_samples_250hz": p95,
              "morphology_screen": "max absolute normalized amplitude within center +/-100 ms",
              "records": per_record}
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"output": str(OUT), **counts, "median_offset": result["offset_median_samples_250hz"],
                      "p95_abs_offset": p95}, indent=2))


if __name__ == "__main__":
    main()
