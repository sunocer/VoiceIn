import sys
from pathlib import Path

def enable_high_dpi():
    """Use native per-monitor DPI rendering before creating tray or Tk windows."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        if ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
            return
    except Exception:
        pass
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return
    except Exception:
        pass
    try:
        import ctypes
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


enable_high_dpi()


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from voicein_windows.app import main


def install_crash_logging():
    import datetime
    import os
    import threading
    import traceback

    log_dir = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "VoiceIn"
    log_path = log_dir / "crash.log"

    def write_exception(kind, exc_type, exc_value, exc_tb):
        try:
            log_dir.mkdir(parents=True, exist_ok=True)
            with log_path.open("a", encoding="utf-8") as handle:
                handle.write(f"\n[{datetime.datetime.now().isoformat()}] {kind}\n")
                traceback.print_exception(exc_type, exc_value, exc_tb, file=handle)
        except Exception:
            pass

    sys.excepthook = lambda t, v, tb: write_exception("main", t, v, tb)
    previous = threading.excepthook
    def thread_hook(args):
        write_exception(f"thread:{args.thread.name}", args.exc_type, args.exc_value, args.exc_traceback)
        previous(args)
    threading.excepthook = thread_hook


install_crash_logging()
try:
    main()
except BaseException:
    sys.excepthook(*sys.exc_info())

