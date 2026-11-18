"""Prepare one record-disjoint V2 experiment using original Train only."""
from pathlib import Path
import hashlib,importlib.util,json
import numpy as np
import wfdb

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/cnn_v2'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    OUT.mkdir(parents=True,exist_ok=True)
    if (OUT/'config.json').exists():raise RuntimeError('V2 already prepared; refusing to replace an experiment')
    data=ROOT/'data/processed/mitbih_nv_250hz.npz';split=data.with_name('mitbih_split_indices.npz')
    with np.load(split,allow_pickle=False) as z:
        train=z['train_indices'];val=z['validation_indices'];test=z['test_indices']
        assert sha(data)==z['dataset_sha256'].item()
    with np.load(data,allow_pickle=False) as z:X=z['X'];y=z['y'];ids=z['record_ids'].astype('U')
    assert not set(train)&set(val) and not set(train)&set(test)
    train_records=sorted(set(ids[train]));assert not set(train_records)&set(ids[val]) and not set(train_records)&set(ids[test])
    group=lambda r:'patient_201_202' if r in ('201','202') else 'record_'+r
    groups=sorted({group(r) for r in train_records});rng=np.random.default_rng(42)
    dev_groups=set(rng.permutation(groups)[:int(np.ceil(len(groups)*.2))])
    fit=np.array([i for i in train if group(ids[i]) not in dev_groups]);dev=np.array([i for i in train if group(ids[i]) in dev_groups])
    assert set(y[fit])=={0,1} and set(y[dev])=={0,1}
    spec=importlib.util.spec_from_file_location('build_dataset',ROOT/'python/05_build_dataset.py');builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
    hard=np.zeros(len(y),dtype=bool);centers=np.full(len(y),-1,dtype=np.int64)
    # Reconstruct original extraction order to prove annotation-to-array alignment.
    for rid in train_records:
        path=ROOT/'mit-bih-arrhythmia-database-1.0.0'/rid
        row=dict.fromkeys(builder.FIELDS,0);row.update(record_id=rid,lead='',status='',reason='')
        rx,ry=builder.extract_record(path,row);ix=np.flatnonzero(ids==rid)
        np.testing.assert_allclose(rx,X[ix],rtol=2e-6,atol=1e-7);np.testing.assert_array_equal(ry,y[ix])
        assert row['n_nonfinite']==0
        a=wfdb.rdann(str(path),'atr');c=(a.sample.astype(np.int64)*25+18)//36;symbols=np.asarray(a.symbol)
        n=int(np.ceil(wfdb.rdheader(str(path)).sig_len*25/36))
        keep=np.isin(symbols,['N','V']) & (c>=128) & (c+128<=n)
        assert len(c[keep])==len(ix)
        centers[ix]=c[keep];pvc=c[symbols=='V']
        count=np.searchsorted(pvc,centers[ix]+128)-np.searchsorted(pvc,centers[ix]-128)
        hard[ix]=(y[ix]==0)&(count>0)
        print(rid,'N',sum(ry==0),'V',sum(ry==1),'hard_N',sum(hard[ix]),flush=True)
    local={int(i):j for j,i in enumerate(train)}
    fit_local=np.array([local[int(i)] for i in fit]);dev_local=np.array([local[int(i)] for i in dev])
    np.savez_compressed(OUT/'train_only.npz',X=X[train],y=y[train],ids=ids[train],hard=hard[train],centers=centers[train],global_indices=train,fit=fit_local,development=dev_local)
    config=dict(seed=42,epochs=30,patience=5,batch_size=64,learning_rate=.001,threshold=.52,hard_negative_multiplicity=4,
        training='from scratch, cloned V1 architecture, no V1 weights',monitor='development PVC F1 at fixed .52; maximum, patience5',
        export_rule='development F1 > V1 Float32, precision >= V1 Float32, recall >= V1 Float32 minus .02; exploratory selection only',
        hard_definition='central N and at least one V annotation inside [center-128,center+128) at250Hz',
        train_records=train_records,fit_records=sorted(set(ids[fit])),development_records=sorted(set(ids[dev])),development_groups=sorted(dev_groups),
        counts={name:dict(samples=len(ix),N=int(sum(y[ix]==0)),V=int(sum(y[ix]==1)),hard_N=int(sum(hard[ix]))) for name,ix in [('original_train',train),('fit',fit),('development',dev)]},
        provenance=dict(dataset_sha256=sha(data),original_split_sha256=sha(split)),
        limitations=['Record proxies except known 201/202 shared patient; other patient identity not independently verified.','V1 previously trained on all original Train, including new development; V1 development comparison is optimistic for V1.','Historical Validation is exploratory only; no Test prediction or raw Test record access.'])
    protected=[*list((ROOT/'models').glob('*')),*list((ROOT/'python').glob('0*.py')),data,split,ROOT/'results/optimized_threshold.json']
    protected+=list((ROOT/'firmware/esp32_ecg_tinyml_integrated/main').rglob('*'))+list((ROOT/'tools/ecg_monitor/ecg_monitor').glob('*.py'))
    (OUT/'protected_sha256.json').write_text(json.dumps({str(p.relative_to(ROOT)):sha(p) for p in protected if p.is_file()},indent=2))
    (OUT/'config.json').write_text(json.dumps(config,indent=2));print(json.dumps(config,indent=2),flush=True)
if __name__=='__main__':main()
