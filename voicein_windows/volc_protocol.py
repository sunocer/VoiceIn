"""Volcengine SAUC V3 framing used by the desktop client."""
import gzip
import io
import json
import struct

def frame(payload: bytes, *, audio=False, final=False):
    body = gzip.compress(payload)
    return bytes([0x11, (0x20 if audio else 0x10) | (2 if final else 0),
                  0x01 if audio else 0x11, 0]) + struct.pack(">I", len(body)) + body


def decode(data: bytes):
    if len(data) < 8 or data[0] >> 4 != 1:
        raise ValueError("无效的 V3 响应头")
    offset = (data[0] & 15) * 4
    kind, flags = data[1] >> 4, data[1] & 15
    serialization, compression = data[2] >> 4, data[2] & 15
    if offset < 4 or kind not in (9, 15):
        raise ValueError("不支持的响应类型")

    def integer(signed=False):
        nonlocal offset
        if offset + 4 > len(data):
            raise ValueError("响应帧被截断")
        value = struct.unpack_from(">i" if signed else ">I", data, offset)[0]
        offset += 4
        return value

    code = integer() if kind == 15 else None
    sequence = integer(True) if kind == 9 and flags & 1 else None
    size = integer()
    if len(data) - offset != size:
        raise ValueError("响应长度不匹配")
    body = data[offset:]
    if compression == 1:
        with gzip.GzipFile(fileobj=io.BytesIO(body)) as stream:
            body = stream.read(2 * 1024 * 1024 + 1)
        if len(body) > 2 * 1024 * 1024:
            raise ValueError("响应过大")
    elif compression != 0:
        raise ValueError("不支持的响应压缩类型")
    text = body.decode("utf-8")
    try:
        payload = json.loads(text) if serialization == 1 else {"message": text}
    except json.JSONDecodeError:
        payload = {"message": text}
    return {"payload": payload, "final": bool(flags & 2), "sequence": sequence, "code": code}


ENDPOINTS = {name: "wss://openspeech.bytedance.com/api/v3/sauc/" + name
             for name in ("bigmodel_async", "bigmodel", "bigmodel_nostream")}


def configuration(config, request_id):
    def field(name):
        value = str(config.get(name, "")).strip()
        if not value or len(value) > 2048 or any(ord(char) < 32 for char in value):
            raise ValueError(f"请检查 {name} 参数")
        return value

    endpoint = ENDPOINTS.get(config.get("endpoint"))
    if not endpoint:
        raise ValueError("请选择官方识别接口")
    headers = {"X-Api-Resource-Id": field("resource"), "X-Api-Connect-Id": request_id,
               "X-Api-Request-Id": request_id, "X-Api-Sequence": "-1"}
    if config.get("auth") == "legacy":
        headers.update({"X-Api-App-Key": field("appid"), "X-Api-Access-Key": field("token")})
    elif config.get("auth") == "apikey":
        headers["X-Api-Key"] = field("apikey")
    else:
        raise ValueError("请选择鉴权方式")
    payload = {
        "user": {"uid": "voicein-windows"},
        "audio": {"format": "pcm", "codec": "raw", "rate": 16000, "bits": 16, "channel": 1},
        "request": {"model_name": "bigmodel", "show_utterances": True, "result_type": "full",
                    "enable_itn": bool(config.get("itn", True)),
                    "enable_punc": bool(config.get("punc", True)),
                    "enable_ddc": bool(config.get("ddc", False))},
    }
    return endpoint, headers, payload

