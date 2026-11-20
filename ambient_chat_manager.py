"""Ambient Context-Aware Chat Manager for BandoriPet.

Provides living, proactive character dialogue by blending:
1. Real-time desktop context (system time, media playback, weather).
2. Role-specific few-shot exemplars from greetings.json and CHARACTER_PROMPTS.
3. Zero-latency prefetch pool so user clicks or idle ambient events feel instant.
4. Graceful offline fallback to static daily_chat entries if LLM is unavailable.
"""

from __future__ import annotations

import datetime
import json
import os
import random
import re
import sys
import threading
import urllib.request
import urllib.error
from pathlib import Path
from PySide6.QtCore import QObject, Signal, QThread, QTimer

from process_utils import app_base_dir
from media_session_manager import get_current_media_snapshot, format_track_line
import weather_manager

# Extract action tags like [natural01], [serious01], [smile01]
_ACTION_TAG_REGEX = re.compile(r"\[([a-zA-Z0-9_]+)\]")


def parse_dialogue_motion(text: str) -> tuple[str, str]:
    """Split response text into clean dialogue and action motion tag."""
    matches = _ACTION_TAG_REGEX.findall(text)
    clean_text = _ACTION_TAG_REGEX.sub("", text).strip()
    motion = matches[-1] if matches else ""
    return clean_text, motion


def gather_desktop_context(config_manager=None) -> dict[str, str]:
    """Gather current real-world environment snapshot."""
    now = datetime.datetime.now()
    now_str = now.strftime("%H:%M")
    hour = now.hour

    if 0 <= hour < 5:
        time_phase = "深夜/凌晨（应休息时间）"
    elif 5 <= hour < 9:
        time_phase = "清晨/早晨"
    elif 9 <= hour < 12:
        time_phase = "上午（学习工作时间）"
    elif 12 <= hour < 14:
        time_phase = "中午/午休时间"
    elif 14 <= hour < 18:
        time_phase = "下午"
    elif 18 <= hour < 22:
        time_phase = "傍晚/夜晚"
    else:
        time_phase = "深夜（休息准备）"

    # Music snapshot
    try:
        media_snapshot = get_current_media_snapshot()
        if media_snapshot and media_snapshot.playback_status == "playing":
            music_info = format_track_line(media_snapshot)
        else:
            music_info = "静音（未播放音乐）"
    except Exception:
        music_info = "静音（未播放音乐）"

    # Weather snapshot
    weather_info = ""
    if config_manager and config_manager.get("weather_enabled"):
        try:
            w_text = weather_manager.get_weather_prompt(
                config_manager.get("weather_private_key", ""),
                config_manager.get("weather_api_host", ""),
                config_manager.get("weather_city", ""),
                config_manager.get("weather_key_id", ""),
                config_manager.get("weather_project_id", ""),
            )
            if w_text:
                weather_info = w_text.strip().replace("\n", " ")
        except Exception:
            pass

    user_name = config_manager.get("user_name", "你") if config_manager else "你"

    return {
        "time_str": now_str,
        "time_phase": time_phase,
        "music": music_info,
        "weather": weather_info,
        "user_name": user_name,
    }


def load_character_few_shots(character: str) -> list[str]:
    """Extract sample dialogue from greetings.json for Few-Shot prompt conditioning."""
    if not character:
        return []
    path = app_base_dir() / "characters" / character / "greetings.json"
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        daily_list = data.get("daily_chat", [])
        samples = []
        for item in daily_list[:6]:
            t = item.get("text", "").strip()
            m = item.get("motion", "")
            if t:
                tag = f" [{m}]" if m else ""
                samples.append(f'- "{t}"{tag}')
        return samples
    except Exception:
        return []


def build_ambient_prompt(character: str, context: dict[str, str], config_manager=None) -> str:
    """Build a compact, persona-faithful prompt for ambient living dialogue."""
    from llm_manager import CHARACTER_PROMPTS

    base_desc = CHARACTER_PROMPTS.get(character, "")
    few_shots = load_character_few_shots(character)
    few_shots_text = "\n".join(few_shots) if few_shots else ""

    # Character-specific personality hints
    persona_summary = ""
    if base_desc:
        # Extract the core identity section
        lines = [l.strip() for l in base_desc.splitlines() if l.strip()]
        persona_summary = "\n".join(lines[:12])

    prompt = f"""你是 BanG Dream! 中的角色：{character}。
请保持角色一贯的语言习惯、标点习惯（如特有口癖、省略号、语气词）。
严格禁止任何客服式、AI助手机器人式套话。

【角色设定参考】：
{persona_summary}

【角色原版经典台词范例】：
{few_shots_text}

【当前真实桌面环境】：
- 系统当前时间：{context.get('time_str')}（{context.get('time_phase')}）
- 用户电脑正在播放的音乐：{context.get('music')}
- 外部天气状况：{context.get('weather') or '舒适晴朗'}
- 陪伴对象昵称：{context.get('user_name', '你')}

【台词输出要求】：
你正以桌面宠物的形态陪伴在{context.get('user_name')}身旁。
请结合当前的真实桌面环境（注意当前时间是 {context.get('time_str')}），用符合你性格口吻的语句说一两句日常碎碎念。
- 字数严格控制在 20 到 38 个中文字符以内。
- 句末必须带有且仅带有 1 个 Live2D 动作标签（如 [natural01]、[serious01]、[smile01]、[thinking]、[angry01] 等）。
- 严禁输出任何额外前缀、心理描写或解释，只输出台词本身。"""

    return prompt


