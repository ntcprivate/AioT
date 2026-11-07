"""Full-sample offline analysis; experimental display filter never changes CNN."""
import argparse
import csv
import json
from pathlib import Path
import numpy as np
from scipy import signal


def capture(path):
    with Path(path).open(encoding='utf-8-sig',newline='') as f:
        reader=csv.DictReader(f)
        if not {'timestamp_us','raw_adc'}<=set(reader.fieldnames or []):raise ValueError('Need complete timestamp_us/raw_adc CSV, not first10 logs')
        rows=list(reader)
    if len(rows)<250:raise ValueError('Need at least250 complete samples')
    if len({r.get('source','UNKNOWN') for r in rows})>1 or len({r.get('boot','UNKNOWN') for r in rows})>1:raise ValueError('Analyze one source/boot session at a time')
    t=np.array([int(r['timestamp_us']) for r in rows],dtype=np.int64)
    raw=np.array([float(r['raw_adc']) for r in rows])
    if not np.isfinite(raw).all() or np.any(np.diff(t)<=0):raise ValueError('Nonfinite ADC or nonmonotonic timestamps')
    if np.any((np.diff(t)<2000)|(np.diff(t)>6000)):raise ValueError('Sample gaps/jitter outside gate; split capture into continuous segments before PSD')
    if np.any((raw<0)|(raw>4095)):raise ValueError('ADC error/sentinel in capture; cannot treat it as ECG')
    return t,raw,rows[0].get('source','UNKNOWN')


def display_filter(raw,fs=250):
    b,a=signal.iirnotch(50,30,fs=fs)
    sos=np.vstack((signal.tf2sos(b,a),signal.butter(2,[.5,40],fs=fs,btype='bandpass',output='sos')))
    # Causal preview: no unreported zero-phase look-ahead or model preprocessing.
    return signal.sosfilt(sos,np.asarray(raw,dtype=float)-raw[0])


def measures(raw,fs=250):
    f,p=signal.welch(raw,fs,nperseg=min(len(raw),2048),detrend='constant')
    def power(lo,hi):
        keep=(f>=lo)&(f<=hi)
        return float(np.sum(p[keep])*(f[1]-f[0]))
    total=power(.05,100)
    metrics=dict(samples=len(raw),ptp_counts=float(np.ptp(raw)),mean_counts=float(np.mean(raw)),
        clipping_fraction=float(np.mean((raw<=16)|(raw>=4079))),
        power50_fraction=power(48,52)/total if total else None,
        baseline_fraction=power(.05,.5)/total if total else None,
        high_frequency_fraction=power(40,100)/total if total else None,
        baseline_first_last_counts=float(np.mean(raw[-250:])-np.mean(raw[:250])))
    return metrics,f,p


def analyze(t,raw,source,output):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    fs=(len(t)-1)*1e6/(t[-1]-t[0])
    if not 249<=fs<=251:raise ValueError(f'Observed fs={fs}; expected250Hz')
    before,f,p=measures(raw,fs);filtered=display_filter(raw,fs);after,ff,pp=measures(filtered+2048,fs)
    fig,axes=plt.subplots(3,1,figsize=(11,8),layout='constrained')
    seconds=(t-t[0])/1e6;axes[0].plot(seconds,raw,lw=.7);axes[0].set(ylabel='Raw ADC counts',title=f'{source} / full capture; no diagnosis')
    axes[1].plot(seconds,filtered,lw=.7,color='#b87923');axes[1].set(ylabel='Filtered AC counts',xlabel='Time (s)',title='Causal notch50 + bandpass0.5-40Hz: analysis ONLY, phase delay not compensated')
    axes[2].semilogy(f,np.maximum(p,1e-12),label='Raw');axes[2].semilogy(ff,np.maximum(pp,1e-12),label='Filtered');axes[2].set(xlabel='Frequency (Hz)',ylabel='PSD counts²/Hz',xlim=(0,125));axes[2].legend()
    fig.savefig(output/'signal_analysis.png',dpi=140);plt.close(fig)
    report=dict(source=source,scope='Exploratory bench analysis; filter not approved for model',observed_fs=fs,
        raw=before,filtered=after,filter='Causal50Hz notch Q30 +2nd-order0.5-40Hz bandpass',
        filter_model_use='BLOCKED: labeled QRS alignment/classification parity required',
        limits='PSD50 estimate does not prove mains origin. Filter startup transients/phase delay retained; no validity inferred.')
    (output/'signal_analysis.json').write_text(json.dumps(report,indent=2))
    np.savetxt(output/'filtered_preview.csv',np.column_stack((t,raw,filtered)),delimiter=',',header='timestamp_us,raw_adc,filtered_ac_counts',comments='')
    return report


def main():
    p=argparse.ArgumentParser();p.add_argument('--csv',type=Path);p.add_argument('--demo',action='store_true');p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    if args.demo:
        t=np.arange(7500,dtype=np.int64)*4000;sec=t/1e6
        raw=2048+50*np.sin(2*np.pi*1*sec)+100*np.sin(2*np.pi*50*sec)+30*np.sin(2*np.pi*.2*sec);source='SYNTHETIC50Hz_TEST'
    elif args.csv:t,raw,source=capture(args.csv)
    else:p.error('Choose --csv or --demo')
    print(json.dumps(analyze(t,raw,source,args.output),indent=2))


if __name__=='__main__':main()
