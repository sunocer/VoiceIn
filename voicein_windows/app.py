import asyncio
import os
import secrets
import webbrowser
import socket
import subprocess
import sys
import sqlite3
from pathlib import Path

from aiohttp import web

from .config import ConfigStore
from .controller import VoiceController
from .startup import create_manual_shortcuts, set_autostart
from .tray import Tray
from .hotkeys import GlobalModeHotkey, RecordingHotkey
from .overlay import RecognitionOverlay
from .codex_tasks import discover_codex_tasks


ROOT = Path(__file__).parent / "static"


def _authorized(request):
    expected = request.app["session_token"]
    origin = request.headers.get("Origin")
    return (request.cookies.get("voicein_session") == expected and
            (not origin or origin == "http://127.0.0.1:8766"))


async def index(request):
    response = web.FileResponse(ROOT / "index.html")
    response.set_cookie("voicein_session", request.app["session_token"], httponly=True,
                        samesite="Strict", max_age=8 * 3600)
    response.headers["Cache-Control"] = "no-store"
    return response


async def static(request):
    name = request.match_info["name"]
    if name not in ("app.js", "style.css"):
        raise web.HTTPNotFound()
    return web.FileResponse(ROOT / name, headers={"Cache-Control": "no-store"})


async def api_config(request):
    if not _authorized(request):
        raise web.HTTPForbidden()
    store = request.app["store"]
    if request.method == "GET":
        return web.json_response(store.public())
    try:
        data = await request.json()
        saved = store.save(data)
        install_hotkeys(request.app, saved)
        return web.json_response(saved)
    except ValueError as exc:
        return web.json_response({"ok": False, "message": str(exc)}, status=400)
    except PermissionError:
        return web.json_response(
            {"ok": False, "message": "无法写入 Windows 用户配置目录，请从正常桌面用户环境重新启动 VoiceIn。"},
            status=503,
        )
    except OSError as exc:
        return web.json_response({"ok": False, "message": f"保存配置失败：{exc}"}, status=500)


async def api_status(request):
    if not _authorized(request):
        raise web.HTTPForbidden()
    status = request.app["controller"].status()
    hotkey = request.app.get("mode_hotkey")
    status["modeHotkeyAlive"] = bool(hotkey and hotkey.thread.is_alive())
    status["modeHotkeyTriggers"] = hotkey.trigger_count if hotkey else 0
    return web.json_response(status)


async def api_codex_tasks(request):
    if not _authorized(request):
        raise web.HTTPForbidden()
    try:
        tasks = await asyncio.to_thread(discover_codex_tasks)
        return web.json_response({"ok": True, "tasks": tasks})
    except (OSError, sqlite3.Error, RuntimeError, ValueError) as exc:
        return web.json_response({"ok": False, "message": f"无法读取 Codex 任务：{exc}", "tasks": []}, status=503)


def install_hotkeys(app, config):
    controller = app["controller"]
    controller.record_hotkey_name = config["recordHotkey"]
    controller.mode_hotkey_name = config["modeHotkey"]
    old_record = app.pop("record_hotkey", None)
    old_mode = app.pop("mode_hotkey", None)
    if old_record:
        old_record.stop()
    if old_mode:
        old_mode.stop()
    controller.release()
    record = RecordingHotkey(controller, config["recordHotkey"])
    record.start()
    mode = GlobalModeHotkey(controller.toggle_output, config["modeHotkey"])
    controller.mode_hotkey_ok = mode.start()
    controller.mode_hotkey_error = "" if controller.mode_hotkey_ok else str(mode.error)
    if not controller.mode_hotkey_ok:
        controller.message = f"{config['modeHotkey']} 注册失败，可能已被其他程序占用：{mode.error}"
    elif controller.state == "idle":
        controller.message = f"按住 {config['recordHotkey']} 开始说话"
    app["record_hotkey"] = record
    app["mode_hotkey"] = mode


async def on_startup(app):
    loop = asyncio.get_running_loop()
    overlay = RecognitionOverlay()
    app["overlay"] = overlay
    controller = VoiceController(loop, app["store"], overlay=overlay)
    app["controller"] = controller
    tray = Tray(controller)
    controller.on_mode_changed = tray.mode_changed
    tray.start()
    app["tray"] = tray
    try:
        set_autostart(bool(app["store"].load(include_secrets=False).get("autostart", True)))
        create_manual_shortcuts()
    except (OSError, subprocess.SubprocessError) as exc:
        controller.message = f"启动入口设置失败：{exc}"
    app["install_hotkeys"] = install_hotkeys
    install_hotkeys(app, app["store"].load(include_secrets=False))
    async def update_tray():
        last_hotkey_restart = 0.0
        while True:
            tray.update()
            record = app.get("record_hotkey")
            if record and not record.listener.is_alive():
                now = loop.time()
                if now - last_hotkey_restart >= 5:
                    last_hotkey_restart = now
                    controller.message = "录音快捷键监听中断，正在自动恢复"
                    try:
                        install_hotkeys(app, app["store"].load(include_secrets=False))
                    except Exception as exc:
                        controller.message = f"快捷键恢复失败；可从桌面重新启动 VoiceIn：{exc}"
            await asyncio.sleep(.5)
    app["tray_task"] = asyncio.create_task(update_tray())
    if os.environ.get("VOICEIN_NO_BROWSER") != "1":
        loop.call_later(1, lambda: webbrowser.open("http://127.0.0.1:8766/"))


async def on_cleanup(app):
    app.get("record_hotkey") and app["record_hotkey"].stop()
    app.get("mode_hotkey") and app["mode_hotkey"].stop()
    if app.get("tray_task"):
        app["tray_task"].cancel()
    app.get("tray") and app["tray"].stop()
    app.get("overlay") and app["overlay"].stop()


def create_app(config_path=None):
    app = web.Application(client_max_size=32768)
    app["session_token"] = secrets.token_urlsafe(32)
    app["store"] = ConfigStore(config_path)
    app.router.add_get("/", index)
    app.router.add_get("/{name:app.js|style.css}", static)
    app.router.add_route("*", "/api/config", api_config)
    app.router.add_get("/api/status", api_status)
    app.router.add_get("/api/codex/tasks", api_codex_tasks)
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
    return app


def main():
    try:
        with socket.create_connection(("127.0.0.1", 8766), timeout=.4):
            if "--background" not in sys.argv:
                webbrowser.open("http://127.0.0.1:8766/")
            return
    except OSError:
        pass
    if "--background" in sys.argv:
        os.environ["VOICEIN_NO_BROWSER"] = "1"
    web.run_app(create_app(), host="127.0.0.1", port=8766, access_log=None)


if __name__ == "__main__":
    main()
