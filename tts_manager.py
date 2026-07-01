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
import urllib.request

import numpy as np
import requests
import sounddevice as sd
import soundfile as sf

from PySide6.QtCore import QObject, QThread, QTimer, Signal

from process_utils import app_base_dir

# ---------------------------------------------------------------------------
# Module-level caches — shared across all TTSRequestWorker instances
# ---------------------------------------------------------------------------

# dialog.json: cache with mtime-based invalidation
_dialog_json_cache: dict | None = None
_dialog_json_mtime: float = 0.0

# Reference audio path per character (content of audio_reference/ rarely changes)
_audio_path_cache: dict[str, str] = {}

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


def _remote_tts_root(config: dict) -> str:
    value = str(config.get("tts_gpt_sovits_remote_root", "") or "").strip()
    return (value or _GPT_SOVITS_REMOTE_ROOT).rstrip("/")


def _gpt_sovits_model_paths(character: str, config: dict) -> dict[str, str]:
    ref_char = (character or "").strip().lower()
    gpt_file = _GPT_SOVITS_GPT_FILES.get(ref_char)
    sovits_file = _GPT_SOVITS_SOVITS_FILES.get(ref_char)
    if not gpt_file or not sovits_file:
        raise ValueError(f"GPT-SoVITS weights not configured for character: {character}")
    root = _remote_tts_root(config)
    return {
        "gpt": f"{root}/GPT-SoVITS/GPT_weights_v2/{gpt_file}",
        "sovits": f"{root}/GPT-SoVITS/SoVITS_weights_v2/{sovits_file}",
        "reference": f"{root}/audio_reference_wav/{ref_char}.wav",
    }


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


