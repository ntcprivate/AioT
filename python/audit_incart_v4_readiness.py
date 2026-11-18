"""Audit the local INCART corpus and prepare a patient-disjoint V4 split.

This script is diagnostic only.  It does not extract beat windows or train a
model.  Current headers in ``files`` are authoritative; ``.old-headers`` is
never passed to WFDB.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import wfdb


PATIENT_RE = re.compile(r"^#\s*patient\s+(\d+)\s*$", re.IGNORECASE)
RECORD_RE = re.compile(r"^I\d{2}$")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def patient_from_current_header(path: Path) -> str:
    for line in path.read_text(encoding="ascii", errors="strict").splitlines():
        match = PATIENT_RE.match(line.strip())
        if match:
            return match.group(1)
    raise ValueError(f"No '# patient <id>' line in current header: {path}")


def qrs_offset_samples(signal: np.ndarray, samples: np.ndarray, fs: float) -> list[int]:
    """Estimate annotation-to-local-QRS offsets on raw lead II.

    The estimate is the maximum absolute excursion from a local median within
    +/-100 ms.  It is a screening statistic, not a replacement annotation.
    """
    radius = max(1, int(round(0.100 * fs)))
    baseline_radius = max(radius + 1, int(round(0.250 * fs)))
    offsets: list[int] = []
    for sample in samples:
        sample = int(sample)
        if sample < baseline_radius or sample + baseline_radius >= signal.size:
            continue
        baseline = float(np.median(signal[sample - baseline_radius : sample + baseline_radius + 1]))
        region = signal[sample - radius : sample + radius + 1]
        offsets.append(int(np.argmax(np.abs(region - baseline))) - radius)
    return offsets


def choose_split(patient_rows: list[dict], seed: int) -> dict[str, list[str]]:
    """Choose 22/5/5 patients using counts only and a fixed reproducible seed."""
    rng = np.random.default_rng(seed)
    patient_ids = np.array([row["patient_id"] for row in patient_rows])
    counts = {row["patient_id"]: np.array([row["N"], row["V"], row["OTHER"]], dtype=float)
              for row in patient_rows}
    total = sum(counts.values(), np.zeros(3))
    targets = {"train": 22 / 32, "validation": 5 / 32, "test": 5 / 32}
    best_score = float("inf")
    best: dict[str, list[str]] | None = None
    # This uses annotation totals only.  No waveform or model output is used.
    for _ in range(100_000):
        perm = rng.permutation(patient_ids)
        candidate = {
            "train": sorted(perm[:22].tolist(), key=int),
            "validation": sorted(perm[22:27].tolist(), key=int),
            "test": sorted(perm[27:].tolist(), key=int),
        }
        score = 0.0
        for name, ids in candidate.items():
            actual = sum((counts[pid] for pid in ids), np.zeros(3))
            expected = total * targets[name]
            # Balance N and V most strongly; OTHER is reported but not trained.
            rel = (actual - expected) / np.maximum(expected, 1.0)
            score += float(rel[0] ** 2 + 2.0 * rel[1] ** 2 + 0.25 * rel[2] ** 2)
        if score < best_score:
            best_score, best = score, candidate
    assert best is not None
    best["selection_score"] = best_score  # type: ignore[assignment]
    return best


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--source", type=Path, default=Path("files"))
    parser.add_argument("--output", type=Path, default=Path("results/incart_v4_preparation.json"))
    parser.add_argument("--split-output", type=Path,
                        default=Path("data/processed/incart_patient_split_v4.json"))
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    root = args.root.resolve()
    source = (root / args.source).resolve() if not args.source.is_absolute() else args.source.resolve()
    output = (root / args.output).resolve() if not args.output.is_absolute() else args.output.resolve()
    split_output = ((root / args.split_output).resolve()
                    if not args.split_output.is_absolute() else args.split_output.resolve())
    records_file = source / "RECORDS"
    records = [line.strip() for line in records_file.read_text(encoding="ascii").splitlines() if line.strip()]
    if len(records) != 75 or len(set(records)) != 75 or not all(RECORD_RE.match(x) for x in records):
        raise RuntimeError(f"Expected 75 unique Ixx records, got {len(records)}")

    expected_hashes: dict[str, str] = {}
    checksum_file = source / "SHA256SUMS.txt"
    for line in checksum_file.read_text(encoding="ascii").splitlines():
        digest, name = line.split(maxsplit=1)
        expected_hashes[name.lstrip("* ")] = digest.lower()

    record_rows: list[dict] = []
    patient_records: dict[str, list[str]] = defaultdict(list)
    patient_counts: dict[str, Counter] = defaultdict(Counter)
    all_offsets: list[int] = []
    checksum_failures: list[str] = []
    read_failures: list[str] = []

    for record in records:
        required = {ext: source / f"{record}.{ext}" for ext in ("hea", "dat", "atr")}
        missing = [str(path) for path in required.values() if not path.is_file()]
        if missing:
            raise FileNotFoundError(f"{record}: missing {missing}")
        for path in required.values():
            expected = expected_hashes.get(path.name)
            if expected is None or sha256(path) != expected:
                checksum_failures.append(path.name)

        patient_id = patient_from_current_header(required["hea"])
        try:
            header = wfdb.rdheader(str(source / record))
            # Read a real signal segment, not only header metadata.
            probe = wfdb.rdrecord(str(source / record), sampfrom=0, sampto=min(1024, header.sig_len), physical=True)
            annotation = wfdb.rdann(str(source / record), "atr")
            if probe.p_signal is None or probe.p_signal.shape[1] != header.n_sig:
                raise RuntimeError("signal probe shape mismatch")
            lead_names = list(header.sig_name)
            lead_ii_indices = [index for index, name in enumerate(lead_names) if name.strip().upper() == "II"]
            if len(lead_ii_indices) != 1:
                raise RuntimeError(f"expected one lead II, found {lead_ii_indices} in {lead_names}")
            # Load only lead II for the offset screening statistic.
            lead_record = wfdb.rdrecord(
                str(source / record), channels=lead_ii_indices, physical=True, return_res=32
            )
            lead_signal = np.asarray(lead_record.p_signal[:, 0], dtype=np.float32)
            if not np.isfinite(lead_signal).all():
                raise RuntimeError("lead II contains NaN/Inf")
        except Exception as exc:  # keep an explicit machine-readable failure list
            read_failures.append(f"{record}: {type(exc).__name__}: {exc}")
            continue

        symbols = Counter(annotation.symbol)
        n_count = int(symbols.get("N", 0))
        v_count = int(symbols.get("V", 0))
        other_count = int(len(annotation.symbol) - n_count - v_count)
        nv_mask = np.fromiter((symbol in {"N", "V"} for symbol in annotation.symbol), dtype=bool)
        offsets = qrs_offset_samples(lead_signal, np.asarray(annotation.sample)[nv_mask], float(header.fs))
        all_offsets.extend(offsets)
        row = {
            "record_id": record,
            "patient_id": patient_id,
            "fs_hz": float(header.fs),
            "samples": int(header.sig_len),
            "duration_seconds": float(header.sig_len / header.fs),
            "signals": lead_names,
            "lead_ii_index": int(lead_ii_indices[0]),
            "N": n_count,
            "V": v_count,
            "OTHER": other_count,
            "annotation_total": int(len(annotation.symbol)),
            "symbols": dict(sorted(symbols.items())),
            "qrs_offset_count": len(offsets),
        }
        record_rows.append(row)
        patient_records[patient_id].append(record)
        patient_counts[patient_id].update(N=n_count, V=v_count, OTHER=other_count)

    patient_rows = [
        {
            "patient_id": patient_id,
            "records": sorted(patient_records[patient_id]),
            "record_count": len(patient_records[patient_id]),
            "N": int(patient_counts[patient_id]["N"]),
            "V": int(patient_counts[patient_id]["V"]),
            "OTHER": int(patient_counts[patient_id]["OTHER"]),
        }
        for patient_id in sorted(patient_records, key=int)
    ]
    split = choose_split(patient_rows, args.seed)
    split_score = float(split.pop("selection_score"))
    by_patient = {row["patient_id"]: row for row in patient_rows}
    split_summary = {}
    for name, ids in split.items():
        rows = [by_patient[pid] for pid in ids]
        split_summary[name] = {
            "patient_ids": ids,
            "records": sorted([record for row in rows for record in row["records"]]),
            "patient_count": len(ids),
            "record_count": sum(row["record_count"] for row in rows),
            "N": sum(row["N"] for row in rows),
            "V": sum(row["V"] for row in rows),
            "OTHER": sum(row["OTHER"] for row in rows),
        }

    offsets_array = np.asarray(all_offsets, dtype=int)
    result = {
        "schema": 1,
        "purpose": "INCART integrity audit and V4 split preparation; no beat extraction or training",
        "source": str(source.relative_to(root)),
        "authoritative_headers": "files/*.hea",
        "old_headers_used": False,
        "integrity": {
            "records_listed": len(records),
            "complete_triplets": sum(all((source / f"{r}.{e}").is_file() for e in ("hea", "dat", "atr")) for r in records),
            "checksum_entries": len(expected_hashes),
            "checksum_failures": checksum_failures,
            "wfdb_records_read": len(record_rows),
            "wfdb_failures": read_failures,
        },
        "summary": {
            "patients": len(patient_rows),
            "records": len(record_rows),
            "N": sum(row["N"] for row in record_rows),
            "V": sum(row["V"] for row in record_rows),
            "OTHER": sum(row["OTHER"] for row in record_rows),
            "sample_rates_hz": sorted(set(row["fs_hz"] for row in record_rows)),
            "lead_sets": sorted({tuple(row["signals"]) for row in record_rows}),
        },
        "annotation_alignment_screen": {
            "method": "lead II local max absolute excursion from +/-250 ms median within +/-100 ms",
            "count": int(offsets_array.size),
            "median_samples": float(np.median(offsets_array)) if offsets_array.size else None,
            "median_ms": float(1000 * np.median(offsets_array) / 257) if offsets_array.size else None,
            "p95_absolute_samples": float(np.percentile(np.abs(offsets_array), 95)) if offsets_array.size else None,
            "p95_absolute_ms": float(1000 * np.percentile(np.abs(offsets_array), 95) / 257) if offsets_array.size else None,
            "warning": "Screening only; do not shift annotations globally without morphology-stratified review.",
        },
        "records": record_rows,
        "patients": patient_rows,
        "proposed_split": {
            "seed": args.seed,
            "search": "100000 fixed-seed patient permutations; count balance only; no waveforms/model outputs",
            "score": split_score,
            "patient_overlap": False,
            **split_summary,
        },
        "v4_contract": {
            "labels": {"N": 0, "V": 1},
            "other_policy": "exclude; never map OTHER to NORMAL",
            "incart_lead": "II",
            "incart_resampling": "257 Hz to 250 Hz with scipy.signal.resample_poly(up=250, down=257)",
            "annotation_mapping": "round half up: floor(sample*250/257 + 0.5); validate on extracted windows",
            "window": "256 samples centered at mapped annotation: 128 before, 128 from center",
            "normalization": "per-window z-score with finite/epsilon guard, matching V1",
            "test_policy": "seal proposed INCART test patients; no architecture, checkpoint, or threshold selection",
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    split_artifact = {
        "schema": 1,
        "dataset": "INCART files/ current headers",
        "seed": args.seed,
        "selection": result["proposed_split"]["search"],
        "selection_score": split_score,
        "labels_used_for_balance": ["N", "V", "OTHER"],
        "waveforms_or_model_outputs_used": False,
        "patient_overlap": False,
        "other_policy": "exclude; never map OTHER to NORMAL",
        "train": split_summary["train"],
        "validation": split_summary["validation"],
        "test": split_summary["test"],
    }
    split_output.parent.mkdir(parents=True, exist_ok=True)
    split_output.write_text(json.dumps(split_artifact, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "integrity": result["integrity"], "summary": result["summary"],
                      "split_output": str(split_output), "split": split_summary,
                      "alignment": result["annotation_alignment_screen"]}, indent=2))


if __name__ == "__main__":
    main()
