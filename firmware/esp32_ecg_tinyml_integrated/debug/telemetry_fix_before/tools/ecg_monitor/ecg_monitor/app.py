import argparse
import json
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
from .session import Session,demo_packet,valid_classification

REASONS={
 'MODEL_VALIDATION_PENDING':'Đang kiểm tra mô hình và 12 golden; ADC/telemetry vẫn hoạt động',
 'R_DETECTOR_UNVALIDATED_LIVE_DISABLED':'AI chưa kích hoạt: bộ phát hiện đỉnh R chưa đạt kiểm chứng',
 'HIGH_FREQUENCY_NOISE':'Biến thiên cao tần vượt ngưỡng; chưa đủ bằng chứng kết luận nhiễu 50 Hz',
 'LEADS_OFF':'Mất kết nối đầu vào cảm biến', 'COLLECTING':'Đang thu thập tín hiệu',
 'MODEL_OR_GOLDEN_FAILED':'Mô hình hoặc golden test lỗi', 'ADC_SATURATION':'ADC chạm biên đo',
 'PROCESS_QUEUE_FULL':'Hàng đợi xử lý đầy', 'SAMPLING_STALLED':'Luồng lấy mẫu không cập nhật',
 'FLAT_OR_TOO_SMALL':'Tín hiệu phẳng hoặc biên độ quá nhỏ'}


