import base64
import ctypes
import json
import os
import shutil
from ctypes import wintypes
from pathlib import Path


class DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


def _blob(data: bytes):
    buffer = ctypes.create_string_buffer(data)
    return DATA_BLOB(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte))), buffer


def protect(value: str) -> str:
    if not value:
        return ""
    source, keep = _blob(value.encode("utf-8"))
    target = DATA_BLOB()
    if not ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(source), "VoiceIn", None, None, None, 0, ctypes.byref(target)
    ):
        raise ctypes.WinError()
    try:
        raw = ctypes.string_at(target.pbData, target.cbData)
        return base64.b64encode(raw).decode("ascii")
    finally:
        ctypes.windll.kernel32.LocalFree(target.pbData)


def unprotect(value: str) -> str:
    if not value:
        return ""
    source, keep = _blob(base64.b64decode(value, validate=True))
    target = DATA_BLOB()
    if not ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(source), None, None, None, None, 0, ctypes.byref(target)
    ):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(target.pbData, target.cbData).decode("utf-8")
    finally:
        ctypes.windll.kernel32.LocalFree(target.pbData)


DEFAULTS = {
    "auth": "legacy",
    "endpoint": "bigmodel_async",
    "resource": "volc.bigasr.sauc.duration",
    "itn": True,
    "punc": True,
    "ddc": False,
    "output": "focused",
    "threadId": "",
    "autoFollowCodex": True,
    "recordHotkey": "F8",
    "modeHotkey": "Ctrl+Alt+9",
    "autostart": True,
}
SECRET_FIELDS = ("appid", "token", "apikey")


class ConfigStore:
    def __init__(self, path=None):
        base = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "VoiceIn"
        self.path = Path(path) if path else base / "config.json"

    @property
    def backup_path(self):
        return self.path.with_name("config.backup.json")

    @property
    def legacy_backup_path(self):
        return self.path.with_suffix(".json.bak")

    def load(self, include_secrets=True):
        last_error = None
        for candidate in (self.path, self.backup_path, self.legacy_backup_path):
            if not candidate.exists():
                continue
            try:
                saved = json.loads(candidate.read_text(encoding="utf-8"))
                data = dict(DEFAULTS)
                data.update({k: v for k, v in saved.items() if k != "secrets"})
                if include_secrets:
                    for key, value in saved.get("secrets", {}).items():
                        if key in SECRET_FIELDS:
                            data[key] = unprotect(value)
                for key in SECRET_FIELDS:
                    data.setdefault(key, "")
                return data
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                last_error = exc
        if last_error:
            raise ValueError(f"主配置和备份均无法读取：{last_error}")
        data = dict(DEFAULTS)
        for key in SECRET_FIELDS:
            data[key] = ""
        return data

    def public(self):
        full = self.load(include_secrets=True)
        data = {key: full[key] for key in DEFAULTS}
        data["configured"] = {key: bool(full.get(key)) for key in SECRET_FIELDS}
        appid = str(full.get("appid", ""))
        data["appidHint"] = (appid[:3] + "…" + appid[-4:]) if len(appid) > 7 else ("已保存" if appid else "")
        data["configPath"] = str(self.path)
        return data

    def save(self, incoming):
        old = self.load() if self.path.exists() else {**DEFAULTS, **{k: "" for k in SECRET_FIELDS}}
        allowed = set(DEFAULTS) | set(SECRET_FIELDS)
        merged = {**old, **{k: v for k, v in incoming.items() if k in allowed}}
        if merged["auth"] not in ("legacy", "apikey"):
            raise ValueError("无效鉴权方式")
        if merged["output"] not in ("focused", "codex"):
            raise ValueError("无效输出目标")
        if merged["endpoint"] not in ("bigmodel_async", "bigmodel", "bigmodel_nostream"):
            raise ValueError("无效识别接口")
        if merged["resource"] not in ("volc.seedasr.sauc.duration", "volc.bigasr.sauc.duration"):
            raise ValueError("无效语音识别模型")
        if not isinstance(merged.get("threadId"), str) or len(merged["threadId"]) > 80:
            raise ValueError("无效 Codex 任务 ID")
        from .hotkeys import normalize_hotkey
        merged["recordHotkey"] = normalize_hotkey(merged["recordHotkey"])
        merged["modeHotkey"] = normalize_hotkey(merged["modeHotkey"])
        if merged["recordHotkey"].lower() == merged["modeHotkey"].lower():
            raise ValueError("录音和模式切换不能使用同一个快捷键")
        secrets = {key: protect(str(merged.get(key, ""))) for key in SECRET_FIELDS}
        plain = {key: merged[key] for key in DEFAULTS}
        plain["secrets"] = secrets
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(".tmp")
        temp.write_text(json.dumps(plain, ensure_ascii=False, indent=2), encoding="utf-8")
        # Keep the last known-good configuration for recovery from interrupted
        # writes, sync conflicts, or manual corruption.
        if self.path.exists():
            try:
                json.loads(self.path.read_text(encoding="utf-8"))
                shutil.copy2(self.path, self.backup_path)
            except (OSError, ValueError, json.JSONDecodeError):
                pass
        os.replace(temp, self.path)
        return self.public()
