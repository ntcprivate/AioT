"""Diagnostic Float32 inference on the same matched windows. No fit/save/tuning."""
from pathlib import Path
import hashlib
import numpy as np
import tensorflow as tf
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'firmware/esp32_ecg_tinyml_integrated/debug/final_ai_readiness'
model_path=ROOT/'models/ecg_cnn_best.keras';fingerprint=hashlib.sha256(model_path.read_bytes()).hexdigest()
tf.config.threading.set_inter_op_parallelism_threads(1);tf.config.threading.set_intra_op_parallelism_threads(1)
model=tf.keras.models.load_model(model_path,compile=False)
data=np.fromfile(OUT/'matched_normalized_float32.bin',dtype='<f4').reshape(-1,256,1)
scores=model.predict(data,batch_size=64,verbose=0).reshape(-1)
assert np.isfinite(scores).all();scores.astype('<f4').tofile(OUT/'matched_keras_scores.bin')
assert hashlib.sha256(model_path.read_bytes()).hexdigest()==fingerprint
print('Float32 probe, matched Validation only:',len(scores),'model SHA unchanged',fingerprint)
