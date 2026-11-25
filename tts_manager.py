import hashlib
import io
import json
import os
import pathlib
import queue
import re
import struct
import tempfile
import threading
import time
import urllib.error
from contextlib import contextmanager
from urllib.parse import urlsplit
import urllib.request

try:
    import msvcrt
except ImportError:
    msvcrt = None

try:
    import fcntl
except ImportError:
    fcntl = None

import numpy as np
import requests
import sounddevice as sd
import soundfile as sf

from PySide6.QtCore import QObject, QThread, QTimer, Signal

from daily_chat import daily_chat_entries, complete_daily_chat_entries
from repeated_click import offline_voice_path, repeated_click_entries
from process_utils import app_base_dir

# ---------------------------------------------------------------------------
# Module-level caches — shared across all TTSRequestWorker instances
# ---------------------------------------------------------------------------

# dialog.json: cache with mtime-based invalidation
_dialog_json_cache: dict | None = None
_dialog_json_mtime: float = 0.0

# Reference audio path per character (content of audio_reference/ rarely changes)
_audio_path_cache: dict[str, str] = {}

# Resolved GPT-SoVITS model/reference paths per (ref_char, root, custom_json)
_model_paths_cache: dict[tuple[str, str, str], dict[str, str]] = {}

# LoRA list from backend — refresh every 60 s; use sentinel None = "never fetched yet"
_lora_list_cache: dict | None = None     # {} means "server has no loras"
_lora_list_cache_time: float = 0.0
_LORA_LIST_TTL = 60.0

# Track which LoRA is currently loaded on the server so we skip pointless unloads
_current_loaded_lora: str | None = None

# Track the currently loaded GPT-SoVITS v2 weights on the remote API.
_current_gpt_sovits_weights: tuple[str, str] | None = None

# Serialise set_gpt_weights + set_sovits_weights + POST /tts so concurrent
# workers (prewarm, chat, double-click) never race on weight switching.
_tts_lock = threading.Lock()
_tts_http_sessions: dict[bool, requests.Session] = {}
_interactive_tts_count = 0
_interactive_tts_lock = threading.Lock()

_GPT_SOVITS_REMOTE_ROOT = "/home/kirby/minecraft/bandori-tts"

_GPT_SOVITS_GPT_FILES = {
    "ako": "ako-e15.ckpt",
    "anon": "anon-e15.ckpt",
    "arisa": "arisa-e15.ckpt",
    "aya": "aya-e15.ckpt",
    "chisato": "chisato-e15.ckpt",
    "chu2": "chuchu-e15.ckpt",
    "eve": "eve-e15.ckpt",
    "hagumi": "hagumi-e15.ckpt",
    "himari": "himari-e15.ckpt",
    "hina": "hina-e15.ckpt",
    "kanon": "kanon-e15.ckpt",
    "kaoru": "kaoru-e15.ckpt",
    "kasumi": "kasumi-e5.ckpt",
    "kokoro": "kokoro-e15.ckpt",
    "lisa": "lisa-e15.ckpt",
    "lock": "lock-e15.ckpt",
    "mashiro": "mashiro-e15.ckpt",
    "masuki": "masking-e15.ckpt",
    "maya": "maya-e15.ckpt",
    "misaki": "misaki-e15.ckpt",
    "moca": "moka-e15.ckpt",
    "nanami": "nanami-e15.ckpt",
    "pareo": "pareo-e15.ckpt",
    "ran": "ran-chitchai-e10.ckpt",
    "rana": "rana-e15.ckpt",
    "rei": "layer-e15.ckpt",
    "rimi": "rimi-e10.ckpt",
    "rinko": "rinko-e5.ckpt",
    "rui": "rui-e15.ckpt",
    "saaya": "saaya-e15.ckpt",
    "sayo": "sayo-e15.ckpt",
    "soyo": "soyo-e15.ckpt",
    "tae": "tae-e15.ckpt",
    "taki": "taki-e15.ckpt",
    "tomoe": "tomoe-e15.ckpt",
    "tomorin": "tomori-e15.ckpt",
    "touko": "toko-e15.ckpt",
    "tsugumi": "tsugumi-e15.ckpt",
    "tsukushi": "tsukushi-e15.ckpt",
    "yukina": "yukina-e15.ckpt",
}

_GPT_SOVITS_SOVITS_FILES = {
    "ako": "ako_e15_s8745.pth",
    "anon": "anon_e15_s2085.pth",
    "arisa": "arisa_e15_s10815.pth",
    "aya": "aya_e15_s9345.pth",
    "chisato": "chisato_e15_s9240.pth",
    "chu2": "chuchu_e15_s4230.pth",
    "eve": "eve_e15_s8070.pth",
    "hagumi": "hagumi_e15_s7740.pth",
    "himari": "himari_e15_s9255.pth",
    "hina": "hina_e15_s9060.pth",
    "kanon": "kanon_e15_s7755.pth",
    "kaoru": "kaoru_e15_s6675.pth",
    "kasumi": "kasumi_e15_s11190.pth",
    "kokoro": "kokoro_e15_s6915.pth",
    "lisa": "lisa_e15_s10200.pth",
    "lock": "lock_e15_s4590.pth",
    "mashiro": "mashiro_e15_s5085.pth",
    "masuki": "masking_e15_s4095.pth",
    "maya": "maya_e15_s8280.pth",
    "misaki": "misaki_e15_s10245.pth",
    "moca": "moka_e15_s8460.pth",
    "nanami": "nanami_e15_s4650.pth",
    "pareo": "pareo_e15_s3705.pth",
    "ran": "ran-chitchai_e15_s8310.pth",
    "rana": "rana_e15_s690.pth",
    "rei": "layer_e15_s3960.pth",
    "rimi": "rimi_e15_s7545.pth",
    "rinko": "rinko_e15_s7215.pth",
    "rui": "rui_e15_s3495.pth",
    "saaya": "saaya_e15_s7860.pth",
    "sayo": "sayo_e15_s8430.pth",
    "soyo": "soyo_e15_s1545.pth",
    "tae": "tae_e15_s6855.pth",
    "taki": "taki_e15_s1710.pth",
    "tomoe": "tomoe_e15_s8130.pth",
    "tomorin": "tomori_e15_s1470.pth",
    "touko": "toko_e15_s5400.pth",
    "tsugumi": "tsugumi_e15_s8625.pth",
    "tsukushi": "tsukushi_e15_s4875.pth",
    "yukina": "yukina_e15_s7140.pth",
}


# GPT-SoVITS v2 exposes sampling and playback-speed controls at inference
# time. Keep the application's default slightly slower than the server's 1.0
# default, then apply only the small character differences requested for the
# desktop-pet voices. Users can still override any value via
# ``tts_character_profiles`` in ConfigManager-managed configuration.
_DEFAULT_TTS_VOICE_PROFILE = {
    "speed_factor": 0.92,
    "temperature": 0.60,
    "top_k": 8,
    "top_p": 0.88,
    "repetition_penalty": 1.35,
}

_BUILTIN_TTS_CHARACTER_PROFILES = {
    "rei": {"speed_factor": 0.89, "temperature": 0.58, "top_p": 0.85},
    "lisa": {"speed_factor": 0.90, "temperature": 0.62, "top_k": 9},
    "chu2": {"speed_factor": 0.96, "temperature": 0.76, "top_k": 12, "top_p": 0.92},
}


def _bounded_profile_float(value, default: float, minimum: float, maximum: float) -> float:
    try:
        return max(minimum, min(maximum, float(value)))
    except (TypeError, ValueError):
        return default


def _bounded_profile_int(value, default: int, minimum: int, maximum: int) -> int:
    try:
        return max(minimum, min(maximum, int(value)))
    except (TypeError, ValueError):
        return default


def effective_tts_voice_profile(character: str, config: dict) -> dict[str, float | int]:
    """Return the validated inference profile for a pet character.

    The global speed and temperature settings are the normal user controls.
    Character profiles provide gentle defaults for voices that need a distinct
    pace or livelier sampling, and an optional saved profile wins last.
    """
    config = config if isinstance(config, dict) else {}
    profile = dict(_DEFAULT_TTS_VOICE_PROFILE)
    global_speed_factor = _bounded_profile_float(
        config.get("tts_speed_factor", profile["speed_factor"]),
        profile["speed_factor"],
        0.50,
        1.50,
    )
    profile["speed_factor"] = global_speed_factor
    profile["temperature"] = config.get("tts_temperature", profile["temperature"])

    character_key = str(character or "").strip().lower()
    builtin_profile = _BUILTIN_TTS_CHARACTER_PROFILES.get(character_key, {})
    builtin_speed_factor = builtin_profile.get("speed_factor")
    if builtin_speed_factor is not None:
        # Character profiles express a small pace difference from the default.
        # Preserve that difference when the user changes the global slider.
        profile["speed_factor"] = global_speed_factor + (
            float(builtin_speed_factor) - _DEFAULT_TTS_VOICE_PROFILE["speed_factor"]
        )
    profile.update({key: value for key, value in builtin_profile.items() if key != "speed_factor"})

    saved_profiles = config.get("tts_character_profiles", {})
    if isinstance(saved_profiles, dict):
        saved_profile = saved_profiles.get(character_key, {})
        if isinstance(saved_profile, dict):
            profile.update(saved_profile)

    return {
        "speed_factor": _bounded_profile_float(profile.get("speed_factor"), 0.92, 0.50, 1.50),
        "temperature": _bounded_profile_float(profile.get("temperature"), 0.60, 0.01, 2.00),
        "top_k": _bounded_profile_int(profile.get("top_k"), 8, 1, 100),
        "top_p": _bounded_profile_float(profile.get("top_p"), 0.88, 0.05, 1.00),
        "repetition_penalty": _bounded_profile_float(profile.get("repetition_penalty"), 1.35, 0.10, 3.00),
    }


