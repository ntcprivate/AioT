"""Step 5: build the local MIT-BIH N/V dataset, preserving record IDs.

Run: .venv/Scripts/python.exe python/05_build_dataset.py
Only annotated N/V beats are included. No training or dataset split is done.
Record IDs are provenance, not patient IDs (different records may share a patient).
"""

import csv
from pathlib import Path
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.signal import resample_poly
import wfdb


ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "mit-bih-arrhythmia-database-1.0.0"
OUTPUT = ROOT / "data" / "processed" / "mitbih_nv_250hz.npz"
SUMMARY = OUTPUT.with_name("mitbih_record_summary.csv")
PLOT = ROOT / "plots" / "mitbih_class_distribution.png"
SOURCE_FS = 360
TARGET_FS = 250
WINDOW = 256
HALF = 128
STD_EPS = 1e-8
LABELS = {"N": 0, "V": 1}
FIELDS = ["record_id", "lead", "n_normal", "n_pvc", "n_rejected",
          "status", "reason", "n_boundary", "n_nonfinite", "n_low_std",
          "n_other_annotations"]


def extract_record(path, row):
    """Load only one selected channel from one record at a time."""
    missing = [ext for ext in (".hea", ".dat", ".atr")
               if not path.with_suffix(ext).is_file()]
    if missing:
        raise ValueError("Missing local files: " + ", ".join(missing))
    header = wfdb.rdheader(str(path))
    leads = [name.strip().upper() for name in header.sig_name]
    if "MLII" not in leads:
        raise ValueError(f"No MLII lead (available: {header.sig_name})")
    row["lead"] = "MLII"
    if header.fs != SOURCE_FS:
        raise ValueError(f"Expected {SOURCE_FS} Hz, found {header.fs} Hz")
    annotations = wfdb.rdann(str(path), "atr")
    if len(annotations.sample) != len(annotations.symbol):
        raise ValueError("Annotation sample/symbol lengths differ")
    if (np.any(annotations.sample < 0)
            or np.any(annotations.sample >= header.sig_len)):
        raise ValueError("Annotation sample outside original signal")
    record = wfdb.rdrecord(str(path), channels=[leads.index("MLII")])
    signal = record.p_signal[:, 0]
    # Reject a damaged record before filtering can spread NaN/Inf to neighbors.
    if not np.isfinite(signal).all():
        raise ValueError("Source MLII contains NaN/Inf; record excluded before resampling")
    resampled = resample_poly(signal, up=25, down=36)
    # Exact integer round-half-up of sample * 250/360; no floating point drift.
    centers = (annotations.sample.astype(np.int64) * 25 + 18) // 36
    beats, labels = [], []
    for center, symbol in zip(centers, annotations.symbol):
        if symbol not in LABELS:
            row["n_other_annotations"] += 1
            continue
        start, end = int(center) - HALF, int(center) + HALF
        if start < 0 or end > len(resampled):
            row["n_boundary"] += 1
            continue
        beat = resampled[start:end].astype(np.float64, copy=True)
        if not np.isfinite(beat).all():
            row["n_nonfinite"] += 1
            continue
        std = float(beat.std())
        if std < STD_EPS:
            row["n_low_std"] += 1
        beat = ((beat - beat.mean()) / max(std, STD_EPS)).astype(np.float32)
        if not np.isfinite(beat).all():
            row["n_nonfinite"] += 1
            continue
        beats.append(beat)
        labels.append(LABELS[symbol])
    row["n_rejected"] = row["n_boundary"] + row["n_nonfinite"]
    X = np.asarray(beats, dtype=np.float32).reshape(-1, WINDOW, 1)
    y = np.asarray(labels, dtype=np.int32)
    row["n_normal"] = int(np.count_nonzero(y == 0))
    row["n_pvc"] = int(np.count_nonzero(y == 1))
    return X, y


def validate(X, y, record_ids):
    """Verify actual dataset structure, values and provenance alignment."""
    if X.shape != (len(y), WINDOW, 1) or record_ids.shape != y.shape or y.ndim != 1:
        raise ValueError("Invalid shapes or unequal sample counts")
    if X.dtype != np.float32 or y.dtype != np.int32 or record_ids.dtype.kind != "U":
        raise ValueError("Invalid dtypes; expected float32, int32 and Unicode IDs")
    if not np.isin(y, [0, 1]).all():
        raise ValueError("Labels outside {0, 1}")
    if not np.isfinite(X).all():
        raise ValueError("X contains NaN/Inf")
    if np.any(record_ids == ""):
        raise ValueError("Empty record ID")