class AmbientPrefetchWorker(QThread):
    """Background worker that calls LLM API to prepare one ambient dialogue entry."""
    fetched = Signal(str, dict)  # character, entry dict

    def __init__(self, character: str, config_manager, parent=None):
        super().__init__(parent)
        self._character = character
        self._cfg = config_manager

    def run(self):
        if not self._cfg or not self._character:
            return
        api_url = self._cfg.get("llm_api_url", "").strip()
        api_key = self._cfg.get("llm_api_key", "").strip()
        if not api_url or not api_key:
            return

        context = gather_desktop_context(self._cfg)
        prompt = build_ambient_prompt(self._character, context, self._cfg)
        model_id = self._cfg.get("llm_model_id", "gpt-4o-mini")

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }

        user_content = f"（{context.get('user_name', '用户')}轻轻点击了你，或者在桌面看向你）"

        if "responses" in api_url:
            payload = {
                "model": model_id,
                "input": [
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": user_content},
                ],
            }
        else:
            payload = {
                "model": model_id,
                "messages": [
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": user_content},
                ],
                "max_tokens": 75,
                "temperature": 0.75,
            }

        try:
            req = urllib.request.Request(
                api_url,
                data=json.dumps(payload).encode("utf-8"),
                headers=headers,
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                res_data = json.loads(resp.read().decode("utf-8"))

            raw_reply = ""
            if "responses" in api_url:
                output_items = res_data.get("output", [])
                for item in output_items:
                    if item.get("type") == "message":
                        for c in item.get("content", []):
                            if c.get("type") == "output_text":
                                raw_reply = c.get("text", "").strip()
                                break
            else:
                raw_reply = res_data["choices"][0]["message"]["content"].strip()

            if raw_reply:
                clean_text, motion = parse_dialogue_motion(raw_reply)
                if clean_text:
                    entry = {
                        "text": clean_text,
                        "motion": motion,
                        "expression": "",
                        "tts_text": clean_text,
                        "is_dynamic": True,
                    }
                    self.fetched.emit(self._character, entry)
        except Exception as exc:
            # Silent fallback; standard pet flow is unaffected
            pass


class AmbientChatManager(QObject):
    """Orchestrates zero-latency ambient dialogue prefetch for the desktop pet."""

    def __init__(self, config_manager, parent=None):
        super().__init__(parent)
        self._cfg = config_manager
        # character -> list of prefetched entry dicts
        self._pool: dict[str, list[dict]] = {}
        self._active_worker: AmbientPrefetchWorker | None = None
        self._current_char = ""

        # Auto-refresh timer: refresh pool every 15 minutes to reflect passing time/music
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(15 * 60 * 1000)
        self._refresh_timer.timeout.connect(self._on_auto_refresh)
        self._refresh_timer.start()

    def set_character(self, character: str):
        if self._current_char != character:
            self._current_char = character
            self.trigger_prefetch(character)

    def trigger_prefetch(self, character: str):
        """Asynchronously prefetch one dialogue entry in the background."""
        if not character or (self._active_worker and self._active_worker.isRunning()):
            return
        worker = AmbientPrefetchWorker(character, self._cfg, self)
        worker.fetched.connect(self._on_entry_fetched)
        worker.finished.connect(self._on_worker_finished)
        self._active_worker = worker
        worker.start()

    def _on_entry_fetched(self, character: str, entry: dict):
        pool = self._pool.setdefault(character, [])
        # Keep at most 2 fresh entries per character
        if len(pool) >= 2:
            pool.pop(0)
        pool.append(entry)

    def _on_worker_finished(self):
        self._active_worker = None

    def _on_auto_refresh(self):
        if self._current_char:
            self.trigger_prefetch(self._current_char)

    def pop_ambient_entry(self, character: str) -> dict | None:
        """Get an instant dialogue entry with 0ms latency.
        
        Returns None if pool is empty (caller should fallback to daily_chat.py).
        Automatically schedules background prefetch of the next entry.
        """
        pool = self._pool.get(character, [])
        entry = pool.pop(0) if pool else None
        # Always trigger a fresh background pull after consumption
        self.trigger_prefetch(character)
        return entry
