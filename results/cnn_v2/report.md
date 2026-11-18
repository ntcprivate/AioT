# CNN V2 ? m?t c?u h?nh hard-negative, 2026-11-07

**Gi? V1 tr?n ESP32. V2 ch?a c?i thi?n; kh?ng xu?t INT8, kh?ng tri?n khai v? kh?ng m? th?m th? nghi?m.**
Model ?ng vi?n ???c l?u ri?ng t?i `models/v2/ecg_cnn_v2_best.keras` (47.482 bytes,
weights Float32, 849 tham s?). Kh?ng ghi ?? V1, kh?ng flash/COM, kh?ng s?a firmware,
GUI, detector, threshold 0,52 ho?c ch?y c?c b? ki?m th? firmware/GUI c?.

## Train v? l?a ch?n

Train g?c: 58.134 m?u, 53.216 N / 4.918 V; **1.586 hard negatives**.
Nh?n v?n thu?c nh?p gi?a; hard negative l? N c? annotation V trong
`[center?128, center+128)` ? 250 Hz. ?? ??i chi?u th? t? annotation/nh?n v?i
pipeline b??c 5. Input hu?n luy?n l?y nguy?n t? NPZ ?? l?u, kh?ng ??i preprocessing.
T?i t?o t?n hi?u ch? ?? x?c minh mapping; so s?nh float c? dung sai s? h?c nh?
`rtol=2e-6, atol=1e-7` gi?a m?i tr??ng NumPy, kh?ng s?a gi? tr? NPZ.

T?ch development b?ng permutation nh?m seed42 duy nh?t, 20% s? nh?m Train:
**111, 207, 217, 220, 221, 231**; 5.207 m?u (4.541 N/666 V), 361 hard negatives.
Train-fit: 52.927 m?u (48.675 N/4.252 V), 1.225 hard negatives. 201/202 gi? c?ng
nh?m; c?c record kh?c l? proxy, ch?a x?c minh th?m danh t?nh b?nh nh?n.

M?i epoch ch?a m?i Train-fit m?t l?n, th?m ba l?n m?i hard negative: 56.602 l??t,
4.900 l??t hard negative (8,66% t?ng l??t); gi? m?i NORMAL th??ng/PVC, kh?ng SMOTE.
Class weights ch? t? Train-fit: N=0.543677, V=6.223777.
Gi? ki?n tr?c V1, clone architecture v? **kh?i t?o m?i**, kh?ng d?ng weights V1.
Adam 0,001, batch64, seed42, deterministic CPU, t?i ?a30 epoch, patience5;
ch?n epoch c? development PVC F1 cao nh?t t?i threshold0,52.
**Best epoch15; d?ng epoch20; 106.6 gi?y.** Kh?ng th? c?u h?nh th? hai.

?i?u ki?n xu?t ch?t tr??c train: F1 dev > V1 Float32, precision kh?ng gi?m,
recall gi?m t?i ?a2 ?i?m ph?n tr?m; ??y l? quy t?c ch?n th? nghi?m, kh?ng ph?i
nghi?m thu y t?. V2 kh?ng ??t ngay ?i?u ki?n F1/precision n?n kh?ng xu?t.

|Train-development|PVC Precision|Recall|F1|N?V|V?N|
|---|---:|---:|---:|---:|---:|
|V1 Float32|100.00%|99.55%|99.77%|0|3|
|V2 Float32|98.81%|99.85%|99.33%|8|1|

**Gi?i h?n quan tr?ng:** V1 ?? h?c development n?y khi train tr?n to?n Train c?;
V2 kh?ng h?c c?c record development. Baseline dev do ?? thi?n l?i cho V1,
kh?ng ph?i so s?nh t?ng qu?t h?a ??c l?p c?n b?ng. Kh?ng train th?m m?t baseline
kh?c ?? v??t ph?m vi m?t c?u h?nh V2. Validation t?ng ph?n t?ch l?i kh?ng tham gia
fit/early stopping/ch?n checkpoint/quy?t ??nh xu?t. Kh?ng inference tr?n Test.

## Validation c? ? tham kh?o sau khi ??ng b?ng V2

T?i d?ng c?a s?/events/safety admission detector2B v? greedy matching ?12 m?u
c?, kh?ng ch?y l?i detector ho?c ??i tolerance. 16.775 c?a s?, 12.378 matched N/V;
66 N v?24 V b? b? tr??c CNN gi? ri?ng. F1 CNN kh?ng so tr?c ti?p v?i F1 end-to-end.

|Matched CNN|PVC Precision|Recall|F1|N?V|V?N|Recall N|
|---|---:|---:|---:|---:|---:|---:|
|V1_INT8|72.72%|89.35%|80.18%|428|136|96.14%|
|V1_FLOAT32|70.77%|89.66%|79.10%|473|132|95.74%|
|V2_FLOAT32|56.93%|96.16%|71.52%|929|49|91.63%|