def main():
    if not DATA_DIR.is_dir():
        raise FileNotFoundError(f"Data directory not found: {DATA_DIR}")
    # MIT-BIH records are in this directory; do not scan ancillary sample folders.
    paths = sorted(DATA_DIR.glob("*.hea"))
    if not paths:
        raise FileNotFoundError(f"No .hea files in: {DATA_DIR}")
    rows, x_parts, y_parts, id_parts = [], [], [], []
    for header_path in paths:
        path = header_path.with_suffix("")
        record_id = path.name
        row = dict.fromkeys(FIELDS, 0)
        row.update(record_id=record_id, lead="", status="skipped", reason="")
        try:
            X_record, y_record = extract_record(path, row)
            if len(y_record):
                x_parts.append(X_record)
                y_parts.append(y_record)
                id_parts.append(np.full(len(y_record), record_id,
                                        dtype=f"<U{len(record_id)}"))
                row["status"] = "ok"
            else:
                row["reason"] = "No valid N/V beats after filtering"
            print(f"{record_id}: {row['status']}; N={row['n_normal']}, "
                  f"V={row['n_pvc']}, rejected={row['n_rejected']} "
                  f"{row['reason']}", flush=True)
        except (OSError, ValueError, IndexError, EOFError) as error:
            row["reason"] = f"{type(error).__name__}: {error}"
            print(f"{record_id}: skipped; {row['reason']}", flush=True)
        rows.append(row)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with SUMMARY.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"CSV: {SUMMARY}")
    if not x_parts:
        raise ValueError("No valid N/V beats; CSV saved, no new NPZ/plot written")
    X = np.concatenate(x_parts)
    y = np.concatenate(y_parts)
    record_ids = np.concatenate(id_parts)
    del x_parts, y_parts, id_parts
    validate(X, y, record_ids)
    np.savez_compressed(OUTPUT, X=X, y=y, record_ids=record_ids)
    with np.load(OUTPUT, allow_pickle=False) as saved:
        loaded_X, loaded_y, loaded_ids = saved["X"], saved["y"], saved["record_ids"]
        validate(loaded_X, loaded_y, loaded_ids)
        if not (np.array_equal(loaded_X, X) and np.array_equal(loaded_y, y)
                and np.array_equal(loaded_ids, record_ids)):
            raise ValueError("Reloaded NPZ differs from generated arrays")
    del loaded_X, loaded_y, loaded_ids

    counts = np.bincount(y, minlength=2)
    successful = sum(row["status"] == "ok" for row in rows)
    print(f"\nRecords processed successfully: {successful}/{len(rows)}")
    print("Skipped records:")
    skipped = [row for row in rows if row["status"] != "ok"]
    for row in skipped:
        print(f"  {row['record_id']}: {row['reason']}")
    if not skipped:
        print("  None")
    print(f"Total beats: {len(y)}")
    print(f"N (0): {counts[0]} ({100 * counts[0] / len(y):.2f}%)")
    print(f"V (1): {counts[1]} ({100 * counts[1] / len(y):.2f}%)")
    for name, array in (("X", X), ("y", y), ("record_ids", record_ids)):
        print(f"{name}: shape={array.shape}, dtype={array.dtype}")
    print(f"X NaN: {np.isnan(X).any()}; Inf: {np.isinf(X).any()}")
    print("NPZ reload verified: matching sample counts, 256 samples/beat, labels 0/1.")
    print("record_ids identify records, NOT unique patients; no train/test split made.")
    print(f"NPZ: {OUTPUT}")

    fig, ax = plt.subplots(figsize=(8, 5))
    bars = ax.bar(["Normal (N = 0)", "PVC (V = 1)"], counts,
                  color=["steelblue", "tomato"])
    ax.bar_label(bars, padding=3)
    ax.set(title="MIT-BIH MLII - annotated N/V beats at 250 Hz",
           ylabel="Number of beats")
    ax.set_ylim(0, max(counts) * 1.15)
    fig.tight_layout()
    PLOT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(PLOT, dpi=150)
    plt.close(fig)
    print(f"Plot: {PLOT}")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        sys.exit(1)
