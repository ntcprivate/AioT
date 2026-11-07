
from pathlib import Path

import wfdb
import numpy as np
import matplotlib.pyplot as plt

# Duong dan thu muc goc cua du an
PROJECT_DIR = Path(__file__).resolve().parent.parent

# Duong dan du lieu MIT-BIH
DATA_DIR = (
    PROJECT_DIR / "mit-bih-arrhythmia-database-1.0.0"
)

RECORD_PATH = str(DATA_DIR / "100")

# Doc 10 giay ECG dau tien
record = wfdb.rdrecord(
    RECORD_PATH,
    sampfrom=0,
    sampto=3600
)

# Lay kenh ECG dau tien
ecg = record.p_signal[:, 0]

# Tan so lay mau
fs = record.fs

# Tao truc thoi gian
time = np.arange(len(ecg)) / fs

# In thong tin
print("DOC DU LIEU ECG THANH CONG!")
print("Tan so lay mau:", fs, "Hz")
print("So mau:", len(ecg))
print("Thoi luong:", len(ecg) / fs, "giay")

# Ve bieu do
plt.figure(figsize=(12, 5))
plt.plot(time, ecg, color="blue", linewidth=1)

plt.title("ECG - MIT-BIH Record 100")
plt.xlabel("Thoi gian (giay)")
plt.ylabel("Bien do ECG (mV)")
plt.grid(True)
plt.tight_layout()

# Luu hinh anh
plt.savefig(PROJECT_DIR / "plots" / "ecg_100.png")

# Hien thi
plt.show()
