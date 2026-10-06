import asyncio
import json
import subprocess
import sys
import uuid
from pathlib import Path

from .asr import VolcRecognizer
from .targets import capture_target, insert_text
from .codex_active import resolve_active_codex_task


class VoiceController:
    def __init__(self, loop, store, on_mode_changed=None, overlay=None):
        self.loop = loop
        self.store = store
        self.state = "idle"
        self.message = "按住 F8 开始说话"
        self.last_text = ""
        self.target_name = ""
        self.mode = "focused"
        self._audio = None
        self._queue = None
        self._stop = None
        self._task = None
        self._target = None
        self._held = False
        self.on_mode_changed = on_mode_changed
        self.overlay = overlay
        self.mode = store.load(include_secrets=False).get("output", "focused")
        self.mode_hotkey_ok = None
        self.record_hotkey_name = store.load(include_secrets=False).get("recordHotkey", "F8")
        self.mode_hotkey_name = store.load(include_secrets=False).get("modeHotkey", "Ctrl+Alt+9")
        self.mode_hotkey_error = ""

    def status(self):
        return {"state": self.state, "message": self.message, "lastText": self.last_text,
                "target": self.target_name, "mode": self.mode,
                "modeHotkeyOk": self.mode_hotkey_ok, "modeHotkeyError": self.mode_hotkey_error,
                "recordHotkey": self.record_hotkey_name, "modeHotkey": self.mode_hotkey_name}

    def press(self):
        self._held = True
        if self.overlay:
            self.overlay.show("正在聆听…")
        self.loop.call_soon_threadsafe(lambda: asyncio.create_task(self._begin()))

    def release(self):
        self._held = False
        self.loop.call_soon_threadsafe(self._finish_capture)

    def toggle_output(self):
        self.loop.call_soon_threadsafe(self._toggle_output)

    def _toggle_output(self):
        next_mode = "codex" if self.store.load(include_secrets=False).get("output") == "focused" else "focused"
        self.store.save({"output": next_mode})
        self.mode = next_mode
        label = "Codex 当前任务" if next_mode == "codex" else "当前聚焦输入框"
        if self.state == "idle":
            self.message = f"已切换到 {label}；按住 F8 开始说话"
        if self.on_mode_changed:
            self.on_mode_changed(next_mode)

    async def _begin(self):
        if self.state != "idle" or not self._held:
            return
        try:
            import sounddevice as sd
            cfg = self.store.load()
            self.mode = cfg["output"]
            self._target = capture_target() if self.mode == "focused" else None
            if self.mode == "codex" and cfg.get("autoFollowCodex", True):
                active = await asyncio.to_thread(resolve_active_codex_task, cfg.get("threadId", ""))
                cfg = dict(cfg)
                cfg["threadId"] = active["id"]
                self.target_name = active["title"]
                if active.get("ambiguous"):
                    self.message = "检测到同名任务，已锁定最近匹配项"
            else:
                self.target_name = self._target.title if self._target else cfg.get("threadId", "")
            if self.mode == "codex" and not cfg.get("threadId"):
                raise RuntimeError("未识别到 Codex 当前任务，且没有备用任务 ID")
            self._queue = asyncio.Queue(maxsize=80)
            self._stop = asyncio.Event()
            self.state, self.message = "recording", f"正在聆听 → {self.target_name}"

            def audio_callback(indata, frames, time_info, status):
                if status:
                    self.loop.call_soon_threadsafe(self._set_message, f"音频提示：{status}")
                chunk = bytes(indata)
                self.loop.call_soon_threadsafe(self._put_audio, chunk)

            self._audio = sd.RawInputStream(samplerate=16000, blocksize=3200, channels=1,
                                            dtype="int16", callback=audio_callback)
            self._audio.start()
            if not self._held:
                self._finish_capture()
            recognizer = VolcRecognizer(cfg, self._queue, self._stop, self._on_text)
            self._task = asyncio.create_task(self._recognize_and_deliver(recognizer, cfg))
        except Exception as exc:
            self.state, self.message = "idle", f"启动失败：{exc}"
            if self.overlay:
                self.overlay.finish(self.message, 3000)
            self._close_audio()

    def _put_audio(self, chunk):
        if self.state != "recording" or not self._queue:
            return
        if self._queue.full():
            self.state, self.message = "error", "音频积压，已停止；文字不会盲目投递"
            self._finish_capture()
            return
        self._queue.put_nowait(chunk)

    def _finish_capture(self):
        if self.state != "recording":
            return
        self.state, self.message = "recognizing", "等待最终识别结果"
        if self.overlay:
            self.overlay.update("正在生成最终识别结果…")
        self._close_audio()
        self._stop.set()
        if self._queue and not self._queue.full():
            self._queue.put_nowait(None)

    def _close_audio(self):
        audio, self._audio = self._audio, None
        if audio:
            try:
                audio.stop()
                audio.close()
            except Exception:
                pass

    def _set_message(self, message):
        self.message = message

    def _on_text(self, text, final):
        self.last_text = text
        if self.overlay:
            self.overlay.update(text)
        if not final:
            self.message = "识别中：" + text[-30:]

    async def _recognize_and_deliver(self, recognizer, cfg):
        try:
            text = await recognizer.run()
            self.last_text = text
            if not text.strip():
                raise RuntimeError("未识别到有效文字")
            self.state, self.message = "delivering", "正在投递文字"
            if self.mode == "focused":
                count = insert_text(self._target, text)
                self.message = f"已向 {self.target_name} 输入 {count} 个字符"
            else:
                await self._deliver_codex(cfg, text)
                self.message = "Codex 已接收"
            self.state = "idle"
            if self.overlay:
                self.overlay.finish(text, 2000)
        except Exception as exc:
            self.state = "idle"
            self.message = f"未投递，文字已保留：{exc}"
            if self.overlay:
                self.overlay.finish(self.message, 3500)
        finally:
            self._close_audio()

    async def _deliver_codex(self, cfg, text):
        bridge = Path(__file__).with_name("codex_bridge.cjs")
        payload = json.dumps({"threadId": cfg["threadId"], "commandId": str(uuid.uuid4()), "text": text},
                             ensure_ascii=False).encode("utf-8")
        process = await asyncio.create_subprocess_exec(
            "node", str(bridge), stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        out, err = await asyncio.wait_for(process.communicate(payload), 65)
        result = json.loads(out)
        if process.returncode or result.get("error"):
            raise RuntimeError(result.get("error") or err.decode(errors="replace") or "Codex 拒绝投递")
