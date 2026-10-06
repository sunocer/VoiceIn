import os
import signal
import threading
import webbrowser

import pystray
from PIL import Image, ImageDraw, ImageFont


COLORS = {
    "idle": (41, 99, 79, 255),
    "recording": (207, 65, 65, 255),
    "recognizing": (214, 145, 42, 255),
    "delivering": (54, 112, 180, 255),
    "error": (160, 55, 55, 255),
}


def make_icon(state="idle"):
    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((4, 4, 60, 60), radius=15, fill=COLORS.get(state, COLORS["idle"]))
    try:
        font = ImageFont.truetype("segoeuib.ttf", 35)
    except OSError:
        font = ImageFont.load_default()
    box = draw.textbbox((0, 0), "V", font=font)
    draw.text(((64 - (box[2] - box[0])) / 2, (61 - (box[3] - box[1])) / 2 - box[1]),
              "V", fill="white", font=font)
    return image


class Tray:
    def __init__(self, controller):
        self.controller = controller
        self.last_state = "idle"
        self.last_title = ""
        self.last_mode = controller.mode
        self.icon = pystray.Icon("VoiceIn", make_icon(), "VoiceIn · 当前聚焦输入框", menu=pystray.Menu(
            pystray.MenuItem(lambda item: self._mode_text(), None, enabled=False),
            pystray.MenuItem("切换输出目标  Ctrl+Alt+9", lambda icon, item: controller.toggle_output()),
            pystray.MenuItem("打开配置", lambda icon, item: webbrowser.open("http://127.0.0.1:8766/"), default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("退出 VoiceIn", self._exit),
        ))

    def _mode_text(self):
        return "当前模式：" + ("Codex 当前任务" if self.controller.mode == "codex" else "当前聚焦输入框")

    def start(self):
        self.icon.run_detached()

    def update(self):
        status = self.controller.status()
        state = status["state"]
        mode = "Codex 当前任务" if status["mode"] == "codex" else "当前聚焦输入框"
        new_title = f"VoiceIn · {mode} · {status['message']}"
        if new_title != self.last_title:
            self.icon.title = new_title
            self.last_title = new_title
        if state != self.last_state:
            self.icon.icon = make_icon(state)
        if status["mode"] != self.last_mode:
            self.icon.update_menu()
            self.last_mode = status["mode"]
        if state != self.last_state:
            if state == "recording":
                self._signal(880)
                self.notify("开始语音输入", f"输出到：{mode}")
            elif state == "recognizing":
                self._signal(660)
                self.notify("录音结束", "正在等待最终识别结果")
            elif state == "idle" and self.last_state in ("recognizing", "delivering"):
                self._signal(1046)
                self.notify("VoiceIn", status["message"])
            self.last_state = state

    def notify(self, title, message):
        try:
            self.icon.notify(message, title)
        except Exception:
            pass

    @staticmethod
    def _signal(frequency):
        def play():
            try:
                import winsound
                winsound.Beep(frequency, 70)
            except Exception:
                pass
        threading.Thread(target=play, daemon=True).start()

    def mode_changed(self, mode):
        label = "Codex 当前任务" if mode == "codex" else "当前聚焦输入框"
        self.notify("输出目标已切换", label)
        self.icon.update_menu()

    def stop(self):
        self.icon.stop()

    @staticmethod
    def _exit(icon=None, item=None):
        os.kill(os.getpid(), signal.SIGTERM)
