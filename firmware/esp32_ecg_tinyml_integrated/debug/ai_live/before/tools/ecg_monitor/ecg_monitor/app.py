import argparse
import queue
import sys
import os
import time
from pathlib import Path
import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets as W
import pyqtgraph as pg
from serial.tools import list_ports
from .protocol import StreamParser,encode
from .serial_worker import SerialWorker
from .session import Session,demo_packet

REASONS={
 'MODEL_VALIDATION_PENDING':'Đang kiểm tra mô hình và 12 golden; ADC/telemetry vẫn hoạt động',
 'R_DETECTOR_UNVALIDATED_LIVE_DISABLED':'Đang thu ECG; xem dự đoán tại AI ECG CLASSIFICATION',
 'HIGH_FREQUENCY_NOISE':'Biến thiên cao tần vượt ngưỡng; chưa đủ bằng chứng kết luận nhiễu 50 Hz',
 'LEADS_OFF':'Mất kết nối đầu vào cảm biến', 'COLLECTING':'Đang thu thập tín hiệu',
 'MODEL_OR_GOLDEN_FAILED':'Mô hình hoặc golden test lỗi', 'ADC_SATURATION':'ADC chạm biên đo',
 'PROCESS_QUEUE_FULL':'Hàng đợi xử lý đầy', 'SAMPLING_STALLED':'Luồng lấy mẫu không cập nhật',
 'FLAT_OR_TOO_SMALL':'Tín hiệu phẳng hoặc biên độ quá nhỏ'}


