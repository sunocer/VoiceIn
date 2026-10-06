import asyncio
import json
import uuid

import aiohttp

from .volc_protocol import configuration, decode, frame


class VolcRecognizer:
    def __init__(self, config, audio_queue, stop_event, on_text=None):
        self.config = config
        self.audio_queue = audio_queue
        self.stop_event = stop_event
        self.on_text = on_text

    async def run(self):
        request_id = str(uuid.uuid4())
        endpoint, headers, payload = configuration(self.config, request_id)
        final_text = ""
        timeout = aiohttp.ClientTimeout(total=None, sock_connect=15)
        async with aiohttp.ClientSession(timeout=timeout) as client:
            async with client.ws_connect(endpoint, headers=headers, max_msg_size=2 * 1024 * 1024) as cloud:
                await cloud.send_bytes(frame(json.dumps(payload).encode("utf-8")))
                initial = await cloud.receive(timeout=20)
                parsed = self._parse(initial)
                if parsed["code"] is not None:
                    raise RuntimeError(f"火山错误 {parsed['code']}: {parsed['payload']}")

                async def send_audio():
                    total = 0
                    while True:
                        try:
                            chunk = await asyncio.wait_for(self.audio_queue.get(), timeout=.2)
                        except asyncio.TimeoutError:
                            if self.stop_event.is_set():
                                break
                            continue
                        if chunk is None:
                            break
                        total += len(chunk)
                        if total > 16000 * 2 * 180:
                            raise RuntimeError("单次录音达到 3 分钟测试上限")
                        await cloud.send_bytes(frame(chunk, audio=True))
                    await cloud.send_bytes(frame(b"", audio=True, final=True))

                sender = asyncio.create_task(send_audio())
                try:
                    while True:
                        message = await cloud.receive(timeout=45)
                        parsed = self._parse(message)
                        if parsed["code"] is not None:
                            raise RuntimeError(f"火山错误 {parsed['code']}: {parsed['payload']}")
                        result = parsed["payload"].get("result", {})
                        if isinstance(result, list):
                            result = result[0] if result else {}
                        text = result.get("text", "")
                        if text:
                            final_text = text
                            if self.on_text:
                                self.on_text(text, parsed["final"])
                        if parsed["final"]:
                            await sender
                            return final_text
                finally:
                    sender.cancel()
                    await asyncio.gather(sender, return_exceptions=True)

    @staticmethod
    def _parse(message):
        if message.type != aiohttp.WSMsgType.BINARY:
            raise RuntimeError("火山连接提前结束")
        return decode(message.data)
