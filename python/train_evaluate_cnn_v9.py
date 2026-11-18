from __future__ import annotations

import hashlib
import json
import math
import os
import random
import shutil
from pathlib import Path

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
os.environ.setdefault("TF_ENABLE_ONEDNN_OPTS", "0")

import numpy as np
import tensorflow as tf
from sklearn.metrics import average_precision_score


ROOT = Path(__file__).resolve().parents[1]
MIT_PATH = ROOT / "data/processed/mitbih_nv_250hz.npz"
MIT_SPLIT_PATH = ROOT / "data/processed/mitbih_split_indices.npz"
INC_PATH = ROOT / "data/processed/incart_v4_250hz.npz"
V6_CONFIG = ROOT / "results/cnn_v6/config.json"
V8_EVAL = ROOT / "results/cnn_v8/evaluation.json"
MODEL_DIR = ROOT / "models/v9"
RESULT_DIR = ROOT / "results/cnn_v9"
SEED, BATCH_SIZE, MAX_EPOCHS, PATIENCE = 42, 128, 25, 5
THRESHOLDS = np.round(np.arange(0.01, 0.9901, 0.005), 3)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_v4(name: str) -> tf.keras.Model:
    model = tf.keras.Sequential([
        tf.keras.layers.Input((256, 1)),
        tf.keras.layers.Conv1D(8, 5, activation="relu"),
        tf.keras.layers.MaxPooling1D(2),
        tf.keras.layers.Conv1D(16, 5, activation="relu"),
        tf.keras.layers.MaxPooling1D(2),
        tf.keras.layers.GlobalAveragePooling1D(),
        tf.keras.layers.Dense(8, activation="relu"),
        tf.keras.layers.Dense(1, activation="sigmoid"),
    ], name=name)
    if model.count_params() != 849:
        raise RuntimeError(f"V4 architecture contract failed: {model.count_params()}")
    return model


def metrics(y: np.ndarray, scores: np.ndarray, threshold: float) -> dict:
    pred = scores >= threshold
    tp = int(np.sum((y == 1) & pred)); tn = int(np.sum((y == 0) & ~pred))
    fp = int(np.sum((y == 0) & pred)); fn = int(np.sum((y == 1) & ~pred))
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    normal = int(np.sum(y == 0))
    return {"accuracy": (tp + tn) / len(y), "precision": precision, "recall": recall, "f1": f1,
            "pr_auc": float(average_precision_score(y, scores)), "TP": tp, "FP": fp, "FN": fn, "TN": tn,
            "fp_per_1000_normal": fp * 1000.0 / normal if normal else 0.0, "threshold": float(threshold)}


class TrainSequence(tf.keras.utils.Sequence):
    def __init__(self, x, y, weights, augment: bool):
        super().__init__(); self.x, self.y, self.weights, self.augment = x, y, weights, augment
        self.epoch = 0; self.order = np.arange(len(y)); self.on_epoch_end()

    def __len__(self):
        return math.ceil(len(self.y) / BATCH_SIZE)

    def __getitem__(self, batch_index):
        indices = self.order[batch_index * BATCH_SIZE:(batch_index + 1) * BATCH_SIZE]
        result = self.x[indices].copy()
        if self.augment:
            rng = np.random.default_rng(SEED + self.epoch * 100_003 + batch_index)
            position = np.arange(256, dtype=np.float32); time = position / 250.0
            qrs_mask = np.exp(-0.5 * ((position - 128.0) / 32.0) ** 2)[:, None]
            for index in range(len(result)):
                if rng.random() < 0.50:
                    shift = int(rng.integers(-4, 5))
                    if shift:
                        padded = np.pad(result[index], ((4, 4), (0, 0)), mode="reflect")
                        result[index] = padded[4-shift:4-shift+256]
                if rng.random() < 0.45:
                    gain = float(rng.uniform(0.90, 1.10))
                    result[index] *= 1.0 + (gain - 1.0) * qrs_mask
                if rng.random() < 0.40:
                    amp, freq, phase = rng.uniform(0.005, 0.04), rng.uniform(0.25, 0.70), rng.uniform(0, 2*np.pi)
                    result[index, :, 0] += amp * np.sin(2*np.pi*freq*time + phase)
                mean, std = float(result[index].mean()), float(result[index].std())
                result[index] = (result[index] - mean) / max(std, 1e-8)
        return result.astype(np.float32), self.y[indices], self.weights[indices]

    def on_epoch_end(self):
        self.epoch += 1; self.order = np.random.default_rng(SEED + self.epoch).permutation(len(self.y))


