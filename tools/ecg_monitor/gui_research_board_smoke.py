"""Actual GUI+Serial smoke, bench authorization required; never flashes/resets."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import argparse,json
from pathlib import Path
from PySide6 import QtCore,QtGui,QtWidgets as W
from ecg_monitor.app import Monitor

def main():
    p=argparse.ArgumentParser();p.add_argument('--authorized-bench',action='store_true');a=p.parse_args()
    if not a.authorized_bench:p.error('Bench authorization required')
    out=Path(__file__).resolve().parent/'reports/gui_ai_live'
    out.mkdir(parents=True,exist_ok=True)
    app=W.QApplication([]);QtGui.QFontDatabase.addApplicationFont('C:/Windows/Fonts/segoeui.ttf')
    w=Monitor();w.mode.setCurrentIndex(1);idx=w.port.findData('COM3')
    if idx<0:raise RuntimeError('Bench COM3 unavailable')
    w.port.setCurrentIndex(idx);w.show();w.toggle_connect()
    QtCore.QTimer.singleShot(900,w.toggle_monitor)
    def finish():
        w.tick();app.processEvents();w.grab().save(str(out/'gui_actual_board.png'))
        parser=w.worker.parser if w.worker else w.parser
        result=dict(scope='Actual UART -> production Qt GUI; offscreen rendering; no simulated predictions',
            fields={k:v.text() for k,v in w.ai_fields.items()},sample_count=w.session.total,
            crc=parser.crc_failures,missing=parser.lost_samples,framing=parser.framing_errors,schema=parser.schema_errors,
            acquisition_classification=w.session.status.get('classification','UNKNOWN'),model_status=w.session.status.get('model','UNKNOWN'),
            raw_capture=str(w.worker.capture_path) if w.worker and hasattr(w.worker,'capture_path') else 'See tools/ecg_monitor/captures')
        result['status']='PASS' if result['sample_count']>1000 and all(result[k]==0 for k in ['crc','missing','framing','schema']) and result['fields']['Classification']=={'NORMAL':'NORMAL (N)','PVC':'PVC (V)'}.get(w.session.ai_display()['prediction'],'UNKNOWN') else 'FAIL'
        (out/'gui_board_results.json').write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')
        print(result['status'],result['sample_count'],result['fields']['Classification'],flush=True)
        w.close();app.quit()
    QtCore.QTimer.singleShot(15000,finish);app.exec()
if __name__=='__main__':main()
