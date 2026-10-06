import tempfile
import unittest
import asyncio
from pathlib import Path

from voicein_windows.config import ConfigStore, protect, unprotect
from voicein_windows.controller import VoiceController
from voicein_windows.hotkeys import normalize_hotkey, parse_hotkey
from voicein_windows.targets import INPUT, KEYBDINPUT
from voicein_windows.volc_protocol import configuration, decode, frame
import ctypes
import gzip
import json
import struct
import sqlite3

from voicein_windows.codex_tasks import discover_codex_tasks
from voicein_windows.codex_active import match_active_task


class ConfigTests(unittest.TestCase):
    def test_dpapi_roundtrip_and_public_redaction(self):
        secret = "仅用于自动化测试-token"
        self.assertEqual(unprotect(protect(secret)), secret)
        with tempfile.TemporaryDirectory() as folder:
            store = ConfigStore(Path(folder) / "config.json")
            store.save({"appid": "app-test", "token": secret, "output": "focused"})
            raw = store.path.read_text(encoding="utf-8")
            self.assertNotIn(secret, raw)
            self.assertEqual(store.load()["token"], secret)
            public = store.public()
            self.assertNotIn("token", public)
            self.assertTrue(public["configured"]["token"])

    def test_rejects_invalid_resource_model(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError):
                ConfigStore(Path(folder) / "config.json").save({"resource": "unknown.model"})

    def test_recovers_from_backup(self):
        with tempfile.TemporaryDirectory() as folder:
            store = ConfigStore(Path(folder) / "config.json")
            store.save({"appid": "app-one", "token": "token-one", "threadId": "task-one"})
            store.save({"appid": "app-two", "token": "token-two", "threadId": "task-two"})
            store.path.write_text("{broken", encoding="utf-8")
            recovered = store.load()
            self.assertEqual(recovered["appid"], "app-one")
            self.assertEqual(recovered["threadId"], "task-one")

    def test_rejects_invalid_output(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError):
                ConfigStore(Path(folder) / "config.json").save({"output": "send-enter"})


class HotkeyTests(unittest.TestCase):
    def test_copilot_alias(self):
        expected = frozenset(("WIN", "SHIFT", "F23"))
        self.assertEqual(parse_hotkey("Copilot"), expected)
        self.assertEqual(parse_hotkey("Win+Shift+F23"), expected)
        self.assertEqual(normalize_hotkey("Win+Shift+F23"), "Copilot")

    def test_rejects_invalid_hotkey(self):
        with self.assertRaises(ValueError):
            parse_hotkey("Ctrl+Alt")


class StubLoop:
    def call_soon_threadsafe(self, callback, *args):
        callback(*args)


class ControllerTests(unittest.TestCase):
    def test_release_while_idle_is_safe(self):
        with tempfile.TemporaryDirectory() as folder:
            controller = VoiceController(StubLoop(), ConfigStore(Path(folder) / "config.json"))
            controller.release()
            self.assertEqual(controller.status()["state"], "idle")
            self.assertFalse(controller._held)

    def test_fast_release_clears_held_before_start(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as folder:
                controller = VoiceController(StubLoop(), ConfigStore(Path(folder) / "config.json"))
                controller.press()
                controller.release()
                await asyncio.sleep(0)
                self.assertFalse(controller._held)
                self.assertEqual(controller.state, "idle")
        asyncio.run(scenario())

    def test_toggle_persists_next_mode(self):
        with tempfile.TemporaryDirectory() as folder:
            store = ConfigStore(Path(folder) / "config.json")
            store.save({"output": "focused"})
            changed = []
            controller = VoiceController(StubLoop(), store, changed.append)
            controller.toggle_output()
            self.assertEqual(store.load(include_secrets=False)["output"], "codex")
            self.assertEqual(controller.mode, "codex")
            self.assertEqual(changed, ["codex"])


class CodexTaskDiscoveryTests(unittest.TestCase):
    def test_discovers_recent_user_tasks_and_excludes_archived(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Path(folder) / "state_5.sqlite"
            connection = sqlite3.connect(db)
            connection.execute("""CREATE TABLE threads (
                id TEXT PRIMARY KEY, title TEXT, name TEXT, first_user_message TEXT,
                cwd TEXT, archived INTEGER, thread_source TEXT, recency_at_ms INTEGER
            )""")
            connection.executemany(
                "INSERT INTO threads VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    ("11111111-1111-1111-1111-111111111111", "较旧任务", "", "", r"\?\C:\old", 0, "user", 1000),
                    ("22222222-2222-2222-2222-222222222222", "较新任务", "显示名称", "", r"\?\D:\new", 0, "user", 2000),
                    ("33333333-3333-3333-3333-333333333333", "已归档", "", "", r"C:\archived", 1, "user", 3000),
                    ("44444444-4444-4444-4444-444444444444", "自动任务", "", "", r"C:\automation", 0, "automation", 4000),
                ],
            )
            connection.commit()
            connection.close()
            tasks = discover_codex_tasks(folder)
            self.assertEqual([task["id"] for task in tasks], [
                "22222222-2222-2222-2222-222222222222",
                "11111111-1111-1111-1111-111111111111",
            ])
            self.assertEqual(tasks[0]["title"], "显示名称")
            self.assertTrue(tasks[0]["cwd"].endswith(r"D:\new"))


class ActiveCodexTaskTests(unittest.TestCase):
    def test_matches_active_title_and_prefers_saved_duplicate(self):
        tasks = [
            {"id": "11111111-1111-1111-1111-111111111111", "title": "同名任务"},
            {"id": "22222222-2222-2222-2222-222222222222", "title": "同名任务"},
        ]
        matched = match_active_task(tasks, "同名任务", tasks[1]["id"])
        self.assertEqual(matched["id"], tasks[1]["id"])
        self.assertTrue(matched["ambiguous"])


class WindowsInputTests(unittest.TestCase):
    def test_sendinput_struct_sizes_match_windows_abi(self):
        expected_input = 40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28
        expected_keyboard = 24 if ctypes.sizeof(ctypes.c_void_p) == 8 else 16
        self.assertEqual(ctypes.sizeof(INPUT), expected_input)
        self.assertEqual(ctypes.sizeof(KEYBDINPUT), expected_keyboard)


class ProtocolTests(unittest.TestCase):
    def test_audio_final_frame_and_configuration(self):
        packet = frame(b"abc", audio=True, final=True)
        self.assertEqual(packet[1], 0x22)
        size = struct.unpack_from(">I", packet, 4)[0]
        self.assertEqual(gzip.decompress(packet[8:8 + size]), b"abc")
        endpoint, headers, payload = configuration({
            "auth": "legacy", "appid": "app", "token": "token",
            "resource": "volc.bigasr.sauc.duration", "endpoint": "bigmodel_async"
        }, "request-id")
        self.assertTrue(endpoint.startswith("wss://openspeech.bytedance.com/"))
        self.assertEqual(headers["X-Api-App-Key"], "app")
        self.assertEqual(payload["audio"]["rate"], 16000)

    def test_decodes_final_response(self):
        body = gzip.compress(json.dumps({"result": {"text": "测试"}}).encode())
        packet = bytes([0x11, 0x92, 0x11, 0]) + struct.pack(">I", len(body)) + body
        parsed = decode(packet)
        self.assertTrue(parsed["final"])
        self.assertEqual(parsed["payload"]["result"]["text"], "测试")


if __name__ == "__main__":
    unittest.main()
