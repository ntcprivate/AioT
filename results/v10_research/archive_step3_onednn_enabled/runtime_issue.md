# V10-B runtime issue

Training stopped after detecting a runtime configuration mismatch. Initial launch imported TensorFlow before setting TF_ENABLE_ONEDNN_OPTS=0; launch logs explicitly reported oneDNN enabled. Editing the source after launch did not change the running process. Step 1/2 set this variable before importing TensorFlow.

PIDs 44156 and 16904 were parent/child, not independent training runs. PID 44156 was the venv launcher (CPU 0); PID 16904 performed training.

Checkpoint config inspection confirms CentralZScore exists and SpatialDropout does not. The v10a filenames come from the reused Step-2 runner, scoped to step3; Step-2 artifacts were not overwritten.

Existing Step-3 artifacts are preserved but must not be resumed into a run with oneDNN disabled, since that would mix runtime configurations. No comparative result is accepted pending a decision on handling this interrupted run.
