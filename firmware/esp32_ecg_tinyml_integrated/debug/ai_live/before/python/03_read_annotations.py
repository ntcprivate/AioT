"""Read local Record 100 annotations and plot the first 10 seconds."""

from collections import Counter
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import wfdb


PROJECT_DIR = Path(__file__).resolve().parent.parent
RECORD_PATH = str(PROJECT_DIR / "mit-bih-arrhythmia-database-1.0.0" / "100")
OUTPUT_PATH = PROJECT_DIR / "plots" / "ecg_annotations_100.png"
DURATION_SECONDS = 10


def main():
    # Read all annotations to count N and V across the entire record.
    header = wfdb.rdheader(RECORD_PATH)
    annotations = wfdb.rdann(RECORD_PATH, "atr")
    counts = Counter(annotations.symbol)

    sample_end = min(int(DURATION_SECONDS * header.fs), header.sig_len)
    record = wfdb.rdrecord(RECORD_PATH, sampfrom=0, sampto=sample_end)
    ecg = record.p_signal[:, 0]
    time = np.arange(len(ecg)) / record.fs
    symbols = np.asarray(annotations.symbol)

    print("DOC NHAN ECG THANH CONG - MIT-BIH Record 100")
    print(f"Tan so lay mau: {record.fs:g} Hz")
    print(f"Toan bo record: {header.sig_len / header.fs:.2f} giay")
    print(f"Tong so annotation: {len(annotations.sample)}")
    print(f"N (Normal): {counts['N']}")
    print(f"V (PVC): {counts['V']}")
    print("Cac ky hieu khac:", dict(sorted(
        (symbol, count) for symbol, count in counts.items()
        if symbol not in ("N", "V")
    )))
    print(f"\nTrong {len(ecg) / record.fs:g} giay dau (0 <= t < 10):")

    fig, ax = plt.subplots(figsize=(14, 5))
    ax.plot(time, ecg, color="steelblue", linewidth=1, label=record.sig_name[0])
    for symbol, label, color, marker in (
        ("N", "N (Normal)", "green", "o"),
        ("V", "V (PVC)", "red", "X"),
    ):
        # Annotation sample indices refer to the original signal, starting at 0.
        samples = annotations.sample[
            (symbols == symbol) & (annotations.sample >= 0)
            & (annotations.sample < sample_end)
        ]
        print(f"{label}: {len(samples)}")
        print("  Thoi diem (giay):", ", ".join(
            f"{sample / record.fs:.3f}" for sample in samples
        ) or "khong co")
        ax.scatter(samples / record.fs, ecg[samples], color=color,
                   marker=marker, s=55, label=label, zorder=3)
        for sample in samples:
            ax.annotate(symbol, (sample / record.fs, ecg[sample]),
                        xytext=(0, 9), textcoords="offset points",
                        ha="center", color=color)

    ax.set(title="MIT-BIH Record 100 - Annotations (first 10 seconds)",
           xlabel="Time (seconds)", ylabel=f"ECG ({record.units[0]})",
           xlim=(0, len(ecg) / record.fs))
    ax.grid(True, alpha=0.3)
    ax.legend()
    fig.tight_layout()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUTPUT_PATH, dpi=150)
    print(f"\nDa luu bieu do: {OUTPUT_PATH}")
    plt.show()
    plt.close(fig)


if __name__ == "__main__":
    main()