class Selector(tf.keras.callbacks.Callback):
    def __init__(self, x, y, path: Path):
        super().__init__(); self.x, self.y, self.path = x, y, path
        self.best, self.best_epoch, self.wait, self.rows = -1.0, 0, 0, []

    def on_epoch_end(self, epoch, logs=None):
        scores = self.model.predict(self.x, batch_size=512, verbose=0).reshape(-1)
        ap = float(average_precision_score(self.y, scores))
        self.rows.append({"epoch": epoch+1, "checkpoint_pr_auc": ap,
                          "loss": float((logs or {}).get("loss", np.nan))})
        if ap > self.best + 1e-12:
            self.best, self.best_epoch, self.wait = ap, epoch+1, 0; self.model.save(self.path)
        else: self.wait += 1
        print(f" checkpoint_pr_auc={ap:.6f}")
        if self.wait >= PATIENCE: self.model.stop_training = True


def group_weights(y: np.ndarray, groups: np.ndarray) -> np.ndarray:
    result = np.ones(len(y), dtype=np.float64)
    for label in (0, 1):
        mask = y == label; unique, counts = np.unique(groups[mask], return_counts=True)
        mapping = {group: 1.0/math.sqrt(int(count)) for group, count in zip(unique, counts)}
        values = np.asarray([mapping[group] for group in groups[mask]])
        result[mask] = values / values.mean()
    counts = np.bincount(y, minlength=2)
    class_weight = np.asarray([len(y)/(2*counts[label]) for label in y])
    return np.minimum(result * class_weight, 8.0).astype(np.float32)


def choose_threshold(y_inc, scores_inc, y_mit, scores_mit):
    rows = []
    for threshold in THRESHOLDS:
        inc = metrics(y_inc, scores_inc, float(threshold)); mit = metrics(y_mit, scores_mit, float(threshold))
        combined_y = np.concatenate([y_inc, y_mit]); combined_scores = np.concatenate([scores_inc, scores_mit])
        combined = metrics(combined_y, combined_scores, float(threshold))
        rows.append({"threshold": float(threshold), "min_dataset_f1": min(inc["f1"], mit["f1"]),
                     "macro_f1": (inc["f1"] + mit["f1"])/2, "macro_precision": (inc["precision"]+mit["precision"])/2,
                     "INCART": inc, "MITBIH": mit, "combined": combined})
    return max(rows, key=lambda row: (row["min_dataset_f1"], row["macro_f1"], row["macro_precision"], row["threshold"]))


def train_variant(name, augment, x_train, y_train, weights, x_cp, y_cp):
    tf.keras.backend.clear_session(); random.seed(SEED); np.random.seed(SEED); tf.keras.utils.set_random_seed(SEED)
    model = build_v4(f"ecg_nv_cnn_v9_{name.lower()}"); path = MODEL_DIR / f"ecg_cnn_v9_{name.lower()}_best.keras"
    model.compile(optimizer=tf.keras.optimizers.Adam(0.001), loss="binary_crossentropy")
    selector = Selector(x_cp, y_cp, path)
    model.fit(TrainSequence(x_train, y_train, weights, augment), epochs=MAX_EPOCHS, verbose=2,
              callbacks=[selector, tf.keras.callbacks.TerminateOnNaN()])
    return path, selector


