import ctypes
import re
import threading
from ctypes import wintypes


WM_HOTKEY = 0x0312
WM_QUIT = 0x0012
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000
HOTKEY_ID = 0x5649

ALIASES = {
    "CONTROL": "CTRL", "CTL": "CTRL",
    "OPTION": "ALT",
    "WINDOWS": "WIN", "CMD": "WIN", "META": "WIN",
    "RETURN": "ENTER", "ESCAPE": "ESC",
}
MODIFIERS = {"CTRL", "ALT", "SHIFT", "WIN"}
DISPLAY = {"CTRL": "Ctrl", "ALT": "Alt", "SHIFT": "Shift", "WIN": "Win",
           "SPACE": "Space", "ENTER": "Enter", "ESC": "Esc", "TAB": "Tab"}
SPECIAL_VK = {"SPACE": 0x20, "ENTER": 0x0D, "ESC": 0x1B, "TAB": 0x09,
              "HOME": 0x24, "END": 0x23, "INSERT": 0x2D, "DELETE": 0x2E,
              "PAGEUP": 0x21, "PAGEDOWN": 0x22, "UP": 0x26, "DOWN": 0x28,
              "LEFT": 0x25, "RIGHT": 0x27}


def parse_hotkey(value):
    if not isinstance(value, str):
        raise ValueError("快捷键必须是文字")
    raw = value.strip().replace("＋", "+")
    if raw.upper() == "COPILOT":
        raw = "WIN+SHIFT+F23"
    parts = [p.strip().upper() for p in raw.split("+") if p.strip()]
    parts = [ALIASES.get(p, p) for p in parts]
    if not parts or len(parts) != len(set(parts)):
        raise ValueError("快捷键格式无效")
    main = [p for p in parts if p not in MODIFIERS]
    if len(main) != 1:
        raise ValueError("快捷键必须包含且只能包含一个普通按键")
    key = main[0]
    valid = (len(key) == 1 and key.isalnum()) or re.fullmatch(r"F(?:[1-9]|1[0-9]|2[0-4])", key) or key in SPECIAL_VK
    if not valid:
        raise ValueError(f"不支持的快捷键：{key}")
    modifiers = [m for m in ("CTRL", "ALT", "SHIFT", "WIN") if m in parts]
    return frozenset(modifiers + [key])


def normalize_hotkey(value):
    keys = parse_hotkey(value)
    modifiers = [m for m in ("CTRL", "ALT", "SHIFT", "WIN") if m in keys]
    main = next(k for k in keys if k not in MODIFIERS)
    if keys == frozenset(("WIN", "SHIFT", "F23")):
        return "Copilot"
    return "+".join([DISPLAY.get(k, k) for k in modifiers] + [DISPLAY.get(main, main)])


def _token(key):
    from pynput import keyboard
    if key in (keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r):
        return "CTRL"
    if key in (keyboard.Key.alt, keyboard.Key.alt_l, keyboard.Key.alt_r, keyboard.Key.alt_gr):
        return "ALT"
    if key in (keyboard.Key.shift, keyboard.Key.shift_l, keyboard.Key.shift_r):
        return "SHIFT"
    if key in (keyboard.Key.cmd, keyboard.Key.cmd_l, keyboard.Key.cmd_r):
        return "WIN"
    special = {
        keyboard.Key.space: "SPACE", keyboard.Key.enter: "ENTER", keyboard.Key.esc: "ESC",
        keyboard.Key.tab: "TAB", keyboard.Key.home: "HOME", keyboard.Key.end: "END",
        keyboard.Key.insert: "INSERT", keyboard.Key.delete: "DELETE",
        keyboard.Key.page_up: "PAGEUP", keyboard.Key.page_down: "PAGEDOWN",
        keyboard.Key.up: "UP", keyboard.Key.down: "DOWN",
        keyboard.Key.left: "LEFT", keyboard.Key.right: "RIGHT",
    }
    if key in special:
        return special[key]
    name = getattr(key, "name", "")
    if re.fullmatch(r"f(?:[1-9]|1[0-9]|2[0-4])", name or ""):
        return name.upper()
    char = getattr(key, "char", None)
    return char.upper() if char and len(char) == 1 else None


class RecordingHotkey:
    def __init__(self, controller, hotkey):
        from pynput import keyboard
        self.controller = controller
        self.keys = parse_hotkey(hotkey)
        self.pressed = set()
        self.active = False
        self.is_copilot = self.keys == frozenset(("WIN", "SHIFT", "F23"))
        self.listener = keyboard.Listener(on_press=self._press, on_release=self._release,
                                          win32_event_filter=self._filter)

    def start(self):
        self.listener.start()
        return True

    def _filter(self, msg, data):
        # The dedicated Copilot key emits Win+Shift+F23. pynput does not call
        # the normal key callback after suppress_event(), so handle the F23
        # edge here before suppressing it.
        if self.is_copilot and getattr(data, "vkCode", None) == 0x86:
            if msg in (0x0100, 0x0104) and not self.active:
                self.active = True
                self.controller.press()
            elif msg in (0x0101, 0x0105) and self.active:
                self.active = False
                self.controller.release()
            self.listener.suppress_event()
        return True

    def _press(self, key):
        token = _token(key)
        if token:
            self.pressed.add(token)
        if not self.active and self.keys.issubset(self.pressed):
            self.active = True
            self.controller.press()

    def _release(self, key):
        token = _token(key)
        was_active = self.active
        if token:
            self.pressed.discard(token)
        if was_active and not self.keys.issubset(self.pressed):
            self.active = False
            self.controller.release()

    def stop(self):
        if self.active:
            self.controller.release()
        self.listener.stop()


def _vk(key):
    if key in SPECIAL_VK:
        return SPECIAL_VK[key]
    if re.fullmatch(r"F(?:[1-9]|1[0-9]|2[0-4])", key):
        return 0x70 + int(key[1:]) - 1
    return ord(key)


class GlobalModeHotkey:
    def __init__(self, callback, hotkey):
        self.callback = callback
        self.keys = parse_hotkey(hotkey)
        self.thread_id = None
        self.error = None
        self.ready = threading.Event()
        self.trigger_count = 0
        self.thread = threading.Thread(target=self._run, name="voicein-mode-hotkey", daemon=True)

    def start(self):
        self.thread.start()
        self.ready.wait(2)
        return self.error is None

    def _run(self):
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        self.thread_id = kernel32.GetCurrentThreadId()
        modifiers = MOD_NOREPEAT
        for token, flag in (("CTRL", MOD_CONTROL), ("ALT", MOD_ALT), ("SHIFT", MOD_SHIFT), ("WIN", MOD_WIN)):
            if token in self.keys:
                modifiers |= flag
        main = next(k for k in self.keys if k not in MODIFIERS)
        if not user32.RegisterHotKey(None, HOTKEY_ID, modifiers, _vk(main)):
            self.error = ctypes.WinError()
            self.ready.set()
            return
        self.ready.set()
        message = wintypes.MSG()
        try:
            while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
                if message.message == WM_HOTKEY and message.wParam == HOTKEY_ID:
                    self.trigger_count += 1
                    self.callback()
        finally:
            user32.UnregisterHotKey(None, HOTKEY_ID)

    def stop(self):
        if self.thread_id:
            ctypes.windll.user32.PostThreadMessageW(self.thread_id, WM_QUIT, 0, 0)
        if self.thread.is_alive():
            self.thread.join(timeout=2)
