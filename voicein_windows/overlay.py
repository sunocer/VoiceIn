import ctypes
import queue
import threading
import tkinter as tk


class RecognitionOverlay:
    """Thread-owned, non-activating caption window for live recognition text."""

    def __init__(self):
        self._commands = queue.Queue()
        self._thread = threading.Thread(target=self._run, name="VoiceInOverlay", daemon=True)
        self._thread.start()

    def show(self, text="正在聆听…"):
        self._commands.put(("show", text, 0))

    def update(self, text):
        self._commands.put(("update", text, 0))

    def finish(self, text, delay_ms=2000):
        self._commands.put(("finish", text, delay_ms))

    def hide(self):
        self._commands.put(("hide", "", 0))

    def stop(self):
        self._commands.put(("stop", "", 0))

    def _run(self):
        root = tk.Tk()
        root.withdraw()
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        root.configure(bg="#101816")
        frame = tk.Frame(root, bg="#101816", highlightbackground="#347d65", highlightthickness=1, padx=16, pady=12)
        frame.pack(fill="both", expand=True)
        title = tk.Label(frame, text="VOICEIN · 正在聆听", fg="#75d6b4", bg="#101816", font=("Microsoft YaHei UI", 9, "bold"), anchor="w")
        title.pack(fill="x", pady=(0, 6))
        label = tk.Label(frame, text="", fg="#f3f7f5", bg="#101816", font=("Microsoft YaHei UI", 13), anchor="w", justify="left", wraplength=420)
        label.pack(fill="both", expand=True)
        hide_job = {"id": None}

        def cancel_hide():
            if hide_job["id"] is not None:
                root.after_cancel(hide_job["id"])
                hide_job["id"] = None

        def place_without_focus():
            root.update_idletasks()
            width = min(460, max(300, root.winfo_reqwidth()))
            height = min(220, max(86, root.winfo_reqheight()))
            x = root.winfo_screenwidth() - width - 24
            y = root.winfo_screenheight() - height - 72
            root.geometry(f"{width}x{height}+{x}+{y}")
            root.deiconify()
            root.update_idletasks()
            try:
                hwnd = root.winfo_id()
                user32 = ctypes.windll.user32
                style = user32.GetWindowLongW(hwnd, -20)
                user32.SetWindowLongW(hwnd, -20, style | 0x80 | 0x08000000)
                user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010)
            except Exception:
                pass

        def drain():
            try:
                while True:
                    action, text, delay = self._commands.get_nowait()
                    if action == "stop":
                        root.destroy()
                        return
                    if action == "hide":
                        cancel_hide()
                        root.withdraw()
                        continue
                    if action == "show":
                        cancel_hide()
                        title.configure(text="VOICEIN · 正在聆听", fg="#75d6b4")
                        label.configure(text=text or "正在聆听…")
                        place_without_focus()
                    elif action == "update":
                        cancel_hide()
                        title.configure(text="VOICEIN · 实时识别", fg="#75d6b4")
                        label.configure(text=text or "正在聆听…")
                        place_without_focus()
                    elif action == "finish":
                        cancel_hide()
                        title.configure(text="VOICEIN · 识别完成", fg="#f0bd62")
                        label.configure(text=text)
                        place_without_focus()
                        hide_job["id"] = root.after(delay, root.withdraw)
            except queue.Empty:
                pass
            root.after(30, drain)

        root.after(0, drain)
        root.mainloop()
