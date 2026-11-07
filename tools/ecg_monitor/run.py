if __name__=='__main__':
    try:
        from ecg_monitor.app import main
        raise SystemExit(main())
    except Exception:
        import traceback
        from pathlib import Path
        error=traceback.format_exc();path=Path(__file__).parent/'reports/startup_error.txt'
        path.parent.mkdir(exist_ok=True);path.write_text(error,encoding='utf-8')
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None,'ECG Monitor could not start. Run setup.bat. Details: '+str(path),'ECG Monitor',16)
        except (ImportError,AttributeError):print(error)
        raise SystemExit(1)
