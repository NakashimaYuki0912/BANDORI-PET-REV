"""OpenAI Realtime voice for pre-generated ambient stories."""

from __future__ import annotations

import base64
from collections import deque
from contextlib import ExitStack, suppress
import hashlib
import io
import json
import os
from pathlib import Path
import re
import tempfile
import time
import urllib.error
import urllib.request
import wave

from PySide6.QtCore import QEventLoop, QTimer, QUrl
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkProxyFactory, QNetworkProxyQuery, QNetworkRequest
from PySide6.QtWebSockets import QWebSocket

from process_utils import app_base_dir


_MODEL = "gpt-realtime-2.1-mini"
_VOICE = "marin"
_SAMPLE_RATE = 24000
_MAX_PCM_BYTES = 30 * _SAMPLE_RATE * 2
_TEXT_ENDPOINTS = {"https://api.openai.com/v1/responses", "https://api.openai.com/v1/chat/completions"}


def valid_japanese_line(text: str) -> bool:
    return 0 < len(text) <= 160 and bool(re.search(r"[ぁ-ゖァ-ヺ]", text))


def _request(url: str, api_key: str) -> QNetworkRequest:
    request = QNetworkRequest(QUrl(url))
    request.setRawHeader(b"Authorization", ("Bearer " + api_key).encode("ascii"))
    request.setAttribute(QNetworkRequest.Attribute.RedirectPolicyAttribute,
                         QNetworkRequest.RedirectPolicy.ManualRedirectPolicy)
    return request


def _apply_system_proxy(client, url: QUrl):
    # Use the OS proxy, including Windows PAC rules, for both HTTPS and WSS.
    proxy_url = QUrl(url)
    if proxy_url.scheme() == "wss":
        proxy_url.setScheme("https")
    proxies = QNetworkProxyFactory.systemProxyForQuery(QNetworkProxyQuery(proxy_url))
    if proxies:
        client.setProxy(proxies[0])


def post_openai_story_json(url: str, api_key: str, payload: dict, interrupted) -> dict:
    url = url.rstrip("/")
    if url not in _TEXT_ENDPOINTS:
        raise ValueError("Realtime stories require an official OpenAI text endpoint")
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=35) as resp:
            status = getattr(resp, "status", 200)
            if status != 200:
                raise RuntimeError(f"OpenAI story text HTTP {status}")
            raw = resp.read().decode("utf-8")
            res_data = json.loads(raw)
            if not isinstance(res_data, dict):
                raise ValueError("Invalid story response")
            return res_data
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"OpenAI story text HTTP {exc.code}: {exc.reason}") from exc
    except Exception as exc:
        raise RuntimeError(f"OpenAI story text connection failed: {exc}") from exc


