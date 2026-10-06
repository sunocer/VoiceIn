import ctypes
from ctypes import wintypes
from dataclasses import dataclass


user32 = ctypes.windll.user32
INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
ULONG_PTR = ctypes.c_size_t


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG), ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD), ("wParamH", wintypes.WORD)]


class INPUT_UNION(ctypes.Union):
    # The full union is required: SendInput validates sizeof(INPUT), which is
    # 40 bytes on 64-bit Windows even for keyboard-only input.
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", INPUT_UNION)]


@dataclass(frozen=True)
class FocusTarget:
    window: int
    process_id: int
    title: str


def capture_target():
    window = user32.GetForegroundWindow()
    if not window:
        raise RuntimeError("没有检测到前台窗口")
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(window, ctypes.byref(pid))
    size = user32.GetWindowTextLengthW(window) + 1
    text = ctypes.create_unicode_buffer(max(size, 1))
    user32.GetWindowTextW(window, text, len(text))
    return FocusTarget(window, pid.value, text.value or "未命名窗口")


def target_is_current(target):
    if not target or not user32.IsWindow(target.window):
        return False
    if user32.GetForegroundWindow() != target.window:
        return False
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(target.window, ctypes.byref(pid))
    return pid.value == target.process_id


def insert_text(target, text):
    if not text.strip():
        raise ValueError("没有可输入的文字")
    if not target_is_current(target):
        raise RuntimeError("原输入窗口已失去焦点，文字已保留，未写入其他位置")
    units = text.encode("utf-16-le")
    inputs = []
    for offset in range(0, len(units), 2):
        code = int.from_bytes(units[offset:offset + 2], "little")
        inputs.append(INPUT(INPUT_KEYBOARD, INPUT_UNION(ki=KEYBDINPUT(0, code, KEYEVENTF_UNICODE, 0, 0))))
        inputs.append(INPUT(INPUT_KEYBOARD, INPUT_UNION(ki=KEYBDINPUT(0, code, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, 0, 0))))
    array = (INPUT * len(inputs))(*inputs)
    sent = user32.SendInput(len(inputs), array, ctypes.sizeof(INPUT))
    if sent != len(inputs):
        raise ctypes.WinError()
    return sent // 2