class Monitor(W.QMainWindow):
    def __init__(self):
        super().__init__();self.setWindowTitle('ECG Monitor 2.0 • Research Bench');self.resize(1250,850)
        self.session=Session();self.worker=None;self.parser=StreamParser();self.monitoring=False
        self.demo_first=0;self.demo_seq=0;self.last_demo=time.monotonic();self.last_event=None
        self.last_packet=0;self.connected_at=0
        self.display_rejections=0
        self.setStyleSheet('''QWidget {background:#101a2b;color:#e5edf6;font-family:Segoe UI;font-size:13px;}
            QLabel#title {font-size:25px;font-weight:700;} QLabel#banner {background:#26364a;padding:12px;border-radius:6px;}
            QGroupBox {border:1px solid #33465f;border-radius:7px;margin-top:12px;padding:12px;}
            QGroupBox::title {subcontrol-origin:margin;left:14px;color:#9cbbcf;}
            QPushButton {background:#27415c;border:1px solid #466580;border-radius:5px;padding:8px;}
            QPushButton:hover {background:#365979;} QPushButton:disabled {color:#68788a;background:#1b293c;}
            QComboBox,QLineEdit {background:#20324b;padding:6px;} QPlainTextEdit {background:#0c1422;border:0;}
            QLabel#state {font-size:23px;font-weight:700;color:#edc376;}
        ''')
        central=W.QWidget();self.setCentralWidget(central);layout=W.QVBoxLayout(central)
        title=W.QLabel('ECG Monitor');title.setObjectName('title');layout.addWidget(title)
        self.banner=W.QLabel('NGUYÊN MẪU NGHIÊN CỨU • Chỉ dùng simulator/bàn thử • Không kết nối cơ thể');self.banner.setObjectName('banner');layout.addWidget(self.banner)
        row=W.QHBoxLayout();layout.addLayout(row)
        self.mode=W.QComboBox();self.mode.addItems(['DEMO — dữ liệu mô phỏng','HARDWARE MONITOR — USB Serial']);row.addWidget(self.mode)
        self.mode.setMinimumContentsLength(15);self.mode.setSizeAdjustPolicy(W.QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon);self.mode.setMaximumWidth(300)
        self.mode.currentIndexChanged.connect(self.mode_changed)
        self.port=W.QComboBox();row.addWidget(self.port)
        self.port.setMinimumContentsLength(12);self.port.setSizeAdjustPolicy(W.QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon);self.port.setMaximumWidth(230)
        refresh=W.QPushButton('Refresh COM');refresh.clicked.connect(self.refresh_ports);row.addWidget(refresh)
        self.connect_button=W.QPushButton('Connect');self.connect_button.clicked.connect(self.toggle_connect);row.addWidget(self.connect_button)
        self.connect_button.setEnabled(False)
        self.reconnect=W.QCheckBox('Reconnect (opt-in)');row.addWidget(self.reconnect)
        self.start_button=W.QPushButton('Start Monitoring');self.start_button.clicked.connect(self.toggle_monitor);row.addWidget(self.start_button)
        split=W.QHBoxLayout();layout.addLayout(split,1)
        pg.setConfigOptions(antialias=False,background='#0c1422',foreground='#abc3d9')
        graph=W.QGroupBox('ECG • target 250 samples/s • 10-second window');gl=W.QVBoxLayout(graph)
        self.plot=pg.PlotWidget();self.plot.setLabel('left','ADC counts (uncalibrated)');self.plot.setLabel('bottom','Time since first sample','s');self.plot.showGrid(x=True,y=True,alpha=.15)
        self.raw=self.plot.plot(pen=pg.mkPen('#60d6cf',width=1),connect='finite',name='Raw ADC')
        self.filtered=self.plot.plot(pen=pg.mkPen('#e8bc73',width=1),connect='finite',name='Filtered display only')
        gl.addWidget(self.plot)
        options=W.QHBoxLayout();gl.addLayout(options)
        self.show_raw=W.QCheckBox('Raw');self.show_raw.setChecked(True);options.addWidget(self.show_raw)
        self.show_filtered=W.QCheckBox('Filtered • display only');options.addWidget(self.show_filtered)
        self.pause=W.QCheckBox('Pause Display (recording continues)');options.addWidget(self.pause)
        split.addWidget(graph,5)
        side=W.QGroupBox('System / signal status');shell=W.QVBoxLayout(side);split.addWidget(side,2)
        scroll=W.QScrollArea();scroll.setWidgetResizable(True);scroll.setFrameShape(W.QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff);shell.addWidget(scroll)
        content=W.QWidget();content.setSizePolicy(W.QSizePolicy.Policy.Ignored,W.QSizePolicy.Policy.Preferred)
        form=W.QVBoxLayout(content);form.setSizeConstraint(W.QLayout.SizeConstraint.SetNoConstraint);scroll.setWidget(content)
        self.state=W.QLabel('WAITING');self.state.setObjectName('state');form.addWidget(self.state)
        self.reason=W.QLabel('Đang chờ dữ liệu ECG');self.reason.setWordWrap(True);form.addWidget(self.reason)
        self.reason.setSizePolicy(W.QSizePolicy.Policy.Ignored,W.QSizePolicy.Policy.Minimum)
        self.fields={}
        grid=W.QFormLayout();form.addLayout(grid)
        grid.setRowWrapPolicy(W.QFormLayout.RowWrapPolicy.WrapLongRows)
        for name in ['Source','Connection','Firmware','ADC / generator rate','TX completed rate','RX device-time rate','RX wall-clock rate','Lead status','Signal quality','Amplitude / Δ ratio','50 Hz estimate','Clipping / 256','Baseline Δ counts','Errors / lost','BPM / RR','LED / buzzer']:
            label=W.QLabel('--');label.setWordWrap(True);label.setSizePolicy(W.QSizePolicy.Policy.Ignored,W.QSizePolicy.Policy.Minimum);grid.addRow(name,label);self.fields[name]=label
            grid.labelForField(label).setWordWrap(True)
        ai=W.QGroupBox('AI ECG CLASSIFICATION');ai_layout=W.QVBoxLayout(ai)
        prediction=W.QLabel('UNKNOWN');prediction.setObjectName('ai_prediction')
        prediction.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        prediction.setStyleSheet('font-size:32px;font-weight:700;color:#edc376;')
        ai_layout.addWidget(prediction);ai_form=W.QFormLayout();ai_layout.addLayout(ai_form)
        ai_form.setRowWrapPolicy(W.QFormLayout.RowWrapPolicy.WrapLongRows)
        self.ai_fields={'Classification':prediction}
        for name in ['PVC probability','CNN latency','R-peak count','Total classified beats','Prediction age','Reason']:
            label=W.QLabel('--');label.setWordWrap(True);label.setSizePolicy(W.QSizePolicy.Policy.Ignored,W.QSizePolicy.Policy.Minimum)
            ai_form.addRow(name,label);ai_form.labelForField(label).setWordWrap(True);self.ai_fields[name]=label
        notice=W.QLabel('Research prototype \u2014 Not for medical diagnosis');notice.setWordWrap(True)
        notice.setStyleSheet('font-size:11px;color:#9cbbcf;');ai_layout.addWidget(notice)
        form.insertWidget(2,ai);form.addStretch()
        record=W.QHBoxLayout();layout.addLayout(record)
        self.record_button=W.QPushButton('Save session CSV…');self.record_button.clicked.connect(self.toggle_recording);record.addWidget(self.record_button)
        self.record_label=W.QLabel('No recording • DEMO / HARDWARE luôn được ghi rõ nguồn');record.addWidget(self.record_label,1)
        offline=W.QPushButton('Analyze CSV…');offline.clicked.connect(self.analyze_csv);record.addWidget(offline)
        self.log=W.QPlainTextEdit();self.log.setReadOnly(True);self.log.setMaximumBlockCount(200);self.log.setMaximumHeight(125);layout.addWidget(self.log)
        self.timer=QtCore.QTimer(self);self.timer.timeout.connect(self.tick);self.timer.start(40)
        self.refresh_ports();self.log_event('Ứng dụng sẵn sàng. Không tự mở COM, flash hoặc reset thiết bị.')

    def log_event(self,text):
        self.log.appendPlainText(time.strftime('%H:%M:%S')+'  '+text)

    def refresh_ports(self):
        current=self.port.currentData();self.port.clear()
        for p in list_ports.comports():self.port.addItem(f'{p.device} — {p.description}',p.device)
        if self.port.findData(current)>=0:self.port.setCurrentIndex(self.port.findData(current))
        if not self.port.count():self.port.addItem('Không có thiết bị COM',None)

    def mode_changed(self):
        self.disconnect();self.monitoring=False;self.start_button.setText('Start Monitoring')
        self.session=Session();self.parser=StreamParser();self.last_packet=0
        self.connect_button.setEnabled(self.mode.currentIndex()==1)
        self.reset_plot()
        self.log_event('Đổi nguồn: '+self.mode.currentText());self.update_status()

    def disconnect(self):
        if self.worker:self.worker.stop();self.worker=None
        self.session.stop_recording();self.session.disconnect();self.connect_button.setText('Connect')
        self.record_button.setText('Save session CSV…');self.record_label.setText('No recording')
        self.session=Session();self.last_packet=0;self.monitoring=False;self.start_button.setText('Start Monitoring')
        self.parser=StreamParser();self.reset_plot();self.update_status()

    def reset_plot(self):
        self.raw.setData([],[]);self.filtered.setData([],[])
        self.plot.setXRange(0,10,padding=0);self.plot.setYRange(0,4095,padding=.02)
        self.plot.enableAutoRange(axis='y',enable=True)
        self.pause.setChecked(False);self.show_raw.setChecked(True)
        self.demo_first=0;self.demo_seq=0;self.last_demo=time.monotonic()

    def toggle_connect(self):
        if self.worker:self.disconnect();return
        if self.mode.currentIndex()!=1:self.log_event('Chọn HARDWARE MONITOR để kết nối COM.');return
        port=self.port.currentData()
        if not port:self.log_event('Không có COM. Kết nối ESP32 và Refresh COM.');return
        self.worker=SerialWorker(port,self.reconnect.isChecked(),capture_dir=Path(__file__).resolve().parents[1]/'captures')
        self.worker.start();self.connected_at=time.monotonic()
        self.connect_button.setText('Disconnect');self.log_event('Đang mở '+port+'; hãy đóng idf.py monitor nếu cổng đang bận.')

    def toggle_monitor(self):
        if self.mode.currentIndex()==1 and not self.worker and not self.monitoring:self.log_event('Connect ESP32 trước.');return
        self.monitoring=not self.monitoring;self.start_button.setText('Stop Monitoring' if self.monitoring else 'Start Monitoring')
        if self.monitoring:
            self.session=Session();self.reset_plot()
            if self.mode.currentIndex()==0:self.parser=StreamParser()
            if self.worker:
                while True:
                    try:self.worker.events.get_nowait()
                    except queue.Empty:break
            self.session.source='DEMO' if self.mode.currentIndex()==0 else 'HARDWARE'
        if not self.monitoring:
            self.session.stop_recording();self.session.disconnect();self.reset_plot();self.last_packet=0
            self.record_button.setText('Save session CSV…')
        self.log_event('Monitoring '+('started' if self.monitoring else 'stopped'));self.update_status()

    def toggle_recording(self):
        if self.session.csv:
            self.session.stop_recording();self.record_button.setText('Save session CSV…');self.record_label.setText('CSV + session report saved');return
        if not self.monitoring:self.log_event('Start Monitoring trước khi ghi CSV.');return
        path,_=W.QFileDialog.getSaveFileName(self,'New session CSV',f'ecg_{time.strftime("%Y%m%d_%H%M%S")}.csv','CSV (*.csv)')
        if path:
            try:self.session.start_recording(path);self.record_button.setText('Stop Recording');self.record_label.setText(path)
            except OSError as e:self.log_event('Không ghi đè file cũ / không mở được CSV: '+str(e))

    def analyze_csv(self):
        path,_=W.QFileDialog.getOpenFileName(self,'Full sample session CSV','','CSV (*.csv)')
        if not path:return
        output=Path(path).parent/(Path(path).stem+'_analysis_'+time.strftime('%Y%m%d_%H%M%S'))
        process=QtCore.QProcess(self);process.setProgram(sys.executable)
        process.setArguments(['-m','ecg_monitor.offline','--csv',path,'--output',str(output)])
        process.setWorkingDirectory(str(Path(__file__).resolve().parents[1]))
        process.finished.connect(lambda code:self.log_event(('Analysis saved: '+str(output)) if code==0 else 'Analysis rejected: '+bytes(process.readAllStandardError()).decode(errors='replace')[-400:]))
        process.start();self.log_event('Offline analysis running; original CSV unchanged.')

    def accept(self,p,source):
        self.last_packet=time.monotonic()
        actual_source=p.get('source',source)
        if actual_source not in ('SYNTHETIC_TEST','DEMO','HARDWARE','REPLAY'):actual_source=source
        old_boot=self.session.boot;old_source=self.session.source
        try:
            if self.monitoring:self.session.consume(p,actual_source)
            elif p['type']=='status':self.session.consume(p,actual_source)
        except (ValueError,TypeError,OverflowError) as e:
            self.display_rejections+=1
            if self.display_rejections==1:self.log_event('Rejected display input: '+str(e))
            return
        if old_boot is not None and (old_boot!=self.session.boot or old_source!=self.session.source):self.reset_plot()

    def tick(self):
        now=time.monotonic()
        if self.mode.currentIndex()==0 and self.monitoring:
            catchup=0
            while now-self.last_demo>=.128 and catchup<8:
                for p in self.parser.feed(encode(demo_packet(self.demo_first,self.demo_seq))):self.accept(p,'DEMO')
                self.demo_first+=32;self.demo_seq+=1;self.last_demo+=.128;catchup+=1
        if self.worker:
            worker=self.worker
            for _ in range(256):
                try:kind,data=worker.events.get_nowait()
                except queue.Empty:break
                if kind=='packet':self.accept(data,'HARDWARE')
                else:
                    self.log_event(kind+': '+str(data))
                    if kind=='capture' and not self.session.csv:self.record_label.setText('Raw Serial capture active • CSV not recording')
                    if kind in ('connected','disconnected'):
                        self.session.stop_recording();self.session=Session();self.reset_plot();self.last_packet=0
                    if kind=='disconnected' and not worker.auto_reconnect:
                        worker.stop();self.worker=None;self.monitoring=False
                        self.connect_button.setText('Connect');self.start_button.setText('Start Monitoring');break
            if self.worker and self.connected_at and now-self.connected_at>5 and not self.last_packet:
                self.log_event('Chưa nhận ECG1 hợp lệ: kiểm tra firmware telemetry, COM và baud115200.');self.connected_at=now
        if self.last_packet and now-self.last_packet>2:
            self.session.disconnect();self.reset_plot();self.last_packet=0;self.log_event('Telemetry timeout: xóa kết quả AI/BPM cũ.')
        if self.session.record_error:
            self.log_event('Recording stopped: '+self.session.record_error);self.record_label.setText('Recording error — raw monitor continues')
            self.record_button.setText('Save session CSV…');self.session.record_error=None
        if not self.pause.isChecked() and self.session.times:
            origin=self.session.origin_us if self.session.origin_us is not None else self.session.times[0]
            x=np.array([(t-origin)/1e6 for t in self.session.times],dtype=np.float64);y=np.array(self.session.values,dtype=np.float64)
            if np.any(np.isinf(y)) or np.any(np.isfinite(y)&((y<0)|(y>4095))) or not np.isfinite(x).all() or np.any(np.diff(x)<=0):
                self.display_rejections+=1;self.session.disconnect();self.reset_plot()
                self.log_event('Display rejected invalid ADC/timestamp; no range clamp used to hide it.');self.update_status();return
            self.raw.setData(x,y) if self.show_raw.isChecked() else self.raw.setData([],[])
            if self.show_filtered.isChecked():
                from scipy.signal import butter,sosfilt
                # Display-only preview, reset on gaps; never sent to firmware/CNN.
                sos=butter(2,[.5,40],btype='bandpass',fs=250,output='sos');z=np.full_like(y,np.nan)
                good=np.isfinite(y);starts=np.flatnonzero(good & np.r_[True,~good[:-1]])
                for start in starts:
                    end=start
                    while end<len(y) and good[end]:end+=1
                    z[start:end]=sosfilt(sos,y[start:end]-y[start])+2048
                if np.any(np.isinf(z)) or np.any(np.isfinite(z)&(np.abs(z)>16384)):
                    self.filtered.setData([],[]);self.show_filtered.setChecked(False)
                    self.log_event('Filtered preview rejected nonfinite/unstable output; raw data retained.')
                else:self.filtered.setData(x,z)
            else:self.filtered.setData([],[])
            self.plot.setXRange(max(0,x[-1]-10),max(10,x[-1]),padding=0)
        self.update_status()

    def update_status(self):
        # Resolve validity/expiry once so header and prediction cannot disagree
        # at a TTL boundary or because of the separate official-live FSM.
        ai=self.session.research_display(now=time.monotonic(),connected=bool(self.last_packet) and self.monitoring)
        self.update_ai(ai)
        s=self.session.status;demo=self.mode.currentIndex()==0;live=bool(self.last_packet)
        synthetic=self.session.source=='SYNTHETIC_TEST'
        reason=ai['reason']
        if ai['prediction'] in ('NORMAL','PVC'):state='AI LIVE'
        elif reason=='TELEMETRY_TIMEOUT':state='DISCONNECTED'
        elif reason=='STOPPED_OR_DISCONNECTED':
            state='WAITING' if demo else 'STOPPED' if self.worker and not self.monitoring else 'DISCONNECTED'
        elif reason in ('PREDICTION_STALE','AI_STATUS_TIMEOUT'):state=reason
        elif ai['state']=='INVALID':state='SYSTEM_FAULT' if s.get('state')=='SYSTEM_FAULT' else 'LEADS_OFF' if reason=='LEADS_OFF' else 'SIGNAL_INVALID'
        elif s.get('self_test') is True and live:state='SELF_TEST'
        elif demo and self.monitoring:state='DEMO'
        elif synthetic and live:state='SYNTHETIC_TEST'
        else:state='WAITING'
        self.state.setText(state)
        self.reason.setText('Dữ liệu tổng hợp để kiểm thử giao diện; AI chưa chạy.' if demo else REASONS.get(reason,reason.replace('_',' ')))
        self.reason.setToolTip(reason)
        if state=='SELF_TEST':self.reason.setText('Kiểm tra LED/buzzer khi khởi động • độc lập AI, không phải cảnh báo PVC.')
        if synthetic and state=='SYNTHETIC_TEST':self.reason.setText('SYNTHETIC_TEST • mẫu xác định từ ESP32, không phải ECG; không đưa vào AI.')
        fields=self.fields;fields['Source'].setText('DEMO • SYNTHETIC' if demo else 'HARDWARE • ADC' if live else '--')
        if synthetic:fields['Source'].setText('SYNTHETIC_TEST • ESP32')
        fields['Connection'].setText('DEMO / no device' if demo else 'Receiving ECG1' if live else 'No valid telemetry')
        fields['Firmware'].setText(s.get('firmware','--'))
        raw_fresh=live and time.monotonic()-self.session.last_samples_received<2
        if len(self.session.received_times)>1 and raw_fresh:
            times=list(self.session.received_times);rate=(len(times)-1)*1e6/(times[-1]-times[0]) if times[-1]>times[0] else 0
            fields['RX device-time rate'].setText(f'{rate:.2f} Hz (delivered)')
        else:fields['RX device-time rate'].setText('UNKNOWN')
        hz=s.get('acq_hz');tx=s.get('tx_hz');wall=self.session.received_wall_rate()
        fresh_clock=live and 0<=s.get('t_us',0)-s.get('clock_last_us',-10**18)<2_000_000
        fields['ADC / generator rate'].setText(f'{hz:.2f} Hz / {"SYNTH" if synthetic else "ADC"}' if hz is not None and fresh_clock else 'UNKNOWN')
        fields['TX completed rate'].setText(f'{tx:.2f} Hz' if tx is not None and raw_fresh else 'UNKNOWN')
        fields['RX wall-clock rate'].setText(f'{wall:.2f} Hz' if wall is not None and raw_fresh else 'UNKNOWN')
        last_flag=self.session.flags[-1] if self.session.flags else None
        fields['Lead status'].setText('SIMULATED' if demo else '--' if last_flag is None or not raw_fresh else f'LO+={last_flag&1}, LO−={(last_flag>>1)&1}')
        known=s.get('quality_known') is True and live and 0<=s.get('t_us',0)-s.get('quality_t_us',-10**18)<=2_000_000
        fields['Signal quality'].setText('REJECTED' if ai['state']=='INVALID' else 'Bench checks pass (not validated ECG)' if known and s.get('quality_valid') else 'Collecting / checks pending' if known else '--')
        fields['Amplitude / Δ ratio'].setText(f'{s["ptp"]} counts / {s["diff_percent"]:.1f}% (limit {s.get("diff_limit",25)}%)' if known else '--')
        fields['50 Hz estimate'].setText(f'{100*s["power50_ratio"]:.1f}% • diagnostic' if known else '--')
        fields['Clipping / 256'].setText(str(s.get('clip_count','--')) if known else '--')
        fields['Baseline Δ counts'].setText(f'{s.get("baseline_delta",0):.1f}' if known else '--')
        parser=self.worker.parser if self.worker else self.parser
        self.session.transport_stats=dict(scope='Cumulative parser/worker counters at last UI update',
            rejected_frames_total=parser.errors,lost_packets=parser.lost_packets,lost_samples=parser.lost_samples,
            crc_failures=parser.crc_failures,framing_errors=parser.framing_errors,schema_errors=parser.schema_errors,
            sequence_errors=parser.sequence_errors,rx_timing_violations=parser.timing_violations,synthetic_mismatches=parser.synthetic_mismatches,
            host_queue_dropped=self.worker.host_dropped if self.worker else 0,reconnects=parser.reconnects)
        fields['Errors / lost'].setText(f'Connection counters: CRC {parser.crc_failures} • frame {parser.framing_errors} • schema {parser.schema_errors} • sequence {parser.sequence_errors}\nPacket gaps {parser.lost_packets} • missing samples {parser.lost_samples} • RX timing {parser.timing_violations}\nSynthetic mismatch {parser.synthetic_mismatches} • host queue drops(worker) {self.worker.host_dropped if self.worker else 0} • reconnects(worker) {parser.reconnects}')
        if s:fields['Errors / lost'].setText(fields['Errors / lost'].text()+f'\nFW since boot: ADC errors {s.get("adc_errors","--")} • missed slots(est) {s.get("missed_est","--")} • queue drops {s.get("tx_dropped","--")}')
        if s:fields['Errors / lost'].setText(fields['Errors / lost'].text()+f'\nFW UART write {s.get("uart_write_errors","--")} • drain timeout {s.get("uart_tx_timeouts","--")} • format {s.get("format_errors","--")}')
        fields['BPM / RR'].setText('-- / --') # No validated R detector, no invented HR.
        fields['LED / buzzer'].setText(f'{"ON" if s.get("led") else "OFF"} / {"ON" if s.get("buzzer") else "OFF"}' if s and live else '--')
        event=(state,reason)
        if event!=self.last_event:self.log_event(state+' • '+REASONS.get(reason,reason));self.last_event=event

    def update_ai(self,d):
        r=d['research'];f=self.ai_fields
        label={'NORMAL':'NORMAL (N)','PVC':'PVC (V)'}.get(d['prediction'],'UNKNOWN')
        f['Classification'].setText(label)
        f['PVC probability'].setText('--' if d['probability'] is None else f"{100*d['probability']:.4f}%")
        f['CNN latency'].setText(f"{r.get('latency_us',0)/1000:.3f} ms" if d['prediction']!='UNKNOWN' else '--')
        f['R-peak count'].setText(str(r.get('detected',0)))
        f['Total classified beats'].setText(str(r.get('classified',0)))
        f['Prediction age'].setText('--' if d['age_us'] is None else f"{max(0,d['age_us'])/1000:.0f} ms")
        f['Reason'].setText(d['reason'].replace('_',' '))
        f['Reason'].setToolTip(d['reason'])

    def closeEvent(self,event):
        self.disconnect();event.accept()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--demo',action='store_true');parser.add_argument('--smoke',type=Path)
    args=parser.parse_args();app=W.QApplication(sys.argv)
    if not QtGui.QFontDatabase.families():
        QtGui.QFontDatabase.addApplicationFont(str(Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts/segoeui.ttf'))
    app.setFont(QtGui.QFont('Segoe UI',10))
    window=Monitor();window.show()
    if args.demo or args.smoke:window.toggle_monitor()
    if args.smoke:
        def capture():
            args.smoke.parent.mkdir(parents=True,exist_ok=True);window.grab().save(str(args.smoke));window.close();app.quit()
        QtCore.QTimer.singleShot(4000,capture)
    return app.exec()


if __name__=='__main__':raise SystemExit(main())