class RealtimeStorySpeech:
    """Read one Japanese line at a time over a single story-scoped session."""

    def __init__(self, api_key: str, interrupted):
        self._request = _request(f"wss://api.openai.com/v1/realtime?model={_MODEL}", api_key)
        self._interrupted = interrupted
        self._socket = QWebSocket()
        self._socket.setMaxAllowedIncomingMessageSize(256 * 1024)
        _apply_system_proxy(self._socket, self._request.url())
        self._events: deque[str] = deque()
        self._loop = QEventLoop()
        self._timer = QTimer()
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._loop.quit)
        self._socket.textMessageReceived.connect(self._on_text)
        self._socket.disconnected.connect(self._on_close)
        self._socket.errorOccurred.connect(self._on_close)
        self._closed = False

    def _on_text(self, text: str):
        self._events.append(text)
        self._loop.quit()

    def _on_close(self, *_args):
        self._closed = True
        self._loop.quit()

    def __enter__(self):
        self._socket.open(self._request)
        try:
            deadline = time.monotonic() + 12
            while self._next_event(deadline)["type"] != "session.created":
                pass
            return self
        except Exception:
            self._socket.abort()
            raise

    def __exit__(self, *_exc):
        self._socket.abort()

    def _next_event(self, deadline: float) -> dict:
        while True:
            remaining_ms = int((deadline - time.monotonic()) * 1000)
            if self._interrupted() or remaining_ms <= 0:
                raise TimeoutError("Realtime story audio interrupted or timed out")
            if self._events:
                event = json.loads(self._events.popleft())
                if not isinstance(event, dict) or not isinstance(event.get("type"), str):
                    raise ValueError("Invalid Realtime event")
                if event["type"] == "error":
                    raise RuntimeError("Realtime API rejected the speech request")
                return event
            if self._closed:
                raise ConnectionError("Realtime connection closed")
            self._timer.start(min(remaining_ms, 100))
            self._loop.exec()
            self._timer.stop()

    def synthesize(self, text: str) -> bytes:
        if not valid_japanese_line(text) or self._interrupted():
            raise ValueError("Missing or invalid Japanese story line")
        request = {
            "type": "response.create",
            "response": {
                "conversation": "none",
                "instructions": (
                    "Read the supplied Japanese line verbatim as casual, natural Japanese dialogue. "
                    "Speak only that line. Preserve its wording, names, meaning, and language. "
                    "Do not add any introduction, answer, translation, or commentary."
                ),
                "input": [{"type": "message", "role": "user", "content": [{"type": "input_text", "text": text}]}],
                "output_modalities": ["audio"],
                "audio": {"output": {"voice": _VOICE, "format": {"type": "audio/pcm", "rate": _SAMPLE_RATE}}},
                "tools": [],
                "max_output_tokens": 768,
            },
        }
        if self._socket.sendTextMessage(json.dumps(request, ensure_ascii=False)) <= 0:
            raise ConnectionError("Could not send the Realtime speech request")
        deadline = time.monotonic() + 35
        pcm = bytearray()
        while True:
            event = self._next_event(deadline)
            if event["type"] == "response.output_audio.delta":
                pcm.extend(base64.b64decode(event["delta"], validate=True))
                if len(pcm) > _MAX_PCM_BYTES:
                    raise ValueError("Realtime story line exceeds the audio limit")
            if event["type"] == "response.done":
                if event["response"].get("status") != "completed" or not pcm or len(pcm) % 2:
                    raise ValueError("Incomplete Realtime speech")
                break
        output = io.BytesIO()
        with wave.open(output, "wb") as wav:
            wav.setparams((1, 2, _SAMPLE_RATE, 0, "NONE", "not compressed"))
            wav.writeframes(pcm)
        return output.getvalue()


def _cached_wave(path: Path) -> bytes | None:
    try:
        with path.open("rb") as stream:
            audio = stream.read(_MAX_PCM_BYTES + 1024)
        with wave.open(io.BytesIO(audio), "rb") as wav:
            frames = wav.getnframes()
            if (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) == (1, 2, _SAMPLE_RATE):
                if 0 < frames * 2 <= _MAX_PCM_BYTES and len(wav.readframes(frames)) == frames * 2:
                    return audio
    except (OSError, EOFError, wave.Error):
        pass
    return None


def _cache_wave(path: Path, audio: bytes):
    temporary = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".wav", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(audio)
        os.replace(temporary, path)
        temporary = None
    except OSError:
        print("[ambient story] Realtime audio cache write failed")
    finally:
        if temporary is not None:
            with suppress(OSError):
                temporary.unlink()


def prepare_realtime_story_audio(lines: list[str], character: str, api_key: str, progress, interrupted) -> list[bytes]:
    """Return a complete set of audio segments or raise without publishing a story."""
    if not 2 <= len(lines) <= 4 or not all(valid_japanese_line(line) for line in lines):
        raise ValueError("Invalid Japanese story segments")
    result = []
    speech = None
    with ExitStack() as connection:
        for index, line in enumerate(lines, 1):
            if interrupted():
                raise InterruptedError("Story generation cancelled")
            progress(index, len(lines))
            cache_key = json.dumps((character, _MODEL, _VOICE, _SAMPLE_RATE, line), ensure_ascii=False)
            digest = hashlib.sha256(cache_key.encode("utf-8")).hexdigest()
            path = app_base_dir() / "tts_cache" / "realtime_story" / f"{digest}.wav"
            audio = _cached_wave(path)
            if audio is None:
                if speech is None:
                    speech = connection.enter_context(RealtimeStorySpeech(api_key, interrupted))
                audio = speech.synthesize(line)
                _cache_wave(path, audio)
            result.append(audio)
    return result