def _remote_tts_root(config: dict) -> str:
    value = str(
        config.get("tts_gpt_sovits_root", "")
        or config.get("tts_gpt_sovits_remote_root", "")
        or ""
    ).strip()
    return (value or _GPT_SOVITS_REMOTE_ROOT).rstrip("/")


def _is_local_tts_url(url: str) -> bool:
    host = urlsplit(str(url or "").strip()).hostname
    return host in {"127.0.0.1", "localhost", "::1"}


def _tts_url_digest(url: str) -> str:
    normalized = str(url or "http://127.0.0.1:9880/").strip().rstrip("/").lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def _tts_ipc_paths(url: str) -> tuple[pathlib.Path, pathlib.Path, pathlib.Path]:
    digest = _tts_url_digest(url)
    base = pathlib.Path(tempfile.gettempdir())
    return (
        base / f"bandoripet_tts_{digest}.lock",
        base / f"bandoripet_tts_{digest}.json",
        base / f"bandoripet_tts_{digest}.busy",
    )


def _get_tts_session(url: str) -> requests.Session:
    """Return a keep-alive HTTP session; callers must hold ``_tts_lock``."""
    local = _is_local_tts_url(url)
    session = _tts_http_sessions.get(local)
    if session is None:
        session = requests.Session()
        if local:
            session.trust_env = False
        _tts_http_sessions[local] = session
    return session


@contextmanager
def _cross_process_tts_lock(url: str, is_interrupted=None, timeout: float = 300.0):
    lock_path, _, _ = _tts_ipc_paths(url)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o666)
    acquired = False
    try:
        if os.fstat(fd).st_size == 0:
            os.write(fd, b"\0")
        deadline = time.monotonic() + timeout
        while True:
            if is_interrupted is not None and is_interrupted():
                raise InterruptedError("TTS request interrupted while waiting for lock")
            try:
                if msvcrt is not None:
                    os.lseek(fd, 0, os.SEEK_SET)
                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                elif fcntl is not None:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise TimeoutError("Timed out waiting for TTS process lock")
                time.sleep(0.025)
        yield
    finally:
        if acquired:
            try:
                if msvcrt is not None:
                    os.lseek(fd, 0, os.SEEK_SET)
                    msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
                elif fcntl is not None:
                    fcntl.flock(fd, fcntl.LOCK_UN)
            except OSError:
                pass
        os.close(fd)


def _norm_weight_path(path: str) -> str:
    return str(path or "").strip().replace("\\", "/")


def _read_tts_state_weights(url: str) -> tuple[str, str, float]:
    _, state_path, _ = _tts_ipc_paths(url)
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return (
                _norm_weight_path(data.get("gpt", "")),
                _norm_weight_path(data.get("sovits", "")),
                float(data.get("updated_at", 0.0) or 0.0),
            )
    except (OSError, ValueError, TypeError):
        pass
    return "", "", 0.0


def _write_tts_state_weights(url: str, gpt: str, sovits: str):
    _, state_path, _ = _tts_ipc_paths(url)
    payload = {
        "gpt": _norm_weight_path(gpt),
        "sovits": _norm_weight_path(sovits),
        "updated_at": time.time(),
    }
    tmp_path = None
    try:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(suffix=".json", prefix=".tmp_tts_", dir=str(state_path.parent))
        try:
            os.write(fd, json.dumps(payload, ensure_ascii=False).encode("utf-8"))
        finally:
            os.close(fd)
        os.replace(tmp_path, str(state_path))
        tmp_path = None
    except OSError:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


def _read_local_runtime_weights(config: dict, url: str) -> tuple[str, str, float] | None:
    if not _is_local_tts_url(url):
        return None
    runtime = str((config or {}).get("tts_gpt_sovits_runtime", "") or "").strip()
    if not runtime:
        return None
    yaml_path = pathlib.Path(runtime) / "GPT_SoVITS" / "configs" / "bandoripet_local.yaml"
    try:
        stat = yaml_path.stat()
        text = yaml_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    in_custom = False
    gpt = ""
    sovits = ""
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if not raw_line[0].isspace():
            in_custom = stripped.startswith("custom:")
            continue
        if in_custom:
            if stripped.startswith("t2s_weights_path:"):
                gpt = stripped.split(":", 1)[1].strip().strip("'\"")
            elif stripped.startswith("vits_weights_path:"):
                sovits = stripped.split(":", 1)[1].strip().strip("'\"")
    if gpt and sovits:
        return _norm_weight_path(gpt), _norm_weight_path(sovits), stat.st_mtime
    return None


def _configured_tts_url(config: dict | None) -> str:
    url = str((config or {}).get("tts_api_url", "") or "").strip() or "http://127.0.0.1:9880/"
    return url if url.endswith("/") else url + "/"


@contextmanager
def _interactive_tts_scope(url: str):
    global _interactive_tts_count
    _, _, busy_path = _tts_ipc_paths(url)
    with _interactive_tts_lock:
        _interactive_tts_count += 1
        try:
            busy_path.write_text(
                json.dumps({"pid": os.getpid(), "until": time.time() + 45.0}),
                encoding="utf-8",
            )
        except OSError:
            pass
    try:
        yield
    finally:
        with _interactive_tts_lock:
            _interactive_tts_count = max(0, _interactive_tts_count - 1)
            if _interactive_tts_count == 0:
                try:
                    busy_path.unlink(missing_ok=True)
                except OSError:
                    pass


def is_interactive_tts_busy(config: dict | None = None) -> bool:
    """Return True while an interactive TTS request is active in this or another process."""
    with _interactive_tts_lock:
        if _interactive_tts_count > 0:
            return True
    url = _configured_tts_url(config)
    _, _, busy_path = _tts_ipc_paths(url)
    try:
        data = json.loads(busy_path.read_text(encoding="utf-8"))
        return float(data.get("until", 0.0) or 0.0) > time.time()
    except (OSError, ValueError, TypeError):
        return False


