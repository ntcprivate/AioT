# V5 FP32 final evaluation

Thresholds remained frozen: V4 0.88 and V5 0.33. Validation values were reused without inference. Test was not used for model or threshold selection.

## MIT-BIH

| Split | Model | Accuracy | PVC Precision | Recall | F1 | TP | FP | FN | TN | Confusion matrix N/V |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Validation | V4 | 93.9241% | 65.0917% | 90.0769% | 75.5728% | 1,171 | 628 | 129 | 10,531 | `[[10531,628],[129,1171]]` |
| Validation | V5 | 99.3097% | 97.9463% | 95.3846% | 96.6485% | 1,240 | 26 | 60 | 11,133 | `[[11133,26],[60,1240]]` |
| Test | V5 | 84.5820% | 33.7363% | 95.5801% | 49.8703% | 865 | 1,699 | 40 | 8,675 | `[[8675,1699],[40,865]]` |

No pre-existing V4 MIT-BIH Test result was available, so V4 was not rerun.

## INCART

| Split | Model | Accuracy | PVC Precision | Recall | F1 | TP | FP | FN | TN | Confusion matrix N/V |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Validation | V4 | 98.6046% | 95.6435% | 92.9541% | 94.2796% | 2,876 | 131 | 218 | 21,785 | `[[21785,131],[218,2876]]` |
| Validation | V5 | 99.9600% | 99.8062% | 99.8707% | 99.8384% | 3,090 | 6 | 4 | 21,910 | `[[21910,6],[4,3090]]` |
| Test | V4 | 95.6802% | 86.5532% | 77.8511% | 81.9719% | 2,594 | 403 | 738 | 22,678 | `[[22678,403],[738,2594]]` |
| Test | V5 | 87.6955% | 50.6398% | 97.3890% | 66.6324% | 3,245 | 3,163 | 87 | 19,918 | `[[19918,3163],[87,3245]]` |

## Conclusion

V5 is much better on both Validation sets, but it does not outperform V4 on the independent INCART Test: F1 falls from 81.97% to 66.63% because false positives rise from 403 to 3,163. On MIT-BIH Test V5 preserves high recall but has 33.74% precision and 49.87% F1; no existing V4 Test result is available for a paired comparison. The Validation gains therefore did not generalize reliably.
