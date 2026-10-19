"""Frozen control entry point with an explicit, hardware-free diagnosis mode."""
import sys
import traceback

from startup_diagnostics import diagnose, prepare_windowed_streams


if __name__ == '__main__':
    prepare_windowed_streams()
    if '--diagnose-startup' in sys.argv:
        sys.exit(diagnose('control'))
    try:
        from app import main
        main()
    except Exception as exc:
        from portable_paths import runtime_paths
        path = runtime_paths().data_path('logs/g10-control-last-error.txt')
        path.write_text(traceback.format_exc(), encoding='utf-8')
        from tkinter import Tk, messagebox
        root = Tk()
        root.withdraw()
        messagebox.showerror('G10 Control 未能启动', f'{exc}\n\n诊断日志：{path}', parent=root)
        root.destroy()
        sys.exit(1)