class Monitor(W.QMainWindow):
    def __init__(self):
        super().__init__();self.setWindowTitle('ECG Monitor • Research Bench');self.resize(1250,850)
        self.session=Session();self.worker=None;self.parser=StreamParser();self.monitoring=False
        self.demo_first=0;self.demo_seq=0;self.last_demo=time.monotonic();self.last_event=None
        self.last_packet=0;self.connected_at=0;self.filter_state=None
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
        self.mode=W.QComboBox();self.mode.addItems(['DEMO — dữ liệu mô phỏng','HARDWARE MONITOR — USB Serial','VALIDATED AI TEST — LOCKED']);row.addWidget(self.mode)
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
        graph=W.QGroupBox('ECG • 250 samples/s • 10-second window');gl=W.QVBoxLayout(graph)
        self.plot=pg.PlotWidget();self.plot.setLabel('left','ADC counts (uncalibrated)');self.plot.setLabel('bottom','Device time','s');self.plot.showGrid(x=True,y=True,alpha=.15)
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
        content=W.QWidget();form=W.QVBoxLayout(content);form.setSizeConstraint(W.QLayout.SizeConstraint.SetMinimumSize);scroll.setWidget(content)
        self.state=W.QLabel('WAITING');self.state.setObjectName('state');form.addWidget(self.state)
        self.reason=W.QLabel('Đang chờ dữ liệu ECG');self.reason.setWordWrap(True);form.addWidget(self.reason)
        self.fields={}
        grid=W.QFormLayout();form.addLayout(grid)
        for name in ['Source','Connection','Firmware','Sampling rate','Lead status','Signal quality','Amplitude / Δ ratio','50 Hz estimate','Clipping / 256','Baseline Δ counts','Errors / lost','AI mode','Classification','PVC probability','BPM / RR','LED / buzzer']:
            label=W.QLabel('--');label.setWordWrap(True);label.setSizePolicy(W.QSizePolicy.Policy.Preferred,W.QSizePolicy.Policy.Minimum);grid.addRow(name,label);self.fields[name]=label
        form.addStretch()
        locked=W.QLabel('AI TEST: LOCKED\nCần detector + end-to-end + simulator PASS. Golden inference không mở khóa AI-live.');locked.setWordWrap(True);form.addWidget(locked)
        validation=Path(__file__).resolve().parents[1]/'reports/offline_validation.json'
        if validation.exists():
            try:
                result=json.loads(validation.read_text());metrics=result['aggregate']
                locked.setText(locked.text()+f'\nDetector: {result["status"]}\nSensitivity {metrics["sensitivity"]:.2%} / PPV {metrics["ppv"]:.2%}')
            except (OSError,ValueError,KeyError,TypeError):pass
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
        self.session=Session();self.parser=StreamParser();self.last_packet=0;self.filter_state=None
        self.connect_button.setEnabled(self.mode.currentIndex()==1)
        self.raw.setData([],[]);self.filtered.setData([],[])
        self.log_event('Đổi nguồn: '+self.mode.currentText());self.update_status()

    def disconnect(self):
        if self.worker:self.worker.stop();self.worker=None
        self.session.stop_recording();self.session.disconnect();self.connect_button.setText('Connect')
        self.record_button.setText('Save session CSV…');self.record_label.setText('No recording')

    def toggle_connect(self):
        if self.worker:self.disconnect();return
        if self.mode.currentIndex()!=1:self.log_event('Chọn HARDWARE MONITOR để kết nối COM.');return
        port=self.port.currentData()
        if not port:self.log_event('Không có COM. Kết nối ESP32 và Refresh COM.');return
        self.worker=SerialWorker(port,self.reconnect.isChecked());self.worker.start();self.connected_at=time.monotonic()
        self.connect_button.setText('Disconnect');self.log_event('Đang mở '+port+'; hãy đóng idf.py monitor nếu cổng đang bận.')

    def toggle_monitor(self):
        if self.mode.currentIndex()==2:
            self.log_event('AI TEST bị khóa: xem reports/offline_validation.json; không giả lập kết quả AI.');return
        if self.mode.currentIndex()==1 and not self.worker:self.log_event('Connect ESP32 trước.');return
        self.monitoring=not self.monitoring;self.start_button.setText('Stop Monitoring' if self.monitoring else 'Start Monitoring')
        if self.monitoring:
            self.last_demo=time.monotonic();self.session.source='DEMO' if self.mode.currentIndex()==0 else 'HARDWARE'
        if not self.monitoring:self.session.stop_recording();self.record_button.setText('Save session CSV…')
        self.log_event('Monitoring '+('started' if self.monitoring else 'stopped'))

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
        if self.monitoring:self.session.consume(p,source)
        elif p['type']=='status':self.session.consume(p,source)

    def tick(self):
        now=time.monotonic()
        if self.mode.currentIndex()==0 and self.monitoring:
            catchup=0
            while now-self.last_demo>=.128 and catchup<8:
                for p in self.parser.feed(encode(demo_packet(self.demo_first,self.demo_seq))):self.accept(p,'DEMO')
                self.demo_first+=32;self.demo_seq+=1;self.last_demo+=.128;catchup+=1
        if self.worker:
            for _ in range(256):
                try:kind,data=self.worker.events.get_nowait()
                except queue.Empty:break
                if kind=='packet':self.accept(data,'HARDWARE')
                else:
                    self.log_event(kind+': '+str(data))
                    if kind=='disconnected':self.session.disconnect();self.last_packet=0
            if self.connected_at and now-self.connected_at>5 and not self.last_packet:
                self.log_event('Chưa nhận ECG1 hợp lệ: kiểm tra firmware telemetry, COM và baud115200.');self.connected_at=now
        if self.last_packet and now-self.last_packet>2:
            self.session.disconnect();self.last_packet=0;self.log_event('Telemetry timeout: xóa kết quả AI/BPM cũ.')
        if self.session.record_error:
            self.log_event('Recording stopped: '+self.session.record_error);self.record_label.setText('Recording error — raw monitor continues')
            self.record_button.setText('Save session CSV…');self.session.record_error=None
        if not self.pause.isChecked() and self.session.times:
            x=np.array(self.session.times,dtype=float)/1e6;y=np.array(self.session.values,dtype=float)
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
                self.filtered.setData(x,z)
            else:self.filtered.setData([],[])
            self.plot.setXRange(max(0,x[-1]-10),max(10,x[-1]),padding=0)
        self.update_status()

    def update_status(self):
        s=self.session.status;demo=self.mode.currentIndex()==0;live=bool(self.last_packet)
        label,p=valid_classification(s,self.session.source,max(s.get('t_us',0),self.session.times[-1] if self.session.times else 0),self.session.last_invalid_t)
        state='DEMO' if demo and self.monitoring else s.get('state','WAITING') if live else 'WAITING'
        if self.session.local_invalid_reason and not demo and live:
            label,p='UNKNOWN',None
            if state not in ('SYSTEM_FAULT','SELF_TEST'):state='SIGNAL_INVALID'
        if state in ('NORMAL','PVC') and label=='UNKNOWN':state='SIGNAL_INVALID'
        self.state.setText(state)
        reason=s.get('reason','');self.reason.setText('Dữ liệu tổng hợp để kiểm thử giao diện; AI chưa chạy.' if demo else REASONS.get(reason,reason or 'Đang chờ dữ liệu ECG'))
        if self.session.local_invalid_reason and not demo and state=='SIGNAL_INVALID':self.reason.setText(REASONS.get(self.session.local_invalid_reason,self.session.local_invalid_reason))
        if state=='SELF_TEST':self.reason.setText('Kiểm tra LED/buzzer khi khởi động • độc lập AI, không phải cảnh báo PVC.')
        fields=self.fields;fields['Source'].setText('DEMO • SYNTHETIC' if demo else 'HARDWARE • ADC' if live else '--')
        fields['Connection'].setText('DEMO / no device' if demo else 'Receiving ECG1' if live else 'No valid telemetry')
        fields['Firmware'].setText(s.get('firmware','--'))
        raw_fresh=live and time.monotonic()-self.session.last_samples_received<2
        if len(self.session.received_times)>1 and raw_fresh:
            times=list(self.session.received_times);rate=(len(times)-1)*1e6/(times[-1]-times[0]) if times[-1]>times[0] else 0
            fields['Sampling rate'].setText(f'{rate:.2f} Hz')
        else:fields['Sampling rate'].setText('--')
        last_flag=self.session.flags[-1] if self.session.flags else None
        fields['Lead status'].setText('SIMULATED' if demo else '--' if last_flag is None or not raw_fresh else f'LO+={last_flag&1}, LO−={(last_flag>>1)&1}')
        known=s.get('quality_known') is True and live and 0<=s.get('t_us',0)-s.get('quality_t_us',-10**18)<=2_000_000
        fields['Signal quality'].setText('REJECTED' if state=='SIGNAL_INVALID' else 'Bench checks pass (not validated ECG)' if known and s.get('quality_valid') else 'Collecting / checks pending' if known else '--')
        fields['Amplitude / Δ ratio'].setText(f'{s["ptp"]} counts / {s["diff_percent"]:.1f}% (limit {s.get("diff_limit",25)}%)' if known else '--')
        fields['50 Hz estimate'].setText(f'{100*s["power50_ratio"]:.1f}% • diagnostic' if known else '--')
        fields['Clipping / 256'].setText(str(s.get('clip_count','--')) if known else '--')
        fields['Baseline Δ counts'].setText(f'{s.get("baseline_delta",0):.1f}' if known else '--')
        parser=self.worker.parser if self.worker else self.parser
        self.session.transport_stats=dict(scope='Cumulative parser/worker counters at last UI update',
            parse_errors=parser.errors,lost_packets=parser.lost_packets,lost_samples=parser.lost_samples,
            host_queue_dropped=self.worker.host_dropped if self.worker else 0,reconnects=parser.reconnects)
        fields['Errors / lost'].setText(f'CRC/parse {parser.errors} • packets {parser.lost_packets} • samples {parser.lost_samples} • host {self.worker.host_dropped if self.worker else 0}')
        if s:fields['Errors / lost'].setText(fields['Errors / lost'].text()+f'\nADC {s.get("adc_errors","--")} • missed {s.get("missed_est","--")} • tx {s.get("tx_dropped","--")}')
        fields['AI mode'].setText('DISABLED • DEMO' if demo else s.get('model','LOCKED / no data'))
        fields['Classification'].setText(label);fields['PVC probability'].setText('--' if p is None else f'{p:.5f}')
        fields['BPM / RR'].setText('-- / --') # No validated R detector, no invented HR.
        fields['LED / buzzer'].setText(f'{"ON" if s.get("led") else "OFF"} / {"ON" if s.get("buzzer") else "OFF"}' if s and live else '--')
        if reason and reason!=self.last_event:self.log_event(state+' • '+REASONS.get(reason,reason));self.last_event=reason

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
