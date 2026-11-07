"""Step 4: extract annotated N/V beats from local MIT-BIH Record 100."""

from collections import Counter
from pathlib import Path
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.signal import resample_poly
import wfdb


ROOT = Path(__file__).resolve().parent.parent
RECORD = ROOT / "mit-bih-arrhythmia-database-1.0.0" / "100"
OUTPUT = ROOT / "data" / "processed" / "record100_beats_250hz.npz"
PLOT = ROOT / "plots" / "ecg_beats_100.png"
TARGET_FS = 250
HALF_WINDOW = 128
STD_EPS = 1e-8
LABELS = {"N": 0, "V": 1}


def main():
    for extension in (".hea", ".dat", ".atr"):
        path = RECORD.with_suffix(extension)
        if not path.is_file():
            raise FileNotFoundError(f"Khong tim thay du lieu cuc bo: {path}")

    record = wfdb.rdrecord(str(RECORD), channels=[0])
    annotations = wfdb.rdann(str(RECORD), "atr")
    if record.fs != 360:
        raise ValueError(f"Can ECG 360 Hz, nhung record co fs={record.fs}")
    ecg = record.p_signal[:, 0]
    if not np.isfinite(ecg).all():
        raise ValueError("Tin hieu goc chua NaN/Inf; khong tao du lieu dau ra.")

    # 250 / 360 = 25 / 36; polyphase resampling includes anti-alias filtering.
    ecg_250 = resample_poly(ecg, up=25, down=36)
    if not np.isfinite(ecg_250).all():
        raise ValueError("Tin hieu sau resample chua NaN/Inf.")
    # Round to the nearest sample at 250 Hz (half-sample ties round upward).
    centers = np.floor(annotations.sample.astype(np.float64) * 25 / 36 + 0.5).astype(np.int64)
    beats, labels = [], []
    skipped_boundary = Counter()
    low_std = Counter()
    ignored = Counter()
    for center, symbol in zip(centers, annotations.symbol):
        if symbol not in LABELS:
            ignored[symbol] += 1
            continue
        start, end = center - HALF_WINDOW, center + HALF_WINDOW
        if start < 0 or end > len(ecg_250):
            skipped_boundary[symbol] += 1
            continue
        beat = ecg_250[start:end].astype(np.float64, copy=True)
        std = float(beat.std())
        if std < STD_EPS:
            low_std[symbol] += 1
        # Flooring the denominator also handles a constant beat safely.
        beat = (beat - beat.mean()) / max(std, STD_EPS)
        beats.append(beat.astype(np.float32))
        labels.append(LABELS[symbol])

    X = np.asarray(beats, dtype=np.float32).reshape(-1, 256, 1)
    y = np.asarray(labels, dtype=np.int32)
    has_nan, has_inf = bool(np.isnan(X).any()), bool(np.isinf(X).any())
    if has_nan or has_inf:
        raise ValueError("Du lieu trich xuat chua NaN/Inf; khong luu.")
    if len(y) == 0:
        raise ValueError("Khong co nhip N/V hop le de luu.")

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(OUTPUT, X=X, y=y)
    # Verify the actual saved artifact, including dtype and complete contents.
    with np.load(OUTPUT, allow_pickle=False) as saved:
        if (saved["X"].dtype != np.float32 or saved["y"].dtype != np.int32
                or not np.array_equal(saved["X"], X)
                or not np.array_equal(saved["y"], y)):
            raise ValueError("File NPZ doc lai khong khop du lieu da tao.")

    print(f"Resample: {record.fs:g} -> {TARGET_FS} Hz (25/36)")
    print(f"Tong so nhip trich xuat: {len(y)}")
    print(f"N (0): {np.count_nonzero(y == 0)}")
    pvc_count = int(np.count_nonzero(y == 1))
    print(f"V (1): {pvc_count}")
    print(f"X: shape={X.shape}, dtype={X.dtype}")
    print(f"y: shape={y.shape}, dtype={y.dtype}")
    print(f"NaN: {has_nan}; Inf: {has_inf}")
    print(f"Bo qua nhan khac: {dict(ignored)}")
    print(f"Loai do gan bien: {dict(skipped_boundary)}")
    print(f"Nhip co std < {STD_EPS}: {dict(low_std)}")
    if pvc_count < 5:
        print(f"Record 100 chi co {pvc_count} PVC hop le; khong tao du lieu gia.")
    print(f"Da luu va doc lai thanh cong: {OUTPUT}")

    fig, axes = plt.subplots(2, 1, figsize=(12, 7), sharex=True)
    time = (np.arange(256) - HALF_WINDOW) / TARGET_FS
    for ax, (symbol, label) in zip(axes, LABELS.items()):
        indices = np.flatnonzero(y == label)[:3]
        for index in indices:
            ax.plot(time, X[index, :, 0], label=f"Beat {index}", alpha=0.8)
        if len(indices):
            ax.legend()
        else:
            ax.text(0.5, 0.5, "No annotated beats available", ha="center",
                    transform=ax.transAxes)
        ax.axvline(0, color="black", linestyle="--", alpha=0.5)
        ax.set_title(f"{symbol} ({'Normal' if label == 0 else 'PVC'}) - first {len(indices)} examples")
        ax.set_ylabel("Normalized amplitude")
        ax.grid(alpha=0.3)
    axes[-1].set_xlabel("Time relative to annotation (seconds)")
    fig.suptitle("MIT-BIH Record 100 - 256 samples per beat at 250 Hz")
    fig.tight_layout()
    PLOT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(PLOT, dpi=150)
    plt.close(fig)
    print(f"Da luu bieu do: {PLOT}")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError) as error:
        print(f"LOI: {error}", file=sys.stderr)
        sys.exit(1)
