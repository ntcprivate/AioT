import queue
import threading
import time
import serial
from .protocol import StreamParser


class SerialWorker:
    """Never sends commands, reset pulses or opens a port until Connect is clicked."""
    def __init__(self,port,auto_reconnect=False,serial_factory=serial.Serial):
        self.port=port;self.auto_reconnect=auto_reconnect;self.factory=serial_factory
        self.events=queue.Queue(maxsize=256);self.stop_event=threading.Event();self.parser=StreamParser()
        self.thread=None;self.host_dropped=0

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
                device=self.factory(port=None,baudrate=115200,timeout=.1,write_timeout=.1,dsrdtr=False,rtscts=False)
                device.dtr=False;device.rts=False;device.port=self.port;device.open()
                self.parser.reset_connection();self.post(('connected',self.port))
                while not self.stop_event.is_set():
                    data=device.read(2048)
                    for p in self.parser.feed(data):self.post(('packet',p))
            except (serial.SerialException,OSError,ValueError) as e:self.post(('disconnected',str(e)))
            finally:
                if device:
                    try:device.close()
                    except OSError:pass
            if not self.auto_reconnect:break
            self.stop_event.wait(2)