def _gpt_sovits_model_paths(character: str, config: dict) -> dict[str, str]:
    ref_char = (character or "").strip().lower()
    gpt_file = _GPT_SOVITS_GPT_FILES.get(ref_char)
    sovits_file = _GPT_SOVITS_SOVITS_FILES.get(ref_char)
    if not gpt_file or not sovits_file:
        raise ValueError(f"GPT-SoVITS weights not configured for character: {character}")

    custom_weights = config.get("tts_custom_weights", {}) if isinstance(config, dict) else {}
    if isinstance(custom_weights, dict) and ref_char in custom_weights:
        entry = custom_weights[ref_char]
        if isinstance(entry, dict) and entry.get("gpt") and entry.get("sovits"):
            ref_path = entry.get("reference")
            if not ref_path:
                cached_ref_wav = app_base_dir() / "tts_cache" / "audio_reference_wav" / f"{ref_char}.wav"
                root_wav = pathlib.Path(_remote_tts_root(config)) / "audio_reference_wav" / f"{ref_char}.wav"
                local_ref_wav = app_base_dir() / "audio_reference" / f"{ref_char}.wav"
                local_ref_mp3 = app_base_dir() / "audio_reference" / f"{ref_char}.mp3"
                ref_path = str(
                    next(
                        (p for p in (cached_ref_wav, root_wav, local_ref_wav, local_ref_mp3) if p.exists()),
                        local_ref_mp3,
                    )
                )
            return {
                "gpt": str(entry["gpt"]).replace("\\", "/"),
                "sovits": str(entry["sovits"]).replace("\\", "/"),
                "reference": str(ref_path).replace("\\", "/"),
            }

    root = _remote_tts_root(config)
    if root == _GPT_SOVITS_REMOTE_ROOT:
        return {
            "gpt": f"{root}/GPT-SoVITS/GPT_weights_v2/{gpt_file}",
            "sovits": f"{root}/GPT-SoVITS/SoVITS_weights_v2/{sovits_file}",
            "reference": f"{root}/audio_reference_wav/{ref_char}.wav",
        }

    cache_key = (ref_char, root, "")
    cached = _model_paths_cache.get(cache_key)
    if cached is not None and all(pathlib.Path(p).exists() for p in cached.values()):
        return dict(cached)

    root_path = pathlib.Path(root)

    # 1. GPT weights resolution
    gpt_candidates = [
        root_path / "weights" / "ckpt_files" / gpt_file,
        root_path / "GPT_weights_v2" / gpt_file,
        root_path / "GPT-SoVITS" / "GPT_weights_v2" / gpt_file,
        root_path / "GPT_weights" / gpt_file,
        root_path / gpt_file,
    ]
    resolved_gpt = next((p for p in gpt_candidates if p.exists()), gpt_candidates[0])

    # 2. SoVITS weights resolution
    sovits_candidates = [
        root_path / "weights" / "pth_files" / sovits_file,
        root_path / "SoVITS_weights_v2" / sovits_file,
        root_path / "GPT-SoVITS" / "SoVITS_weights_v2" / sovits_file,
        root_path / "SoVITS_weights" / sovits_file,
        root_path / sovits_file,
    ]
    resolved_sovits = next((p for p in sovits_candidates if p.exists()), sovits_candidates[0])

    # 3. Reference audio resolution (prefer pre-decoded WAV over MP3)
    ref_candidates = [
        app_base_dir() / "tts_cache" / "audio_reference_wav" / f"{ref_char}.wav",
        root_path / "audio_reference_wav" / f"{ref_char}.wav",
        app_base_dir() / "audio_reference" / f"{ref_char}.wav",
        app_base_dir() / "audio_reference" / f"{ref_char}.mp3",
        root_path / "audio_reference" / f"{ref_char}.wav",
        root_path / "audio_reference" / f"{ref_char}.mp3",
    ]
    resolved_ref = next((p for p in ref_candidates if p.exists()), ref_candidates[0])

    result = {
        "gpt": str(resolved_gpt).replace("\\", "/"),
        "sovits": str(resolved_sovits).replace("\\", "/"),
        "reference": str(resolved_ref).replace("\\", "/"),
    }
    if all(pathlib.Path(p).exists() for p in result.values()):
        _model_paths_cache[cache_key] = dict(result)
    return result


def _tts_api_language_code(language: str) -> str:
    values = {
        "Chinese": "zh",
        "zh": "zh",
        "中文": "zh",
        "Japanese": "ja",
        "ja": "ja",
        "日文": "ja",
        "English": "en",
        "en": "en",
        "英文": "en",
    }
    return values.get(language, str(language or "zh").strip() or "zh")


def _select_gpt_sovits_split_params(text: str, *, streaming: bool = False) -> tuple[str, int]:
    """Choose GPT-SoVITS split method and batch size for a single sentence/chunk.

    Short/medium sentences (<= 60 chars) are already segmented by the caller, so
    using ``cut0`` avoids GPT-SoVITS re-splitting on every comma into multiple
    serial T2S passes. Longer passages use ``cut2`` with batching when
    non-streaming, or client-side clause chunking when streaming.
    """
    if len(str(text or "").strip()) <= 60:
        return "cut0", 1
    if streaming:
        return "cut2", 1
    return "cut2", 4


def _pcm_to_wav_bytes(
    pcm: bytes,
    sample_rate: int = 32000,
    channels: int = 1,
    sample_width: int = 2,
) -> bytes:
    """Wrap raw PCM frames in a standard 44-byte RIFF/WAVE header."""
    byte_rate = sample_rate * channels * sample_width
    block_align = channels * sample_width
    data_size = len(pcm)
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + data_size,
        b"WAVE",
        b"fmt ",
        16,
        1,
        channels,
        sample_rate,
        byte_rate,
        block_align,
        sample_width * 8,
        b"data",
        data_size,
    )
    return header + pcm


