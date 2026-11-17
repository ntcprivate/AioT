"""Select fixtures from already-PASS V4 host parity; no quantization or inference rerun."""
import json,hashlib
from pathlib import Path
import numpy as np
import wfdb
from scipy.signal import resample_poly
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/cnn_v4/esp32_golden_test';ASSETS=OUT/'firmware/main/assets'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 OUT.mkdir(parents=True,exist_ok=True);ASSETS.mkdir(parents=True,exist_ok=True)
 if (OUT/'fixtures.json').exists():raise RuntimeError('Fixtures already prepared; refusing overwrite')
 report=json.loads((ROOT/'results/cnn_v4/int8_conversion.json').read_text());model=ROOT/'models/v4/ecg_cnn_v4_int8.tflite';assert model.stat().st_size==8688 and sha(model)==report['int8_sha256']
 assert sha(ROOT/'models/v4/ecg_cnn_v4_best.keras')==report['source_sha256']
 q=np.fromfile(ROOT/'results/cnn_v4/v4_validation_inputs_int8.bin',np.int8).reshape(-1,256);codes=np.fromfile(ROOT/'results/cnn_v4/v4_validation_python_codes.bin',np.int8);host=np.fromfile(ROOT/'results/cnn_v4/v4_validation_tflm_host_codes.bin',np.int8);np.testing.assert_array_equal(codes,host);assert len(q)==len(codes)==25010
 inc=np.load(ROOT/'data/processed/incart_v4_250hz.npz');idx=np.flatnonzero(inc['split']=='validation');y=inc['y'][idx];chosen=[]
 for label in [0,1]:
  at=np.flatnonzero(y==label);chosen+=at[:4].tolist();chosen+=at[np.argsort(abs(codes[at].astype(int)-98),kind='stable')[:4]].tolist();chosen+=at[np.argsort(codes[at],kind='stable')[:2]].tolist();chosen+=at[np.argsort(-codes[at].astype(int),kind='stable')[:2]].tolist()
 chosen=np.unique(chosen);xs=inc['X'][idx[chosen]];raw=[];fixtures=[];signals={}
 for j,pos in enumerate(chosen):
  source=int(idx[pos]);rec=str(inc['record_ids'][source]);center=int(inc['centers_250hz'][source])
  if rec not in signals:
   h=wfdb.rdheader(str(ROOT/'files'/rec));ch=[s.strip().upper() for s in h.sig_name].index('II');s=wfdb.rdrecord(str(ROOT/'files'/rec),channels=[ch],return_res=32).p_signal[:,0];signals[rec]=resample_poly(s,250,257).astype(np.float32)
  wave=signals[rec][center-128:center+128];norm=((wave.astype(np.float64)-wave.mean(dtype=np.float64))/wave.std(dtype=np.float64)).astype(np.float32);np.testing.assert_array_equal(norm,xs[j,:,0]);sc=report['io']['input_scale'];ze=report['io']['input_zero'];quant=np.clip(np.rint(norm.astype(np.float64)/sc)+ze,-128,127).astype(np.int8);np.testing.assert_array_equal(quant,q[pos]);raw.append(wave)
  fixtures.append({'fixture':j,'validation_index':int(pos),'record':rec,'center_250hz':center,'label':int(y[pos]),'reference_code':int(codes[pos]),'pvc_probability':float((int(codes[pos])+128)/256),'reference_prediction':int(int(codes[pos])>=98)})
 ASSETS.joinpath('v4_model.tflite').write_bytes(model.read_bytes());q[chosen].tofile(ASSETS/'v4_inputs.bin');np.asarray(raw,dtype='<f4').tofile(ASSETS/'v4_raw.bin')
 np.savez_compressed(OUT/'golden_fixtures.npz',raw_ecg=np.asarray(raw,np.float32),normalized_ecg=xs,int8_inputs=q[chosen],reference_codes=codes[chosen],labels=y[chosen],validation_indices=chosen)
 meta={'model_sha256':sha(model),'model_bytes':8688,'source_checkpoint_sha256':report['source_sha256'],'count':len(chosen),'io':report['io'],'threshold_probability':.88,'threshold_code_min':98,'source':'INCART Validation only; exact cached 25010/25010 host parity reused; selected static fixtures, no inference rerun','input_sha256':sha(ASSETS/'v4_inputs.bin'),'raw_sha256':sha(ASSETS/'v4_raw.bin'),'fixtures':fixtures}
 (OUT/'fixtures.json').write_text(json.dumps(meta,indent=2));print(json.dumps({'count':len(chosen),'model_sha256':meta['model_sha256'],'input_sha256':meta['input_sha256'],'raw_sha256':meta['raw_sha256'],'reference_codes':[f['reference_code'] for f in fixtures]},indent=2))
if __name__=='__main__':main()