def _gpt_sovits_payload(
    *,
    text: str,
    text_language: str,
    reference_path: str,
    prompt_text: str,
    temperature: float,
) -> dict:
    return {
        "text": text,
        "text_lang": _tts_api_language_code(text_language),
        "ref_audio_path": reference_path,
        "prompt_text": prompt_text,
        "prompt_lang": "ja",
        "top_k": 5,
        "top_p": 1,
        "temperature": temperature,
        "text_split_method": "cut5",
        "batch_size": 1,
        "media_type": "wav",
        "streaming_mode": False,
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


_ONE_CHAR_SURNAMES = frozenset({"凑", "要"})


def _find_referenced_characters(text: str) -> dict:
    if not text:
        return {}
    matched: dict[str, tuple[str, str]] = {}
    for cn, (jp, en_) in CHARACTER_TRILINGUAL_NAMES.items():
        if cn in text:
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


def _build_translation_system_prompt(target_language_name: str, text: str = "") -> str:
    referenced = _find_referenced_characters(text)
    if referenced:
        appendix = "\n\n### BanG Dream! Character Name Reference (CN | JP | EN)\n"
        appendix += "\n".join(
            f"  {cn}  |  {jp}  |  {en_}"
            for cn, (jp, en_) in referenced.items()
        )
        return (
            f"把用户给出的中文聊天台词翻译成自然{target_language_name}，只输出译文，不要解释。保留语气，不要输出动作标签。"
            f"翻译人物名称时请参照以下对照表，按目标语言使用对应名称：\n{appendix}"
        )
    return f"把用户给出的中文聊天台词翻译成自然{target_language_name}，只输出译文，不要解释。保留语气，不要输出动作标签。"


def strip_tts_action_tags(text: str) -> str:
    return _ACTION_TAG_RE.sub("", text).strip()


def split_tts_segments(text: str, max_chars: int = 90) -> list[str]:
    """Split assistant text into small TTS-friendly segments."""
    cleaned = strip_tts_action_tags(str(text or ""))
    cleaned = re.sub(r"[ \t\r\f\v]+", " ", cleaned)
    cleaned = re.sub(r"\n+", "\n", cleaned).strip()
    if not cleaned:
        return []

    pieces: list[str] = []
    sentence_re = re.compile(r".+?(?:[。！？!?；;]+|$)", re.S)
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
    for chunk in re.findall(r".+?(?:[，、,：:]+|$)", text, flags=re.S):
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
    try:
        temperature = str(max(0.01, min(2.0, float(config.get("tts_temperature", 0.9)))))
    except (TypeError, ValueError):
        temperature = "0.9"
    remote_root = _remote_tts_root(config)
    paths = _gpt_sovits_model_paths(ref_char, config)
    # Build a deterministic key from all inputs that affect the output audio
    key_parts = [
        text,
        ref_char,
        language,
        temperature,
        remote_root,
        paths.get("gpt", ""),
        paths.get("sovits", ""),
    ]
    key = "\n".join(key_parts)
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    cache_dir = app_base_dir() / "tts_cache" / "gpt_sovits" / ref_char
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / f"{digest}.wav"


def collect_greeting_tts_lines(greetings: dict) -> list[str]:
    """Collect all unique non-empty text lines from a ``greetings.json`` dict.

    Order: ``startup_greeting`` → ``click_responses[].lines`` → ``tiers[].lines``.
    Duplicates are removed while preserving first-occurrence order.
    """
    seen: set[str] = set()
    result: list[str] = []

    def _add(lines):
        for line in lines:
            text = strip_tts_action_tags(str(line).strip())
            if text and text not in seen:
                seen.add(text)
                result.append(text)

    # startup_greeting
    startup = greetings.get("startup_greeting", [])
    if isinstance(startup, list):
        _add(startup)
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


def _tts_translate_to_selected_language(config: dict, text: str, target_language: str) -> str:
    api_url = str(config.get("llm_aux_api_url", "") or "").strip() or str(config.get("llm_api_url", "") or "").strip()
    api_key = str(config.get("llm_aux_api_key", "") or "").strip() or str(config.get("llm_api_key", "") or "").strip()
    model_id = str(config.get("llm_aux_model_id", "") or "").strip() or str(config.get("llm_model_id", "") or "").strip()
    if not api_url or not api_key or not model_id:
        return ""
    body = {
        "model": model_id,
        "messages": [
            {"role": "system", "content": _build_translation_system_prompt(_tts_language_name(target_language), text)},
            {"role": "user", "content": text},
        ],
        "stream": False,
    }
    enable_thinking = _aux_model_enable_thinking(config)
    if enable_thinking is not None:
        body["enable_thinking"] = enable_thinking
        body["thinking"] = {"type": "enabled" if enable_thinking else "disabled"}
    req = urllib.request.Request(
        api_url,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode("utf-8"))
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
                translated = _tts_translate_to_selected_language(self._config, text, selected_language)
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
                translated = _tts_translate_to_selected_language(self._config, text, selected_language)
                if translated:
                    text = translated
            audio_bytes = self._generate_audio_bytes(text, text_language, selected_language)
            if audio_bytes:
                self.audio_ready.emit(self.sequence, self.generation, audio_bytes, "wav")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            self.error.emit(f"TTS HTTP {exc.code}: {body[:240]}")
        except Exception as exc:
            self.error.emit(f"TTS: {exc}")

    def _generate_audio_bytes(self, text: str, text_language: str,
                              selected_language: str) -> bytes | None:
        """Prepare payload, switch weights, POST /tts — atomic under ``_tts_lock``."""
        try:
            temperature = max(0.01, min(2.0, float(self._config.get("tts_temperature", 0.9))))
        except (TypeError, ValueError):
            temperature = 0.9
        prompt_text = self._reference_prompt_text(selected_language)
        paths = _gpt_sovits_model_paths(self._reference_character(), self._config)
        payload = _gpt_sovits_payload(
            text=text,
            text_language=text_language,
            reference_path=paths["reference"],
            prompt_text=prompt_text,
            temperature=temperature,
        )
        with _tts_lock:
            self._ensure_gpt_sovits_weights(paths)
            response = requests.post(self._tts_url() + "tts", json=payload, stream=False, timeout=300)
        if response.status_code != 200:
            self.error.emit(f"TTS HTTP {response.status_code}: {self._response_error(response)}")
            return None
        return response.content if response.content else None

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

    def _ensure_gpt_sovits_weights(self, paths: dict[str, str]):
        global _current_gpt_sovits_weights
        target = (paths["gpt"], paths["sovits"])
        if _current_gpt_sovits_weights == target:
            return
        self._set_gpt_sovits_weight("set_gpt_weights", paths["gpt"])
        self._set_gpt_sovits_weight("set_sovits_weights", paths["sovits"])
        _current_gpt_sovits_weights = target

    def _set_gpt_sovits_weight(self, endpoint: str, path: str):
        response = requests.get(
            self._tts_url() + endpoint,
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
        ref_char = self._reference_character()
        cache_path = tts_cache_path(self._text, ref_char, self._config)

        # Cache hit — return cached wav bytes
        if cache_path.exists() and cache_path.stat().st_size > 44:
            try:
                audio_bytes = cache_path.read_bytes()
                if self._play_when_ready:
                    self.audio_ready.emit(self.sequence, self.generation, audio_bytes, "wav")
                return
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
                translated = _tts_translate_to_selected_language(self._config, text, selected_language)
                if translated:
                    text = translated

            audio_bytes = self._generate_audio_bytes(text, text_language, selected_language)
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

            if self._play_when_ready:
                self.audio_ready.emit(self.sequence, self.generation, audio_bytes, "wav")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            self.error.emit(f"TTS HTTP {exc.code}: {body[:240]}")
        except Exception as exc:
            self.error.emit(f"TTS: {exc}")


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

    def enqueue(self, audio: bytes, media_type: str = "wav"):
        if not audio:
            return
        del media_type
        try:
            data, sample_rate = sf.read(io.BytesIO(audio), dtype="float32")
        except Exception as exc:
            self.error.emit(f"TTS audio decode failed: {exc}")
            return
        if data.size == 0:
            return
        if data.ndim == 1:
            data = data.reshape(-1, 1)
        if self._stream is not None and sample_rate != self._sample_rate:
            self.stop()
        self._ensure_stream(sample_rate, data.shape[1])
        if self._stream is None:
            return
        self._queue.put_nowait(data)
        self._playback_active = True
        if not self._level_timer.isActive():
            self._level_timer.start()

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
            rms = float(np.sqrt(np.mean(chunk * chunk)))
            peak = float(np.max(np.abs(chunk)))
            self._level = max(self._level, min(max(rms * 4.0, peak * 0.35), 0.55))
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