def main():
    if MODEL_DIR.exists() or RESULT_DIR.exists(): raise RuntimeError("V9 artifacts exist; refusing retrain")
    MODEL_DIR.mkdir(parents=True); RESULT_DIR.mkdir(parents=True)
    tf.config.threading.set_inter_op_parallelism_threads(1); tf.config.threading.set_intra_op_parallelism_threads(2)
    tf.config.experimental.enable_op_determinism()
    mit=np.load(MIT_PATH); split=np.load(MIT_SPLIT_PATH); inc=np.load(INC_PATH)
    mit_train=split["train_indices"]; mit_dev=split["validation_indices"]
    inc_train=inc["split"].astype(str)=="train"; inc_dev=inc["split"].astype(str)=="validation"
    x_train=np.concatenate([mit["X"][mit_train],inc["X"][inc_train]])
    y_train=np.concatenate([mit["y"][mit_train],inc["y"][inc_train]]).astype(np.int32)
    groups=np.concatenate([np.char.add("MIT:",mit["record_ids"][mit_train].astype(str)),
                           np.char.add("INC:",inc["patient_ids"][inc_train].astype(str))])
    weights=group_weights(y_train,groups)
    partition=json.loads(V6_CONFIG.read_text(encoding="utf-8"))["development_partition"]
    inc_x,inc_y,inc_g=inc["X"][inc_dev],inc["y"][inc_dev].astype(np.int32),inc["patient_ids"][inc_dev].astype(str)
    mit_x,mit_y,mit_g=mit["X"][mit_dev],mit["y"][mit_dev].astype(np.int32),mit["record_ids"][mit_dev].astype(str)
    inc_cp=np.isin(inc_g,partition["INCART_checkpoint_patients"]);inc_th=np.isin(inc_g,partition["INCART_threshold_patients"])
    mit_cp=np.isin(mit_g,partition["MITBIH_checkpoint_records"]);mit_th=np.isin(mit_g,partition["MITBIH_threshold_records"])
    x_cp=np.concatenate([inc_x[inc_cp],mit_x[mit_cp]]);y_cp=np.concatenate([inc_y[inc_cp],mit_y[mit_cp]])
    variants={}
    for name,augment in (("A",False),("B",True)):
        path,selector=train_variant(name,augment,x_train,y_train,weights,x_cp,y_cp)
        model=tf.keras.models.load_model(path,compile=False)
        score_inc=model.predict(inc_x[inc_th],batch_size=512,verbose=0).reshape(-1)
        score_mit=model.predict(mit_x[mit_th],batch_size=512,verbose=0).reshape(-1)
        threshold=choose_threshold(inc_y[inc_th],score_inc,mit_y[mit_th],score_mit)
        variants[name]={"path":path,"selector":selector,"threshold_selection":threshold,
                        "threshold":threshold["threshold"]}

    prior=json.loads(V8_EVAL.read_text(encoding="utf-8"))["comparison_same_development_partitions"]
    subsets={"checkpoint_INCART":(inc_x[inc_cp],inc_y[inc_cp]),"threshold_INCART":(inc_x[inc_th],inc_y[inc_th]),
             "checkpoint_MITBIH":(mit_x[mit_cp],mit_y[mit_cp]),"threshold_MITBIH":(mit_x[mit_th],mit_y[mit_th])}
    comparison={}
    for subset,(x,y) in subsets.items():
        comparison[subset]={name:prior[subset][name] for name in ("V4","V6")}
        for name,value in variants.items():
            model=tf.keras.models.load_model(value["path"],compile=False)
            scores=model.predict(x,batch_size=512,verbose=0).reshape(-1)
            comparison[subset][f"V9-{name}"]=metrics(y,scores,value["threshold"])
    # Stable selection: maximize the worst dataset F1 averaged over checkpoint/threshold partitions.
    selection={}
    for name in ("A","B"):
        key=f"V9-{name}"
        dataset_f1={dataset:np.mean([comparison[f"checkpoint_{dataset}"][key]["f1"],comparison[f"threshold_{dataset}"][key]["f1"]])
                    for dataset in ("INCART","MITBIH")}
        selection[name]={"dataset_mean_f1":dataset_f1,"min_dataset_mean_f1":min(dataset_f1.values()),
                         "macro_dataset_mean_f1":float(np.mean(list(dataset_f1.values())))}
    selected_name=max(selection,key=lambda name:(selection[name]["min_dataset_mean_f1"],selection[name]["macro_dataset_mean_f1"]))
    selected_path=variants[selected_name]["path"]
    shutil.copy2(selected_path,MODEL_DIR/"ecg_cnn_v9_best.keras")
    result={"architecture":"V4 baseline","parameters":849,"selected_variant":f"V9-{selected_name}",
            "selected_threshold":variants[selected_name]["threshold"],"selection":selection,
            "variants":{name:{"augmentation":name=="B","threshold":value["threshold"],
                "threshold_selection":value["threshold_selection"],"best_epoch":value["selector"].best_epoch,
                "epochs_run":len(value["selector"].rows),"checkpoint_pr_auc":value["selector"].best,
                "checkpoint_sha256":sha256(value["path"])} for name,value in variants.items()},
            "comparison_same_development_partitions":comparison,"test_used":False,
            "selected_checkpoint_sha256":sha256(MODEL_DIR/"ecg_cnn_v9_best.keras")}
    config={"seed":SEED,"architecture":"V4 849 parameters","group_weighting":"class weight * inverse sqrt within-class group count",
            "groups":{"INCART":"patient","MITBIH":"record proxy"},"variants":{"A":"no augmentation","B":"shift +/-4; central gain 0.9-1.1; baseline wander"},
            "checkpoint":"PR-AUC checkpoint groups","threshold":"maximize min(INCART F1,MITBIH F1), then macro F1 on threshold groups",
            "development_partition":partition,"test_used":False}
    (RESULT_DIR/"config.json").write_text(json.dumps(config,indent=2)+"\n",encoding="utf-8")
    (RESULT_DIR/"evaluation.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    lines=["# CNN V9", "",f"Selected: V9-{selected_name}; threshold: {variants[selected_name]['threshold']:.3f}.",""]
    for subset in subsets:
        lines += [f"## {subset}","","| Model | Precision | Recall | F1 | FP | FN |","|---|---:|---:|---:|---:|---:|"]
        for name,row in comparison[subset].items():lines.append(f"| {name} | {100*row['precision']:.4f}% | {100*row['recall']:.4f}% | {100*row['f1']:.4f}% | {row['FP']} | {row['FN']} |")
        lines.append("")
    lines += ["No Test dataset was used."]
    (RESULT_DIR/"report.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    (RESULT_DIR/"locked.json").write_text(json.dumps({"locked":True,"selected_variant":f"V9-{selected_name}","threshold":variants[selected_name]["threshold"],"sha256":result["selected_checkpoint_sha256"],"test_used":False},indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"selected":result["selected_variant"],"threshold":result["selected_threshold"],"variants":result["variants"],"comparison":comparison},indent=2))


if __name__=="__main__":main()
