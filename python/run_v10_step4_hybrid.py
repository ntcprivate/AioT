import os
os.environ['TF_ENABLE_ONEDNN_OPTS'] = '0'
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'
import json
import tensorflow as tf
import run_v10_step2_v10a as runner

def build(name='v10c'):
    L = tf.keras.layers
    x = L.Input((256, 1))
    c = L.Cropping1D((64, 64))(x)
    c = L.Conv1D(8, 5, activation='relu')(c)
    c = L.MaxPooling1D(2)(c)
    c = L.Conv1D(12, 5, activation='relu')(c)
    c = L.MaxPooling1D(2)(c)
    c = L.GlobalAveragePooling1D()(c)
    c = L.Dense(8, activation='relu')(c)
    w = L.Conv1D(8, 5, activation='relu')(x)
    w = L.MaxPooling1D(2)(w)
    w = L.Conv1D(16, 5, activation='relu')(w)
    w = L.MaxPooling1D(2)(w)
    w = L.GlobalAveragePooling1D()(w)
    w = L.Dense(8, activation='relu')(w)
    z = L.Concatenate()([c, w])
    z = L.Dense(12, activation='relu')(z)
    model = tf.keras.Model(x, L.Dense(1, activation='sigmoid')(z), name=name)
    assert model.count_params() == 1701
    return model

if __name__ == '__main__':
    runner.STEP2_DIR = runner.ROOT / 'results/v10_research/step4_hybrid'
    runner.CKPT_DIR = runner.STEP2_DIR / 'checkpoints'
    runner.build_v10a = build
    runner.STEP2_DIR.mkdir(parents=True, exist_ok=True)
    config = {'architecture': 'V4 context conv8k5-pool2-conv16k5-pool2-GAP-dense8; V6 center crop128-conv8k5-pool2-conv12k5-pool2-GAP-dense8; fusion dense12-sigmoid', 'parameters':1701, 'tensorflow':tf.__version__, 'onednn':'0', 'folds_sha256':runner.sha256_file(runner.STEP1_DIR/'folds_split.json'), 'adaptive_limit':'Prior outer CV influenced architecture; exploratory adaptive comparison, not independent confirmation'}
    (runner.STEP2_DIR/'design_locked.json').write_text(json.dumps(config, indent=2))
    runner.main()
    p = runner.STEP2_DIR/'evaluation.json'
    r = json.loads(p.read_text())
    r['V10-C'] = r.pop('V10-A')
    r['protocol'].update(config)
    p.write_text(json.dumps(r, indent=2))
    (runner.STEP2_DIR/'config.json').write_text(json.dumps(r['protocol'], indent=2))