def _parse_wav_stream_header(buffer: bytearray) -> tuple[int, int, int, int] | None:
    """Parse a streaming WAV header; return ``(data_offset, sr, channels, width)``."""
    if len(buffer) < 44 or buffer[:4] != b"RIFF" or buffer[8:12] != b"WAVE":
        return None
    pos = 12
    channels = 1
    sample_rate = 32000
    sample_width = 2
    found_fmt = False
    while pos + 8 <= len(buffer):
        chunk_id = bytes(buffer[pos:pos + 4])
        chunk_size = struct.unpack_from("<I", buffer, pos + 4)[0]
        pos += 8
        if chunk_id == b"fmt " and pos + 16 <= len(buffer):
            channels = max(1, struct.unpack_from("<H", buffer, pos + 2)[0])
            sample_rate = max(8000, struct.unpack_from("<I", buffer, pos + 4)[0])
            bits_per_sample = max(8, struct.unpack_from("<H", buffer, pos + 14)[0])
            sample_width = max(1, bits_per_sample // 8)
            found_fmt = True
        elif chunk_id == b"data":
            if found_fmt:
                return pos, sample_rate, channels, sample_width
            return None
        pos += chunk_size + (chunk_size & 1)
    return None


def _iter_wav_stream_chunks(
    response,
    is_interrupted=None,
    min_chunk_bytes: int = 4096,
):
    """Yield complete playable WAV chunks from a GPT-SoVITS ``streaming_mode=True`` stream."""
    buf = bytearray()
    header_parsed = False
    sample_rate = 32000
    channels = 1
    sample_width = 2
    frame_bytes = 2
    for chunk in response.iter_content(chunk_size=None):
        if is_interrupted is not None and is_interrupted():
            close = getattr(response, "close", None)
            if callable(close):
                close()
            return
        if not chunk:
            continue
        buf.extend(chunk)
        if not header_parsed:
            if len(buf) >= 4 and buf[:4] != b"RIFF":
                raise ValueError("Unexpected non-WAV stream from TTS server")
            parsed = _parse_wav_stream_header(buf)
            if parsed is None:
                continue
            data_offset, sample_rate, channels, sample_width = parsed
            frame_bytes = max(1, channels * sample_width)
            del buf[:data_offset]
            header_parsed = True
        usable = (len(buf) // frame_bytes) * frame_bytes
        if usable >= min_chunk_bytes:
            pcm = bytes(buf[:usable])
            del buf[:usable]
            yield _pcm_to_wav_bytes(pcm, sample_rate, channels, sample_width)

    if header_parsed:
        usable = (len(buf) // frame_bytes) * frame_bytes
        if usable > 0:
            yield _pcm_to_wav_bytes(bytes(buf[:usable]), sample_rate, channels, sample_width)
    elif len(buf) > 44:
        yield bytes(buf)


def _gpt_sovits_payload(
    *,
    text: str,
    text_language: str,
    reference_path: str,
    prompt_text: str,
    temperature: float,
    speed_factor: float,
    top_k: int,
    top_p: float,
    repetition_penalty: float,
    text_split_method: str = "cut5",
    batch_size: int = 1,
    streaming_mode: bool = False,
) -> dict:
    safe_text = str(text or "").replace("〜", "ー").replace("～", "ー")
    safe_prompt = str(prompt_text or "").replace("〜", "ー").replace("～", "ー")
    return {
        "text": safe_text,
        "text_lang": _tts_api_language_code(text_language),
        "ref_audio_path": reference_path,
        "prompt_text": safe_prompt,
        "prompt_lang": "ja",
        "top_k": top_k,
        "top_p": top_p,
        "temperature": temperature,
        "speed_factor": speed_factor,
        "repetition_penalty": repetition_penalty,
        "text_split_method": text_split_method,
        "batch_size": max(1, int(batch_size)),
        "media_type": "wav",
        "streaming_mode": bool(streaming_mode),
    }


def _load_dialog_json() -> dict:
    """Return cached dialog.json, reloading only when the file changes on disk."""
    global _dialog_json_cache, _dialog_json_mtime
    path = app_base_dir() / "audio_reference" / "dialog.json"
    try:
        mtime = path.stat().st_mtime
        if _dialog_json_cache is not None and mtime == _dialog_json_mtime:
            return _dialog_json_cache
        _dialog_json_cache = json.loads(path.read_text(encoding="utf-8"))
        _dialog_json_mtime = mtime
        return _dialog_json_cache
    except Exception:
        return _dialog_json_cache or {}


_ACTION_TAG_RE = re.compile(r"\[(?:DONE|[A-Za-z0-9_.\-]+)\]")
_DIALOG_GROUPS_KEY = "__groups"


CHARACTER_TRILINGUAL_NAMES = {
    "户山香澄":   ("戸山香澄 (Toyama Kasumi)",    "Kasumi Toyama"),
    "花园多惠":    ("花園たえ (Hanazono Tae)",      "Tae Hanazono"),
    "牛込里美":    ("牛込りみ (Ushigome Rimi)",      "Rimi Ushigome"),
    "山吹沙绫":    ("山吹沙綾 (Yamabuki Saaya)",    "Saaya Yamabuki"),
    "市谷有咲":    ("市ヶ谷有咲 (Ichigaya Arisa)",   "Arisa Ichigaya"),
    "美竹兰":     ("美竹蘭 (Mitake Ran)",         "Ran Mitake"),
    "青叶摩卡":    ("青葉モカ (Aoba Moca)",        "Moca Aoba"),
    "上原绯玛丽":   ("上原ひまり (Uehara Himari)",    "Himari Uehara"),
    "宇田川巴":    ("宇田川巴 (Udagawa Tomoe)",     "Tomoe Udagawa"),
    "羽泽鸫":     ("羽沢つぐみ (Hazawa Tsugumi)",    "Tsugumi Hazawa"),
    "丸山彩":     ("丸山彩 (Maruyama Aya)",       "Aya Maruyama"),
    "冰川日菜":    ("氷川日菜 (Hikawa Hina)",       "Hina Hikawa"),
    "白鹭千圣":    ("白鷺千聖 (Shirasagi Chisato)",  "Chisato Shirasagi"),
    "大和麻弥":    ("大和麻弥 (Yamato Maya)",       "Maya Yamato"),
    "若宫伊芙":    ("若宮イヴ (Wakamiya Eve)",      "Eve Wakamiya"),
    "弦卷心":     ("弦巻こころ (Tsurumaki Kokoro)",  "Kokoro Tsurumaki"),
    "濑田薰":     ("瀬田薫 (Seta Kaoru)",         "Kaoru Seta"),
    "北泽育美":    ("北沢はぐみ (Kitazawa Hagumi)",  "Hagumi Kitazawa"),
    "松原花音":    ("松原花音 (Matsubara Kanon)",    "Kanon Matsubara"),
    "奥泽美咲":    ("奥沢美咲 (Okusawa Misaki)",     "Misaki Okusawa (Michelle)"),
    "凑友希那":    ("湊友希那 (Minato Yukina)",      "Yukina Minato"),
    "冰川纱夜":    ("氷川紗夜 (Hikawa Sayo)",       "Sayo Hikawa"),
    "今井莉莎":    ("今井リサ (Imai Lisa)",         "Lisa Imai"),
    "宇田川亚子":   ("宇田川あこ (Udagawa Ako)",     "Ako Udagawa"),
    "白金燐子":    ("白金燐子 (Shirokane Rinko)",    "Rinko Shirokane"),
    "鳰原令王那":   ("鳰原令王那 / レイヤ (Nihara Reona / PAREO)", "Reona Nihara (PAREO)"),
    "佐藤益木":    ("佐藤ますき (Satou Masuki / MASKING)", "Masuki Satou (MASKING)"),
    "和奏瑞依":    ("和奏レイ (Wakana Rei / LAYER)", "Rei Wakana (LAYER)"),
    "朝日六花":    ("朝日六花 (Asahi Rokka / LOCK)",  "Rokka Asahi (LOCK)"),
    "珠手知由":    ("珠手ちゆ (Shude Chiyu / CHU²)",  "Chiyu Shude (CHU²)"),
    "仓田真白":    ("倉田ましろ (Kurata Mashiro)",     "Mashiro Kurata"),
    "桐谷透子":    ("桐ヶ谷透子 (Kirigaya Touko)",    "Touko Kirigaya"),
    "广町七深":    ("広町七深 (Hiromachi Nanami)",     "Nanami Hiromachi"),
    "二叶筑紫":    ("二葉つくし (Futaba Tsukushi)",     "Tsukushi Futaba"),
    "八潮瑠唯":    ("八潮瑠唯 (Yashio Rui)",         "Rui Yashio"),
    "高松灯":     ("高松燈 (Takamatsu Tomori)",     "Tomori Takamatsu"),
    "千早爱音":    ("千早愛音 (Chihaya Anon)",      "Anon Chihaya"),
    "要乐奈":     ("要楽奈 (Kaname Rāna)",        "Rāna Kaname"),
    "长崎素世":    ("長崎そよ (Nagasaki Soyo)",      "Soyo Nagasaki"),
    "椎名立希":    ("椎名立希 (Shiina Taki)",        "Taki Shiina"),
    "丰川祥子":    ("豊川祥子 (Togawa Sakiko)",     "Sakiko Togawa"),
    "若叶睦":     ("若葉睦 (Wakaba Mutsumi)",      "Mutsumi Wakaba"),
    "三角初华":    ("三角初華 (Misumi Uika)",       "Uika Misumi"),
    "八幡海玲":    ("八幡海鈴 (Yahata Umiri)",       "Umiri Yahata"),
    "祐天寺若麦":   ("祐天寺にゃむ (Yūtenji Nyamu)",  "Nyamu Yūtenji"),
    "纯田真奈":    ("純田まな (Sumida Mana)",       "Mana Sumida"),
    "户山明日香":   ("戸山明日香 (Toyama Asuka)",    "Asuka Toyama"),
    "汐見蛍":     ("汐見螢 (Shiomi Hotaru)",       "Hotaru Shiomi"),
}


# Do not include common Chinese words here.  ``要`` is 要乐奈's surname but is
# also a high-frequency verb, so recognizing it alone polluted unrelated TTS
# translation prompts with the wrong character reference.
_ONE_CHAR_SURNAMES = frozenset({"凑"})
_SHORT_SURNAME_GIVEN_NAME_ALIASES = {
    "凑友希那": "友希那",
    "要乐奈": "乐奈",
}
_TTS_TRANSLATION_FORMAT_VERSION = "speaker-name-guidance-v2"

# BanG Dream! bands, stage names, venues, and common live terms that must be
# rendered in Japanese kana/katakana when synthesizing Japanese speech so that
# GPT-SoVITS does not pronounce them with English phonetics.
# Each entry: (canonical_label, jp_speech_reading, aliases_tuple, word_boundary_only)
_BANDORI_TERM_SPEECH_ENTRIES: tuple[tuple[str, str, tuple[str, ...], bool], ...] = (
    ("Hello, Happy World!", "ハロー、ハッピーワールド！（简称 ハロハピ）", ("hello, happy world", "hello happy world", "hello,happy,world", "hello happy world!", "hhw", "哈罗哈比", "赫萝哈皮"), False),
    ("Roselia", "ロゼリア", ("roselia",), False),
    ("Poppin'Party", "ポッピンパーティ（简称 ポピパ）", ("poppin'party", "poppin’party", "poppin party", "popipa", "ppp"), False),
    ("Afterglow", "アフターグロウ", ("afterglow",), False),
    ("Pastel＊Palettes", "パステルパレット（简称 パスパレ）", ("pastel*palettes", "pastel＊palettes", "pastel palettes", "pasupare"), False),
    ("Morfonica", "モルフォニカ（简称 モニカ）", ("morfonica",), False),
    ("RAISE A SUILEN", "レイズ・ア・スイレン（简称 ラス）", ("raise a suilen",), False),
    ("RAS", "ラス（或 レイズ・ア・スイレン）", ("ras",), True),
    ("MyGO!!!!!", "マイゴ", ("mygo!!!!!", "mygo"), True),
    ("Ave Mujica", "アヴェ・ムジカ", ("ave mujica", "mujica"), False),
    ("CRYCHIC", "クライシック", ("crychic",), True),
    ("sumimi", "すみみ", ("sumimi",), True),
    ("Glitter*Green", "グリッターグリーン", ("glitter*green", "glitter green"), False),
    ("CHiSPA", "チスパ", ("chispa",), True),
    ("BanG Dream!", "バンドリ！", ("bang dream!", "bang dream", "bangdream", "邦邦"), False),
    ("LAYER", "レイヤ", ("layer",), True),
    ("LOCK", "ロック", ("lock",), True),
    ("MASKING", "マスキング", ("masking",), True),
    ("PAREO", "パレオ", ("pareo",), True),
    ("CHU²", "チュチュ", ("chu²", "chu2", "chuchu"), False),
    ("Doloris", "ドロリス", ("doloris",), True),
    ("Mortis", "モーティス", ("mortis",), True),
    ("Timoris", "ティモリス", ("timoris",), True),
    ("Amoris", "アモーリス", ("amoris",), True),
    ("Oblivionis", "オブリビオニス", ("oblivionis",), True),
    ("Michelle", "ミッシェル", ("michelle", "米歇尔"), False),
    ("CiRCLE", "サークル", ("circle",), True),
    ("RiNG", "リング", ("ring",), True),
    ("GALAXY", "ギャラクシー", ("galaxy",), True),
    ("SPACE", "スペース", ("space",), True),
    ("LIVE", "ライブ", ("live",), True),
    ("NFO", "エヌエフオー", ("nfo",), True),
)

_BANDORI_JAPANESE_RULE = (
    "\n【BanG Dream! 日语语音用语规范】"
    "译文将直接交给日语语音合成引擎朗读。凡涉及 BanG Dream! 乐队名、舞台艺名、Live House、"
    "歌曲或英文专有名词，严禁保留英文拼写，必须全部转写为日语假名/片假名读音"
    "（例如：Hello, Happy World! → ハロー、ハッピーワールド！，Roselia → ロゼリア，"
    "Poppin'Party → ポッピンパーティ，Afterglow → アフターグロウ，"
    "Pastel＊Palettes → パステルパレット，Morfonica → モルフォニカ，"
    "RAISE A SUILEN → レイズ・ア・スイレン，MyGO!!!!! → マイゴ，"
    "Ave Mujica → アヴェ・ムジカ，BanG Dream! → バンドリ！）。"
    "其他夹杂的英文词也请按日语习惯写成片假名，避免语音引擎用英语腔调朗读。"
)


def _find_referenced_bandori_terms(text: str) -> list[tuple[str, str]]:
    if not text:
        return []
    lowered = text.lower()
    matched: list[tuple[str, str]] = []
    for label, jp_reading, aliases, word_boundary in _BANDORI_TERM_SPEECH_ENTRIES:
        hit = False
        for alias in aliases:
            if word_boundary and alias.isascii():
                if re.search(rf"(?<![A-Za-z0-9_]){re.escape(alias)}(?![A-Za-z0-9_])", lowered):
                    hit = True
                    break
            elif alias in lowered:
                hit = True
                break
        if hit:
            matched.append((label, jp_reading))
    return matched

# A bare Japanese kanji can have a different dictionary reading from a
# character's name.  Keep the speech spelling here so the translation prompt
# can request unambiguous kana for the affected speaker.
_SPEAKER_NAME_SPEECH_GUIDES = {
    "aya": {
        "display_name": "丸山彩 (Aya Maruyama)",
        "ambiguous_name": "彩",
        "speech_spelling": "あや",
    },
}


def _find_referenced_characters(text: str) -> dict:
    if not text:
        return {}
    matched: dict[str, tuple[str, str]] = {}
    for cn, (jp, en_) in CHARACTER_TRILINGUAL_NAMES.items():
        if cn in text:
            matched[cn] = (jp, en_)
            continue
        given_name = _SHORT_SURNAME_GIVEN_NAME_ALIASES.get(cn)
        if given_name and given_name in text:
            matched[cn] = (jp, en_)
            continue
        for slen in (3, 2, 1):
            if slen >= len(cn):
                continue
            surname = cn[:slen]
            given = cn[slen:]
            if slen == 1 and surname not in _ONE_CHAR_SURNAMES:
                continue
            if surname in text:
                matched[cn] = (jp, en_)
                break
            if len(given) >= 2 and given in text:
                matched[cn] = (jp, en_)
                break
    return matched


def _build_translation_system_prompt(
    target_language_name: str,
    text: str = "",
    speaker_character: str = "",
) -> str:
    referenced = _find_referenced_characters(text)
    referenced_terms = _find_referenced_bandori_terms(text) if target_language_name == "日语" else []
    speaker_guide = _SPEAKER_NAME_SPEECH_GUIDES.get(
        str(speaker_character or "").strip().lower()
    )
    speaker_instruction = ""
    if speaker_guide and target_language_name == "日语":
        speaker_instruction = (
            f"\n当前说话角色是 {speaker_guide['display_name']}。为避免语音合成把"
            f"「{speaker_guide['ambiguous_name']}」误读成其他词，日语译文中她的"
            f"自称或单独名字必须写作「{speaker_guide['speech_spelling']}」，"
            f"不要单独写「{speaker_guide['ambiguous_name']}」。"
        )
    jp_bandori_rule = _BANDORI_JAPANESE_RULE if target_language_name == "日语" else ""

    appendices: list[str] = []
    if referenced:
        char_lines = "\n".join(
            f"  {cn}  |  {jp}  |  {en_}"
            for cn, (jp, en_) in referenced.items()
        )
        appendices.append(f"### BanG Dream! Character Name Reference (CN | JP | EN)\n{char_lines}")
    if referenced_terms:
        term_lines = "\n".join(
            f"  {term}  ->  {jp_reading}"
            for term, jp_reading in referenced_terms
        )
        appendices.append(f"### BanG Dream! Term Japanese Speech Reference (MUST use kana)\n{term_lines}")

    if appendices:
        appendix_block = "\n\n" + "\n\n".join(appendices)
        return (
            f"把用户给出的中文聊天台词翻译成自然{target_language_name}，只输出译文，不要解释。保留语气，不要输出动作标签。"
            f"翻译人物与作品专有名词时请参照以下对照表，按目标语言使用对应名称：\n{appendix_block}"
            f"{jp_bandori_rule}"
            f"{speaker_instruction}"
        )
    return (
        f"把用户给出的中文聊天台词翻译成自然{target_language_name}，只输出译文，不要解释。保留语气，不要输出动作标签。"
        f"{jp_bandori_rule}"
        f"{speaker_instruction}"
    )


def strip_tts_action_tags(text: str) -> str:
    cleaned = _ACTION_TAG_RE.sub("", text).strip()
    return cleaned.replace("〜", "ー").replace("～", "ー")


_TTS_SENTENCE_RE = re.compile(r".+?(?:[。！？!?；;]+|$)", re.S)
_TTS_WS_RE = re.compile(r"[ \t\r\f\v]+")
_TTS_NL_RE = re.compile(r"\n+")
_TTS_CLAUSE_RE = re.compile(r".+?(?:[，、,：:]+|$)", re.S)


def split_tts_segments(text: str, max_chars: int = 90) -> list[str]:
    """Split assistant text into small TTS-friendly segments."""
    cleaned = strip_tts_action_tags(str(text or ""))
    cleaned = _TTS_WS_RE.sub(" ", cleaned)
    cleaned = _TTS_NL_RE.sub("\n", cleaned).strip()
    if not cleaned:
        return []

    pieces: list[str] = []
    sentence_re = _TTS_SENTENCE_RE
    for paragraph in (part.strip() for part in cleaned.splitlines()):
        if not paragraph:
            continue
        for match in sentence_re.finditer(paragraph):
            sentence = match.group(0).strip()
            if sentence:
                pieces.extend(_split_tts_long_segment(sentence, max_chars=max_chars))
    return pieces


def _split_tts_long_segment(text: str, max_chars: int) -> list[str]:
    if max_chars <= 0 or len(text) <= max_chars:
        return [text]
    segments: list[str] = []
    current = ""
    for chunk in _TTS_CLAUSE_RE.findall(text):
        chunk = chunk.strip()
        if not chunk:
            continue
        if current and len(current) + len(chunk) > max_chars:
            segments.append(current)
            current = chunk
        else:
            current += chunk
        while len(current) > max_chars + 8:
            segments.append(current[:max_chars])
            current = current[max_chars:]
    if current:
        segments.append(current)
    return segments


# ---------------------------------------------------------------------------
# TTS cache helpers — deterministic cache paths so fixed lines are generated once
# ---------------------------------------------------------------------------

def tts_cache_path(text: str, character: str, config: dict) -> pathlib.Path:
    """Return the cache ``.wav`` path for a given text+character+config.

    The hash includes fields that affect synthesis output so that changing
    the voice model, language or temperature produces a distinct cache entry.

    Uses ``config["tts_reference_character"]`` if set, otherwise *character*,
    so that the cache key matches the actual voice model used for synthesis.
    """
    raw_char = str(config.get("tts_reference_character", "") or "").strip() or character
    ref_char = (raw_char or "").strip().lower()
    language = str(config.get("tts_language", "Japanese") or "Japanese")
    profile = effective_tts_voice_profile(character, config)
    remote_root = _remote_tts_root(config)
    paths = _gpt_sovits_model_paths(ref_char, config)
    # Build a deterministic key from all inputs that affect the output audio
    key_parts = [
        text,
        ref_char,
        language,
        str(profile["speed_factor"]),
        str(profile["temperature"]),
        str(profile["top_k"]),
        str(profile["top_p"]),
        str(profile["repetition_penalty"]),
        remote_root,
        paths.get("gpt", ""),
        paths.get("sovits", ""),
        _TTS_TRANSLATION_FORMAT_VERSION if _tts_should_translate(config, language) else "",
    ]
    key = "\n".join(key_parts)
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    # No mkdir here: pure cache-hit lookups (hundreds during greeting prewarm)
    # should not pay directory syscalls. The write path creates the directory
    # itself right before the atomic replace.
    cache_dir = app_base_dir() / "tts_cache" / "gpt_sovits" / ref_char
    return cache_dir / f"{digest}.wav"


def collect_greeting_tts_lines(greetings: dict, character: str = "", base_dir: pathlib.Path | None = None) -> list[str]:
    """Collect all unique non-empty text lines from a ``greetings.json`` dict.

    The order is ``startup_greeting`` → ``repeated_click`` → ``daily_chat``. If no daily-chat pool
    is configured, legacy ``click_responses[].lines`` and ``tiers[].lines``
    are used instead. Duplicates are removed while preserving
    first-occurrence order.
    """
    return [text for text, _pretranslated in collect_greeting_tts_items(greetings, character, base_dir)]


def collect_greeting_tts_items(greetings: dict, character: str = "", base_dir: pathlib.Path | None = None) -> list[tuple[str, bool]]:
    """Collect ``(text, is_pretranslated)`` items for greeting prewarm."""
    seen: set[str] = set()
    result: list[tuple[str, bool]] = []
    base_dir = base_dir if base_dir is not None else app_base_dir()

    def _add(lines, pretranslated=False):
        for line in lines:
            if isinstance(line, tuple):
                line, pretranslated = line
            text = strip_tts_action_tags(str(line).strip())
            if text and text not in seen:
                seen.add(text)
                result.append((text, pretranslated))

    # startup_greeting
    startup = greetings.get("startup_greeting", []) if isinstance(greetings, dict) else []
    if isinstance(startup, list):
        for line in startup:
            if isinstance(line, dict):
                text, spoken = line.get("text", ""), line.get("tts_text")
            else:
                text, spoken = str(line), None
            spoken = spoken or text
            if spoken and not offline_voice_path(character, "startup_greetings", spoken, base_dir).is_file():
                _add([(spoken, spoken != text)])

    # repeated_click (from greetings or character-specific defaults)
    has_explicit_repeated = isinstance(greetings, dict) and bool(
        greetings.get("repeated_click") or greetings.get("poke")
    )
    if has_explicit_repeated or character:
        for entry in repeated_click_entries(greetings, character):
            tts = entry.get("tts_text") or entry.get("text", "")
            if tts and not offline_voice_path(character, "repeated_clicks", tts, base_dir).is_file():
                is_pre = bool(entry.get("tts_text") and entry.get("tts_text") != entry.get("text"))
                _add([(tts, is_pre)])

    # daily_chat replaces legacy double-click lines, but not startup greetings
    daily_entries = daily_chat_entries(greetings)
    if daily_entries:
        _add(
            (
                (entry["tts_text"], entry["tts_text"] != entry["text"])
                for entry in daily_entries
            ),
        )
        return result
    # click_responses
    for entry in greetings.get("click_responses", []) or []:
        if isinstance(entry, dict):
            _add(entry.get("lines", []) or [])
    # tiers
    for tier in greetings.get("tiers", []) or []:
        lines = tier.get("lines", []) if isinstance(tier, dict) else (tier if isinstance(tier, list) else [])
        _add(lines)

    return result


def _aux_model_enable_thinking(config: dict):
    value = config.get("llm_aux_enable_thinking", None)
    return value if value in (True, False, None) else None


def _tts_should_translate(config: dict, text_language: str) -> bool:
    if not config.get("tts_translate_to_selected_language", True):
        return False
    return text_language not in {"Chinese", "zh", "中文"}


def _tts_translate_to_selected_language(
    config: dict,
    text: str,
    target_language: str,
    speaker_character: str = "",
) -> str:
    aux_url = str(config.get("llm_aux_api_url", "") or "").strip()
    api_url = aux_url or str(config.get("llm_api_url", "") or "").strip()
    api_key = str(config.get("llm_aux_api_key", "") or "").strip() or str(config.get("llm_api_key", "") or "").strip()
    model_id = str(config.get("llm_aux_model_id", "") or "").strip() or str(config.get("llm_model_id", "") or "").strip()
    if not api_url or not api_key or not model_id:
        return ""
    body = {
        "model": model_id,
        "messages": [
            {
                "role": "system",
                "content": _build_translation_system_prompt(
                    _tts_language_name(target_language),
                    text,
                    speaker_character,
                ),
            },
            {"role": "user", "content": text},
        ],
        "stream": False,
    }
    enable_thinking = _aux_model_enable_thinking(config)
    is_responses = urlsplit(api_url).path.rstrip("/").endswith("/responses") or (
        not aux_url and config.get("llm_api_mode") == "responses"
    )
    if is_responses:
        from llm_manager import (
            _apply_responses_thinking_options,
            _extract_response_output_text,
            _messages_to_responses_input,
            _responses_api_url,
        )

        instructions, input_items = _messages_to_responses_input(body.pop("messages"))
        body.update(instructions=instructions, input=input_items)
        _apply_responses_thinking_options(body, enable_thinking)
        api_url = _responses_api_url(api_url)
    elif enable_thinking is not None:
        body["enable_thinking"] = enable_thinking
        body["thinking"] = {"type": "enabled" if enable_thinking else "disabled"}
    if config.get("tts_gpt_sovits_runtime") and api_url.rstrip("/") in {
        "https://api.openai.com/v1/responses", "https://api.openai.com/v1/chat/completions",
    }:
        from realtime_story_tts import post_openai_story_json

        data = post_openai_story_json(api_url, api_key, body, QThread.currentThread().isInterruptionRequested)
    else:
        req = urllib.request.Request(
            api_url,
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    if is_responses:
        return _extract_response_output_text(data).strip()
    return data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()


def _tts_language_name(language: str) -> str:
    names = {
        "Japanese": "日语",
        "ja": "日语",
        "日文": "日语",
        "English": "英语",
        "en": "英语",
        "英文": "英语",
    }
    return names.get(language, language)


class TTSTranslationWorker(QThread):
    translated = Signal(int, int, str, str)
    error = Signal(str)

    def __init__(self, sequence: int, generation: int, text: str, character: str, config: dict, parent=None):
        super().__init__(parent)
        self.sequence = sequence
        self.generation = generation
        self._text = text
        self._character = character
        self._config = config

    def run(self):
        try:
            selected_language = self._config.get("tts_language", "Chinese") or "Chinese"
            text = strip_tts_action_tags(self._text)
            if not text:
                return
            if _tts_should_translate(self._config, selected_language):
                translated = _tts_translate_to_selected_language(
                    self._config, text, selected_language, self._character
                )
                if translated:
                    text = translated
            self.translated.emit(self.sequence, self.generation, text, self._character)
        except Exception as exc:
            self.error.emit(f"TTS translation: {exc}")
            text = strip_tts_action_tags(self._text)
            if text:
                self.translated.emit(self.sequence, self.generation, text, self._character)


class TTSRequestWorker(QThread):
    audio_ready = Signal(int, int, bytes, str)
    error = Signal(str)

    def __init__(self, sequence: int, generation: int, text: str, character: str, config: dict, parent=None):
        super().__init__(parent)
        self.sequence = sequence
        self.generation = generation
        self._text = text
        self._character = character
        self._config = config

    def run(self):
        try:
            selected_language = self._config.get("tts_language", "Chinese") or "Chinese"
            text_language = selected_language
            text = strip_tts_action_tags(self._text)
            if not text:
                return
            if _tts_should_translate(self._config, selected_language):
                translated = _tts_translate_to_selected_language(
                    self._config, text, selected_language, self._character
                )
                if translated:
                    text = translated
            self._synthesize_and_emit(text, text_language, selected_language)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            self.error.emit(f"TTS HTTP {exc.code}: {body[:240]}")
        except Exception as exc:
            self.error.emit(f"TTS: {exc}")

    def _streaming_enabled(self) -> bool:
        return bool(self._config.get("tts_streaming", True))

    def _build_payload(
        self,
        text: str,
        text_language: str,
        selected_language: str,
        *,
        streaming: bool,
    ) -> tuple[dict, dict[str, str]]:
        profile = effective_tts_voice_profile(self._character, self._config)
        prompt_text = self._reference_prompt_text(selected_language)
        paths = _gpt_sovits_model_paths(self._reference_character(), self._config)
        split_method, batch_size = _select_gpt_sovits_split_params(text, streaming=streaming)
        payload = _gpt_sovits_payload(
            text=text,
            text_language=text_language,
            reference_path=paths["reference"],
            prompt_text=prompt_text,
            temperature=profile["temperature"],
            speed_factor=profile["speed_factor"],
            top_k=profile["top_k"],
            top_p=profile["top_p"],
            repetition_penalty=profile["repetition_penalty"],
            text_split_method=split_method,
            batch_size=batch_size,
            streaming_mode=streaming,
        )
        return payload, paths

    def _synthesize_and_emit(self, text: str, text_language: str, selected_language: str):
        streaming = self._streaming_enabled()
        if not streaming:
            audio_bytes = self._generate_audio_bytes(text, text_language, selected_language)
            if audio_bytes:
                self.audio_ready.emit(self.sequence, self.generation, audio_bytes, "wav")
            return

        pieces = split_tts_segments(text, max_chars=55) if len(text) > 60 else [text]
        if not pieces:
            return
        url = self._tts_url()
        with _interactive_tts_scope(url):
            for piece in pieces:
                if self.isInterruptionRequested():
                    return
                payload, paths = self._build_payload(
                    piece, text_language, selected_language, streaming=True
                )
                with _tts_lock, _cross_process_tts_lock(url, self.isInterruptionRequested):
                    self._ensure_gpt_sovits_weights(paths)
                    session = _get_tts_session(url)
                    response = session.post(url + "tts", json=payload, stream=True, timeout=300)
                    try:
                        if response.status_code != 200:
                            self.error.emit(
                                f"TTS HTTP {response.status_code}: {self._response_error(response)}"
                            )
                            return
                        if callable(getattr(response, "iter_content", None)):
                            for wav_chunk in _iter_wav_stream_chunks(
                                response, self.isInterruptionRequested
                            ):
                                if wav_chunk:
                                    self.audio_ready.emit(
                                        self.sequence, self.generation, wav_chunk, "wav"
                                    )
                        else:
                            audio_bytes = response.content if response.content else None
                            if audio_bytes:
                                self.audio_ready.emit(
                                    self.sequence, self.generation, audio_bytes, "wav"
                                )
                    finally:
                        close = getattr(response, "close", None)
                        if callable(close):
                            close()

    def _generate_audio_bytes(self, text: str, text_language: str,
                              selected_language: str, *, interactive: bool = True) -> bytes | None:
        """Prepare payload, switch weights, POST /tts — serialized in-process & cross-process."""
        payload, paths = self._build_payload(
            text, text_language, selected_language, streaming=False
        )
        url = self._tts_url()

        def _execute() -> bytes | None:
            with _tts_lock, _cross_process_tts_lock(url, self.isInterruptionRequested):
                self._ensure_gpt_sovits_weights(paths)
                session = _get_tts_session(url)
                response = session.post(url + "tts", json=payload, stream=False, timeout=300)
                try:
                    if response.status_code != 200:
                        self.error.emit(
                            f"TTS HTTP {response.status_code}: {self._response_error(response)}"
                        )
                        return None
                    return response.content if response.content else None
                finally:
                    close = getattr(response, "close", None)
                    if callable(close):
                        close()

        if interactive:
            with _interactive_tts_scope(url):
                return _execute()
        return _execute()

    def _response_error(self, response) -> str:
        try:
            data = response.json()
            message = str(data.get("message", "") or "").strip()
            detail = str(data.get("detail", "") or "").strip()
            exception = str(data.get("Exception", "") or "").strip()
            text = " | ".join(part for part in (message, detail, exception) if part)
            if text:
                return text[:240]
        except Exception:
            pass
        return response.text[:240]

    def _current_server_weights(self, url: str) -> tuple[str, str]:
        state_gpt, state_sovits, state_ts = _read_tts_state_weights(url)
        local_yaml = _read_local_runtime_weights(self._config, url)
        if local_yaml is not None:
            yaml_gpt, yaml_sovits, yaml_mtime = local_yaml
            if yaml_mtime >= state_ts or not (state_gpt and state_sovits):
                return yaml_gpt, yaml_sovits
        if state_gpt and state_sovits:
            return state_gpt, state_sovits
        if _current_gpt_sovits_weights is not None:
            return _current_gpt_sovits_weights
        return "", ""

    def _ensure_gpt_sovits_weights(self, paths: dict[str, str]):
        global _current_gpt_sovits_weights
        url = self._tts_url()
        target_gpt = _norm_weight_path(paths["gpt"])
        target_sovits = _norm_weight_path(paths["sovits"])
        cur_gpt, cur_sovits = self._current_server_weights(url)
        if cur_gpt != target_gpt:
            self._set_gpt_sovits_weight("set_gpt_weights", paths["gpt"])
            cur_gpt = target_gpt
        if cur_sovits != target_sovits:
            self._set_gpt_sovits_weight("set_sovits_weights", paths["sovits"])
            cur_sovits = target_sovits
        _current_gpt_sovits_weights = (cur_gpt, cur_sovits)
        _write_tts_state_weights(url, cur_gpt, cur_sovits)

    def _set_gpt_sovits_weight(self, endpoint: str, path: str):
        url = self._tts_url()
        session = _get_tts_session(url)
        response = session.get(
            url + endpoint,
            params={"weights_path": path},
            timeout=60,
        )
        if response.status_code != 200:
            raise RuntimeError(f"{endpoint} failed: {self._response_error(response)}")
        try:
            data = response.json()
            if str(data.get("message", "")).lower() != "success":
                raise RuntimeError(f"{endpoint} failed: {data}")
        except ValueError:
            pass

    def _read_framed_stream(self, response):
        buffer = bytearray()
        expected_size = None
        for chunk in response.iter_content(chunk_size=65536):
            if self.isInterruptionRequested():
                response.close()
                return
            if not chunk:
                continue
            buffer.extend(chunk)
            while True:
                if expected_size is None:
                    if len(buffer) < 4:
                        break
                    expected_size = struct.unpack(">I", buffer[:4])[0]
                    del buffer[:4]
                if len(buffer) < expected_size:
                    break
                audio = bytes(buffer[:expected_size])
                del buffer[:expected_size]
                expected_size = None
                if audio:
                    self.audio_ready.emit(self.sequence, self.generation, audio, "ogg")

    def _tts_url(self) -> str:
        url = str(self._config.get("tts_api_url", "") or "").strip() or "http://127.0.0.1:9880/"
        return url if url.endswith("/") else url + "/"

    def _reference_character(self) -> str:
        return str(self._config.get("tts_reference_character", "") or "").strip() or self._character

    def _reference_audio_path(self) -> str:
        ref_char = self._reference_character()
        cached = _audio_path_cache.get(ref_char)
        if cached is not None:
            return cached
        ref_dir = app_base_dir() / "audio_reference"
        for suffix in (".mp3", ".wav", ".flac", ".ogg", ".m4a"):
            path = ref_dir / f"{ref_char}{suffix}"
            if path.exists():
                result = str(path)
                _audio_path_cache[ref_char] = result
                return result
        result = str(ref_dir / f"{ref_char}.mp3")
        _audio_path_cache[ref_char] = result
        return result

    def _reference_prompt_text(self, text_language: str) -> str:
        if text_language not in {"Japanese", "ja", "日文"}:
            return ""
        ref_char = self._reference_character()
        data = _load_dialog_json()
        value = data.get(ref_char, "")
        return value if isinstance(value, str) else ""

    def _apply_qwen_lora(self, payload: dict):
        global _current_loaded_lora
        loras = self._available_qwen_loras()
        if loras is None:
            return
        lora_id = self._reference_lora_id()
        if lora_id and lora_id in loras:
            payload["lora_id"] = lora_id
            _current_loaded_lora = lora_id
            return
        if _current_loaded_lora is not None:
            self._unload_qwen_lora()
            _current_loaded_lora = None

    def _available_qwen_loras(self) -> dict | None:
        global _lora_list_cache, _lora_list_cache_time
        now = time.monotonic()
        if _lora_list_cache is not None and (now - _lora_list_cache_time) < _LORA_LIST_TTL:
            return _lora_list_cache if _lora_list_cache else None
        try:
            response = requests.get(self._tts_url() + "lora/list", timeout=5)
            if response.status_code != 200:
                _lora_list_cache = {}
                _lora_list_cache_time = now
                return None
            loras = response.json().get("loras")
            _lora_list_cache = loras if isinstance(loras, dict) else {}
            _lora_list_cache_time = now
            return _lora_list_cache if _lora_list_cache else None
        except Exception:
            _lora_list_cache = {}
            _lora_list_cache_time = now
            return None

    def _unload_qwen_lora(self):
        try:
            requests.post(self._tts_url() + "lora/unload", timeout=5)
        except Exception:
            pass

    def _reference_lora_id(self) -> str:
        data = _load_dialog_json()
        groups = data.get(_DIALOG_GROUPS_KEY, {})
        if not isinstance(groups, dict):
            return ""
        ref_char = self._reference_character()
        for group in groups.values():
            if not isinstance(group, dict):
                continue
            if ref_char in group.get("characters", []):
                return str(group.get("lora_id", "") or "").strip()
        return ""


class CachedTTSRequestWorker(TTSRequestWorker):
    """Like :class:`TTSRequestWorker` but persists generated audio to a local cache.

    - Cache hit → read bytes and emit ``audio_ready`` immediately (unless
      ``play_when_ready=False``, in which case the signal is suppressed).
    - Cache miss → call GPT-SoVITS, write to a temp file, atomically replace
      the final cache path, then emit (respecting ``play_when_ready``).
    - The cache path is determined by :func:`tts_cache_path`.
    """

    def __init__(self, sequence: int, generation: int, text: str, character: str,
                 config: dict, play_when_ready: bool = True, parent=None):
        super().__init__(sequence, generation, text, character, config, parent)
        self._play_when_ready = play_when_ready

    def run(self):
        audio = self.load_or_generate_audio()
        if audio and self._play_when_ready:
            self.audio_ready.emit(self.sequence, self.generation, audio, "wav")

    def load_or_generate_audio(self) -> bytes | None:
        """Return cached or newly synthesized audio in the calling worker thread."""
        cache_path = tts_cache_path(self._text, self._character, self._config)

        # Cache hit — return cached wav bytes (single stat instead of
        # exists() + stat())
        try:
            cache_hit = cache_path.stat().st_size > 44
        except OSError:
            cache_hit = False
        if cache_hit:
            try:
                return cache_path.read_bytes()
            except Exception as exc:
                # Corrupt cache — fall through to re-generate
                print(f"[tts] cache read failed for {cache_path.name}: {exc}")

        # Cache miss — translate then delegate to shared locked generator
        try:
            selected_language = self._config.get("tts_language", "Chinese") or "Chinese"
            text_language = selected_language
            text = strip_tts_action_tags(self._text)
            if not text:
                return
            if _tts_should_translate(self._config, selected_language):
                translated = _tts_translate_to_selected_language(
                    self._config, text, selected_language, self._character
                )
                if translated:
                    text = translated

            if not self._play_when_ready:
                wait_deadline = time.monotonic() + 5.0
                while is_interactive_tts_busy(self._config) and time.monotonic() < wait_deadline:
                    if self.isInterruptionRequested():
                        return None
                    time.sleep(0.1)

            audio_bytes = self._generate_audio_bytes(
                text,
                text_language,
                selected_language,
                interactive=self._play_when_ready,
            )
            if not audio_bytes:
                return

            # Write atomically: temp file then replace
            try:
                cache_dir = cache_path.parent
                cache_dir.mkdir(parents=True, exist_ok=True)
                fd, tmp = tempfile.mkstemp(suffix=".wav", prefix=".tmp_", dir=str(cache_dir))
                try:
                    os.write(fd, audio_bytes)
                finally:
                    os.close(fd)
                os.replace(tmp, str(cache_path))
            except Exception as exc:
                print(f"[tts] cache write failed for {cache_path.name}: {exc}")

            return audio_bytes
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            self.error.emit(f"TTS HTTP {exc.code}: {body[:240]}")
        except Exception as exc:
            self.error.emit(f"TTS: {exc}")


# ---------------------------------------------------------------------------
# OpenAI-compatible TTS synthesis (for ambient dialogue prefetch)
# ---------------------------------------------------------------------------

def openai_tts_synthesize(
    text: str,
    config: dict,
    voice: str = "",
    model: str = "",
) -> bytes | None:
    """Call an OpenAI-compatible ``/v1/audio/speech`` endpoint to synthesize audio.

    Returns raw MP3 bytes on success, or ``None`` on any failure.

    Config keys used:
    - ``openai_tts_api_url``  — base URL (default: ``https://api.openai.com/v1``)
    - ``openai_tts_api_key``  — API key (falls back to ``llm_api_key``)
    - ``openai_tts_voice``    — voice name (default: ``"alloy"``)
    - ``openai_tts_model``    — model name (default: ``"tts-1"``)
    - ``openai_tts_speed``    — speech speed 0.25-4.0 (default: ``1.0``)
    """
    api_url = str(config.get("openai_tts_api_url", "") or "").strip()
    if not api_url:
        api_url = "https://api.openai.com/v1"
    api_url = api_url.rstrip("/")

    api_key = str(config.get("openai_tts_api_key", "") or "").strip()
    if not api_key:
        api_key = str(config.get("llm_api_key", "") or "").strip()
    if not api_key:
        return None

    voice = voice or str(config.get("openai_tts_voice", "") or "").strip() or "alloy"
    model = model or str(config.get("openai_tts_model", "") or "").strip() or "tts-1"
    speed = float(config.get("openai_tts_speed", 1.0) or 1.0)

    endpoint = f"{api_url}/audio/speech"
    payload = {
        "model": model,
        "input": text,
        "voice": voice,
        "response_format": "mp3",
        "speed": max(0.25, min(4.0, speed)),
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    try:
        req = urllib.request.Request(
            endpoint,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            audio_bytes = resp.read()
        if audio_bytes and len(audio_bytes) > 100:
            return audio_bytes
        return None
    except Exception as exc:
        print(f"[openai-tts] synthesis failed: {exc}")
        return None


def openai_tts_cache_path(text: str, character: str, config: dict) -> pathlib.Path:
    """Return the cache ``.mp3`` path for OpenAI TTS output."""
    voice = str(config.get("openai_tts_voice", "") or "").strip() or "alloy"
    model = str(config.get("openai_tts_model", "") or "").strip() or "tts-1"
    speed = str(config.get("openai_tts_speed", 1.0) or 1.0)
    key = "\n".join([text, character, voice, model, speed])
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    cache_dir = app_base_dir() / "tts_cache" / "openai_tts" / (character or "default")
    return cache_dir / f"{digest}.mp3"


class TTSPlayer(QObject):
    error = Signal(str)
    level_changed = Signal(float)
    playback_finished = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._queue: queue.Queue[np.ndarray] = queue.Queue()
        self._stream = None
        self._sample_rate = 0
        self._channels = 1
        self._current_chunk = None
        self._current_pos = 0
        self._level = 0.0
        self._playback_active = False
        self._volume = 0.7
        self._level_timer = QTimer(self)
        self._level_timer.setInterval(33)
        self._level_timer.timeout.connect(self._emit_level)

    def set_volume(self, value: float):
        """Set playback volume.  Range 0.0 (mute) to 1.0 (full)."""
        self._volume = max(0.0, min(1.0, float(value)))

    def volume(self) -> float:
        return self._volume

    def stop(self):
        try:
            if self._stream is not None:
                self._stream.stop()
                self._stream.close()
        except Exception:
            pass
        self._stream = None
        self._current_chunk = None
        self._current_pos = 0
        self._level = 0.0
        self._playback_active = False
        self.level_changed.emit(0.0)
        self._level_timer.stop()
        while True:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break

    def enqueue(self, audio: bytes, media_type: str = "wav") -> bool:
        if not audio:
            return False
        del media_type
        try:
            data, sample_rate = sf.read(io.BytesIO(audio), dtype="float32")
        except Exception as exc:
            self.error.emit(f"TTS audio decode failed: {exc}")
            return False
        if data.size == 0:
            return False
        if data.ndim == 1:
            data = data.reshape(-1, 1)
        if self._stream is not None and sample_rate != self._sample_rate:
            self.stop()
        self._ensure_stream(sample_rate, data.shape[1])
        if self._stream is None:
            return False
        self._queue.put_nowait(data)
        self._playback_active = True
        if not self._level_timer.isActive():
            self._level_timer.start()
        return True

    def is_idle(self) -> bool:
        return (
            not self._playback_active
            or (
                self._queue.empty()
                and (self._current_chunk is None or self._current_pos >= len(self._current_chunk))
            )
        )

    def _ensure_stream(self, sample_rate: int, channels: int):
        if self._stream is not None:
            return
        self._sample_rate = sample_rate
        self._channels = max(1, channels)
        try:
            self._stream = sd.OutputStream(
                samplerate=sample_rate,
                channels=self._channels,
                dtype="float32",
                callback=self._audio_callback,
                blocksize=0,
            )
            self._stream.start()
            if not self._level_timer.isActive():
                self._level_timer.start()
        except Exception as exc:
            self._stream = None
            self.error.emit(f"TTS playback failed: {exc}")

    def _audio_callback(self, outdata, frames, time_info, status):
        del time_info, status
        outdata.fill(0)
        filled = 0
        while filled < frames:
            if self._current_chunk is None or self._current_pos >= len(self._current_chunk):
                try:
                    self._current_chunk = self._queue.get_nowait()
                except queue.Empty:
                    return
                self._current_pos = 0

            available = len(self._current_chunk) - self._current_pos
            take = min(available, frames - filled)
            chunk = self._current_chunk[self._current_pos:self._current_pos + take]
            # Apply volume
            if self._volume < 0.999:
                chunk = chunk * self._volume
            self._level = max(self._level, min(chunk.max() * 0.35, 0.55))
            if chunk.shape[1] == self._channels:
                outdata[filled:filled + take] = chunk
            elif self._channels == 1:
                outdata[filled:filled + take, 0] = chunk[:, 0]
            else:
                outdata[filled:filled + take, :chunk.shape[1]] = chunk
            self._current_pos += take
            filled += take

    def _emit_level(self):
        level = self._level
        self._level *= 0.55
        done = (
            self._queue.empty()
            and (self._current_chunk is None or self._current_pos >= len(self._current_chunk))
        )
        if done and level < 0.01:
            self._level_timer.stop()
            self.level_changed.emit(0.0)
            if self._playback_active:
                self._playback_active = False
                self.playback_finished.emit()
            return
        self.level_changed.emit(level)
