# V4/V5/V6 — MIT-BIH and INCART

Retrospective comparison only. MIT-BIH/INCART Test had already been examined before V6.

## MITBIH

| Split | Model | Accuracy | Precision | Recall | F1 | TP | FP | FN | TN |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Validation | V4 | 93.9241% | 65.0917% | 90.0769% | 75.5728% | 1171 | 628 | 129 | 10531 |
| Validation | V5 | 99.3097% | 97.9463% | 95.3846% | 96.6485% | 1240 | 26 | 60 | 11133 |
| Validation | V6 | 99.1893% | 97.7689% | 94.3846% | 96.0470% | 1227 | 28 | 73 | 11131 |
| Test | V4 | 96.0635% | 69.8194% | 89.7238% | 78.5300% | 812 | 351 | 93 | 10023 |
| Test | V5 | 84.5820% | 33.7363% | 95.5801% | 49.8703% | 865 | 1699 | 40 | 8675 |
| Test | V6 | 92.9515% | 53.6569% | 89.1713% | 66.9988% | 807 | 697 | 98 | 9677 |

## INCART

| Split | Model | Accuracy | Precision | Recall | F1 | TP | FP | FN | TN |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Validation | V4 | 98.6046% | 95.6435% | 92.9541% | 94.2796% | 2876 | 131 | 218 | 21785 |
| Validation | V5 | 99.9600% | 99.8062% | 99.8707% | 99.8384% | 3090 | 6 | 4 | 21910 |
| Validation | V6 | 99.8201% | 99.8692% | 98.6749% | 99.2684% | 3053 | 4 | 41 | 21912 |
| Test | V4 | 95.6802% | 86.5532% | 77.8511% | 81.9719% | 2594 | 403 | 738 | 22678 |
| Test | V5 | 87.6955% | 50.6398% | 97.3890% | 66.6324% | 3245 | 3163 | 87 | 19918 |
| Test | V6 | 96.7062% | 87.0337% | 86.8247% | 86.9291% | 2893 | 431 | 439 | 22650 |

V6 Validation is reconstructed from its saved group-disjoint checkpoint/threshold partitions; no Validation inference was rerun.
V4/V5 Test values were reused from the fixed V5 diagnostic. Only V6 Test inference was performed.
