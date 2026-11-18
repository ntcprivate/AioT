# V4-V8 main-dataset retrospective comparison

Not an independent new evaluation: both Test sets were examined before V8.

## MITBIH

| Split | Model | Accuracy | Precision | Recall | F1 | TP | FP | FN | TN |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Development (checkpoint+threshold groups) | V4 | 93.9241% | 65.0917% | 90.0769% | 75.5728% | 1171 | 628 | 129 | 10531 |
| Development (checkpoint+threshold groups) | V5 | 99.3097% | 97.9463% | 95.3846% | 96.6485% | 1240 | 26 | 60 | 11133 |
| Development (checkpoint+threshold groups) | V6 | 99.1893% | 97.7689% | 94.3846% | 96.0470% | 1227 | 28 | 73 | 11131 |
| Development (checkpoint+threshold groups) | V7 | 97.8489% | 87.1758% | 93.0769% | 90.0298% | 1210 | 178 | 90 | 10981 |
| Development (checkpoint+threshold groups) | V8 | 99.3820% | 99.1955% | 94.8462% | 96.9721% | 1233 | 10 | 67 | 11149 |
| Test (retrospective) | V4 | 96.0635% | 69.8194% | 89.7238% | 78.5300% | 812 | 351 | 93 | 10023 |
| Test (retrospective) | V5 | 84.5820% | 33.7363% | 95.5801% | 49.8703% | 865 | 1699 | 40 | 8675 |
| Test (retrospective) | V6 | 92.9515% | 53.6569% | 89.1713% | 66.9988% | 807 | 697 | 98 | 9677 |
| Test (retrospective) | V7 | 90.5222% | 45.6568% | 95.2486% | 61.7257% | 862 | 1026 | 43 | 9348 |
| Test (retrospective) | V8 | 93.6342% | 56.4173% | 90.8287% | 69.6020% | 822 | 635 | 83 | 9739 |

## INCART

| Split | Model | Accuracy | Precision | Recall | F1 | TP | FP | FN | TN |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Development (checkpoint+threshold groups) | V4 | 98.6046% | 95.6435% | 92.9541% | 94.2796% | 2876 | 131 | 218 | 21785 |
| Development (checkpoint+threshold groups) | V5 | 99.9600% | 99.8062% | 99.8707% | 99.8384% | 3090 | 6 | 4 | 21910 |
| Development (checkpoint+threshold groups) | V6 | 99.8201% | 99.8692% | 98.6749% | 99.2684% | 3053 | 4 | 41 | 21912 |
| Development (checkpoint+threshold groups) | V7 | 99.9040% | 99.9025% | 99.3213% | 99.6110% | 3073 | 3 | 21 | 21913 |
| Development (checkpoint+threshold groups) | V8 | 99.7681% | 99.9014% | 98.2224% | 99.0548% | 3039 | 3 | 55 | 21913 |
| Test (retrospective) | V4 | 95.6802% | 86.5532% | 77.8511% | 81.9719% | 2594 | 403 | 738 | 22678 |
| Test (retrospective) | V5 | 87.6955% | 50.6398% | 97.3890% | 66.6324% | 3245 | 3163 | 87 | 19918 |
| Test (retrospective) | V6 | 96.7062% | 87.0337% | 86.8247% | 86.9291% | 2893 | 431 | 439 | 22650 |
| Test (retrospective) | V7 | 96.5282% | 82.9828% | 91.1765% | 86.8869% | 3038 | 623 | 294 | 22458 |
| Test (retrospective) | V8 | 91.4133% | 61.3240% | 86.4646% | 71.7559% | 2881 | 1817 | 451 | 21264 |

Only V8 Test inference was run. No threshold or model parameter was selected from Test.
