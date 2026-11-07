import queue
import threading
import time
import serial
import json
from pathlib import Path
from datetime import datetime,timezone
from uuid import uuid4
from .protocol import StreamParser


class SerialWorker:
    """Never sends commands, reset pulses or opens a port until Connect is clicked."""
    def __init__(self,port,auto_reconnect=False,serial_factory=serial.Serial,capture_dir=None):
        self.port=port;self.auto_reconnect=auto_reconnect;self.factory=serial_factory
        self.events=queue.Queue(maxsize=256);self.stop_event=threading.Event();self.parser=StreamParser()
        self.thread=None;self.host_dropped=0
        self.capture_dir=Path(capture_dir) if capture_dir else None
        self.raw_capture=None;self.reject_capture=None;self.capture_path=None
        self.parser.on_reject=self.capture_rejection

    def capture_rejection(self,event):
        if self.reject_capture:
            try:self.reject_capture.write(json.dumps(event)+'\n');self.reject_capture.flush()
            except OSError as e:self.post(('capture_error',str(e)));self.close_capture()

    def open_capture(self):
        if not self.capture_dir:return
        try:
            self.capture_dir.mkdir(parents=True,exist_ok=True)
            name=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+uuid4().hex[:8]
            self.capture_path=self.capture_dir/(name+'.bin')
            self.raw_capture=self.capture_path.open('xb')
            self.reject_capture=self.capture_path.with_suffix('.rejects.jsonl').open('x',encoding='utf-8')
            self.post(('capture',str(self.capture_path)))
        except OSError as e:self.post(('capture_error',str(e)));self.close_capture()

    def close_capture(self):
        for file in (self.raw_capture,self.reject_capture):
            if file:
                try:file.close()
                except OSError:pass
        self.raw_capture=self.reject_capture=None

    def post(self,event):
        try:self.events.put_nowait(event)
        except queue.Full:self.host_dropped+=1

    def start(self):
        self.thread=threading.Thread(target=self.run,daemon=True);self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread:self.thread.join(timeout=1)

    def run(self):
        while not self.stop_event.is_set():
            device=None
            try:
                device=self.factory(port=None,baudrate=115200,timeout=.05,write_timeout=.1,dsrdtr=False,rtscts=False)
                device.dtr=False;device.rts=False;device.port=self.port;device.open()
                self.parser.reset_connection();self.open_capture();self.post(('connected',self.port))
                while not self.stop_event.is_set():
                    waiting=getattr(device,'in_waiting',0)
                    data=device.read(max(1,min(waiting,8192)))
                    if self.raw_capture and data:
                        try:self.raw_capture.write(data);self.raw_capture.flush()
                        except OSError as e:self.post(('capture_error',str(e)));self.close_capture()
                    received=time.monotonic()
                    for p in self.parser.feed(data):
                        p['_received_monotonic']=received
                        self.post(('packet',p))
            except (serial.SerialException,OSError,ValueError) as e:self.post(('disconnected',str(e)))
            finally:
                self.close_capture()
                if device:
                    try:device.close()
                    except OSError:pass
            if not self.auto_reconnect:break
            self.stop_event.wait(2)