Confusion matrices h?ng/c?t N,V: V1 INT8 `[[10673,428],[136,1141]]`;
V1 Float32 `[[10628,473],[132,1145]]`; V2 Float32 `[[10172,929],[49,1228]]`.

|End-to-end N/V c?ng protocol|PVC Precision|Recall|F1|FP g?m unmatched|FN g?m miss|Unmatched PVC|
|---|---:|---:|---:|---:|---:|---:|
|V1_INT8|71.76%|87.70%|78.93%|449|160|21|
|V1_FLOAT32|69.86%|88.01%|77.89%|494|156|21|
|V2_FLOAT32|56.25%|94.39%|70.49%|955|73|26|

So s?nh c?ng ??nh d?ng **Float32 ? Float32**: F1 end-to-end77,89%?70,49%,
precision69,86%?56,25%; recall88,01%?94,39%. M?c ?85% ch?a ??t.
V1 INT8 F1 end-to-end78,93% ch? l? baseline INT8 ri?ng, kh?ng b? nh?m v?i F1 CNN.
4.352 c?a s? nh?n ngo?iN/V gi? ri?ng (kh?ng relabel N): V1 INT8 d? ?o?n897 PVC,
V1 Float32980, V2 Float32908; precision b?ng tr?n kh?ng ??i di?n to?n ECG/OOD.

|NORMAL c? PVC l?n c?n, matched|N?V|Recall N c?a nh?m|
|---|---:|---:|
|V1_INT8|402 / 807|50.19%|
|V1_FLOAT32|447 / 807|44.61%|
|V2_FLOAT32|580 / 807|28.13%|

|Record|V1 Float32 N?V / V?N|V2 Float32 N?V / V?N|
|---|---:|---:|
|115|0/0|2/0|
|118|0/12|0/12|
|121|7/0|60/0|
|210|22/42|64/20|
|214|0/57|0/13|
|233|444/20|795/3|
|234|0/1|8/1|

## K?t lu?n v? model INT8

Hard-negative oversampling4x v?i CNN hi?n t?i **kh?ng gi?i quy?t l?i context**:
nh?m NORMAL g?nPVC sai447?580 v? FP ngo?i nh?m c?ng t?ng26?349 tr?n Validation
c?. Sai t?p trung ?233 nh?ng lan sang121/210. FN gi?m m?nh cho th?y m? h?nh m?i
thi?n v? d? ?o?n PVC h?n. ??y l? b?ng ch?ng k?t qu?, ch?a ch?ng minh ri?ng
class weights, seed hay GlobalAveragePooling l? nguy?n nh?n nh?n qu?. Ki?n tr?c
v?n t?ng h?p to?n c?a s?, kh?c bi?t record/context c?n l?n; kh?ng tuning b?ng
nh?ng k?t qu? n?y.

V2 kh?ng ??t l?a ch?n Train-dev, n?n **INT8/TFLite Float32/parity/arena V2: N/A,
kh?ng xu?t theo ?i?u ki?n y?u c?u**. Kh?ng c? s? ?o Float32?INT8 V2 ?? b?o c?o,
kh?ng d?ng parity V1 thay th?. V1 INT8 v?n8.560 bytes; arena V1 t?ng ?o6.124 bytes
trong c?p ph?t64KiB, kh?ng ???c coi l? s? ?o V2. Keras Float32 V2 ???c gi? ?? t?i l?p.
Kh?ng c? cohort ??c l?p m?i ???c x?c l?p; kh?ng tuy?n b? t?ng qu?t h?a ??c l?p.

4 ki?m th? li?n quan PASS: t?ch nh?m/leakage, b?o to?n ?a d?ng v? tr?ng s? sampling,
metric/ph?n bi?t l?i tr??cCNN, hash60 file V1/firmware/GUI/dataset/split b?t bi?n.
Root `.venv` h?ng ???ng d?n Python3.11; d?ng m?i tr??ng x? l? d? li?u hi?n c? v?
`.venv_reference` Python3.13.7 / TF2.21.0 / NumPy2.5.4, kh?ng c?i/thay m?i tr??ng.
TensorFlow ghi c?nh b?o GPU Windows/thu?c t?nh dataset kh?ng nh?n di?n; PowerShell
wrapper b?o NativeCommandError t? stderr. Kh?ng c? Python traceback trong train;
history20 epoch h?u h?n, checkpoint reload v? ??nh gi? sau train ho?n t?t exit0.
Kh?ng ch?y l?i train ?? thay ??i k?t qu?.

Artifacts: `config.json`, `history.json`, `training.json`, `evaluation.json`,
`comparison.csv`, `protected_sha256.json`, log/tests v? prediction arrays trong
`results/cnn_v2/`. Script m?i: `python/prepare_cnn_v2.py`, `train_cnn_v2.py`,
`cnn_v2_common.py`, `prepare_cnn_v2_evaluation.py`, `evaluate_cnn_v2.py`, `test_cnn_v2.py`.
D?ng t?i b?o c?o; **gi? V1, ch?a tri?n khai V2 l?n ESP32**.
