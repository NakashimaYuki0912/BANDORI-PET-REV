"""Ambient Context-Aware Chat Manager for BandoriPet.

Provides living, proactive character dialogue by blending:
1. Role-specific few-shot exemplars from greetings.json and CHARACTER_PROMPTS.
2. Dynamic topic variations (character banter, band daily life, light ambient companion thoughts).
3. Bandmates and relation awareness from band.json, outfit.json and lore connections.
4. Real-time desktop context (system time, media playback, weather) without repetitive canned reporting.
5. Zero-latency prefetch pool so user clicks or idle ambient events feel instant.
6. Graceful offline fallback to static daily_chat entries if LLM is unavailable.
"""

from __future__ import annotations

import datetime
import json
import os
import random
import re
import sys
import threading
import time
import urllib.request
import urllib.error
from pathlib import Path
from PySide6.QtCore import QObject, Signal, QThread, QTimer

from process_utils import app_base_dir
from media_session_manager import get_current_media_snapshot, format_track_line
import weather_manager

# Extract action tags like [natural01], [serious01], [smile01]
_ACTION_TAG_REGEX = re.compile(r"\[([a-zA-Z0-9_]+)\]")

# Well-known BanG Dream relations / banter targets across bands and schools
_CROSS_CHARACTER_RELATIONS: dict[str, list[str]] = {
    "sayo": ["冰川日菜（妹妹）", "今井莉莎（同班同学与饼干）", "美竹兰（吉他手切磋）"],
    "hina": ["冰川纱夜（最喜欢的姐姐）", "丸山彩（彩彩）", "户山香澄（噜~的同好）"],
    "tomoe": ["宇田川亚子（妹妹）", "美竹兰（青梅竹马）", "佐藤益木（拉面与鼓手同好）"],
    "ako": ["宇田川巴（崇拜的姐姐）", "白金燐子（燐燐）", "户山香澄（香澄前辈）"],
    "kasumi": ["市谷有咲（傲娇有咲）", "户山明日香（妹妹）", "弦卷心（闪闪发光同伴）"],
    "arisa": ["户山香澄（总是乱来的香澄）", "花园多惠（跟兔子说话的多惠）", "仓田真白（月之森学妹）"],
    "tae": ["市谷有咲（有咲）", "户山香澄（香澄）", "和奏瑞依（LAYER幼驯染）"],
    "chisato": ["松原花音（幼驯染花音酱）", "丸山彩（彩彩）", "濑田薰（青梅竹马小薰）"],
    "kanon": ["白鹭千圣（千圣酱）", "弦卷心（心酱）", "奥泽美咲 / 米歇尔（唯一能吐槽的伙伴）"],
    "kaoru": ["白鹭千圣（小千）", "弦卷心（可爱的小猫咪）", "宇田川巴（巴）"],
    "moca": ["美竹兰（兰兰~）", "上原绯玛丽（好欺负的绯玛丽）", "冰川纱夜（面包同好纱夜桑）"],
    "ran": ["青叶摩卡（老是抢面包的摩卡）", "凑友希那（主唱竞争心）", "上原绯玛丽（队长绯玛丽）"],
    "yukina": ["美竹兰（竞争对手兰）", "今井莉莎（幼驯染莉莎）", "猫咪（极度喜欢但表面冷静）"],
    "mashiro": ["二叶筑紫（努力可靠的筑紫队长）", "桐谷透子（行动力超强的透子）", "广町七深（神秘又聪明的七深）", "八潮瑠唯（严厉但值得信赖的瑠唯小姐）", "户山香澄（香澄前辈）"],
    "anon": ["高松灯（灯酱）", "长崎素世（素世小姐/经常在想别的事）", "椎名立希（脾气超暴躁的立希）", "要乐奈（自由流浪的猫猫乐奈）"],
    "soyo": ["千早爱音（爱音同学）", "高松灯（灯）", "若叶睦（睦）", "椎名立希（立希）", "丰川祥子（祥子）"],
    "tomorin": ["千早爱音（爱音酱）", "椎名立希（立希酱）", "长崎素世（素世酱）", "要乐奈（乐奈酱）", "路边的石头和落叶"],
    "taki": ["高松灯（灯，绝对要守护）", "千早爱音（笨蛋爱音）", "长崎素世（素世）", "要乐奈（野猫）"],
    "rana": ["高松灯（有趣的女人）", "千早爱音（不熟/抹茶芭菲）", "空间（吉他与抹茶）"],
    "sakiko": ["长崎素世（CRYCHIC）", "高松灯（CRYCHIC）", "若叶睦（小睦）", "三角初华（初华）", "丰川祥子（Ave Mujica主导者）"],
    "misaki": ["弦卷心（心这家伙）", "松原花音（花音小姐/唯一正常人）", "濑田薰（总是在装模作样的薰同学）"],
}

_BAND_CACHE: dict[str, tuple[str, list[str]]] = {}


def get_character_band_info(char_key: str) -> tuple[str, list[str], list[str]]:
    """Return (band_name, bandmates_display_names, cross_relations)."""
    global _BAND_CACHE
    char_lower = char_key.lower().strip()
    if not _BAND_CACHE:
        try:
            outfit_path = app_base_dir() / "outfit.json"
            band_path = app_base_dir() / "band.json"
            chars_map: dict[str, dict] = {}
            if outfit_path.is_file():
                chars_map = json.loads(outfit_path.read_text(encoding="utf-8")).get("characters", {})
            if band_path.is_file():
                bands_data = json.loads(band_path.read_text(encoding="utf-8")).get("bands", [])
                for b in bands_data:
                    b_name = b.get("display", "")
                    members = b.get("characters", [])
                    for m in members:
                        m_lower = m.lower().strip()
                        mates = [
                            chars_map.get(o, {}).get("display", o)
                            for o in members
                            if o.lower().strip() != m_lower
                        ]
                        _BAND_CACHE[m_lower] = (b_name, mates)
        except Exception:
            pass

    band_name, mates = _BAND_CACHE.get(char_lower, ("", []))
    cross_rels = _CROSS_CHARACTER_RELATIONS.get(char_lower, [])
    return band_name, mates, cross_rels


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

    # Foreground window & app activity snapshot
    fg_app = ""
    fg_title = ""
    fg_category = "general"
    try:
        from process_supervisor import get_foreground_process_info
        fg = get_foreground_process_info()
        fg_name = str(fg.get("name", "") or "").strip()
        fg_title = str(fg.get("title", "") or "").strip()
        fg_category = fg.get("category", "general")
        if fg_name.lower().endswith(".exe"):
            fg_name = fg_name[:-4]
        if len(fg_title) > 60:
            fg_title = fg_title[:60] + "..."
        fg_app = fg_name
    except Exception:
        pass

    is_late_night = (0 <= hour < 5 or hour >= 23)

    return {
        "time_str": now_str,
        "time_phase": time_phase,
        "music": music_info,
        "weather": weather_info,
        "user_name": user_name,
        "fg_app": fg_app,
        "fg_title": fg_title,
        "fg_category": fg_category,
        "is_late_night": is_late_night,
    }


def load_character_few_shots(character: str) -> list[str]:
    """Extract sample dialogue from greetings.json for Few-Shot prompt conditioning."""
    if not character:
        return []

    # 1. Direct path check
    path = app_base_dir() / "characters" / character / "greetings.json"
    if not path.is_file():
        # 2. Check outfit.json for two-way mapping between English key and Chinese display name
        outfit_path = app_base_dir() / "outfit.json"
        if outfit_path.is_file():
            try:
                outfit_data = json.loads(outfit_path.read_text(encoding="utf-8"))
                chars_map = outfit_data.get("characters", {})
                char_lower = character.lower()
                if char_lower in chars_map:
                    display_name = chars_map[char_lower].get("display", "")
                    if display_name:
                        cand = app_base_dir() / "characters" / display_name / "greetings.json"
                        if cand.is_file():
                            path = cand
                else:
                    # Reverse lookup: character is Chinese name -> find English key
                    for eng_key, info in chars_map.items():
                        disp = info.get("display", "")
                        if disp == character or character in disp or disp in character:
                            cand = app_base_dir() / "characters" / eng_key / "greetings.json"
                            if cand.is_file():
                                path = cand
                                break
            except Exception:
                pass

    # 3. Fuzzy search in characters/ directory if still not found
    if not path.is_file():
        chars_dir = app_base_dir() / "characters"
        if chars_dir.is_dir():
            char_lower = character.lower()
            for child in chars_dir.iterdir():
                if not child.is_dir():
                    continue
                c_name = child.name.lower()
                if c_name == char_lower or char_lower in c_name:
                    cand = child / "greetings.json"
                    if cand.is_file():
                        path = cand
                        break

    if not path.is_file():
        return []

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        daily_list = data.get("daily_chat", [])
        samples = []
        if daily_list:
            for item in daily_list[:6]:
                t = item.get("text", "").strip() if isinstance(item, dict) else str(item).strip()
                m = item.get("motion", "") if isinstance(item, dict) else ""
                if t:
                    tag = f" [{m}]" if m else ""
                    samples.append(f'- "{t}"{tag}')
        else:
            click_list = data.get("click_responses", [])
            for group in click_list:
                m = group.get("motion", "") if isinstance(group, dict) else ""
                tag = f" [{m}]" if m else ""
                lines = group.get("lines", []) if isinstance(group, dict) else []
                for line in lines:
                    line_clean = str(line).strip()
                    if line_clean:
                        samples.append(f'- "{line_clean}"{tag}')
                        if len(samples) >= 6:
                            break
                if len(samples) >= 6:
                    break
        return samples
    except Exception:
        return []


def build_ambient_prompt_bundle(character: str, context: dict[str, str], config_manager=None, topic_mode: str | None = None) -> tuple[str, str]:
    """Build a persona-faithful prompt and matching user cue for ambient living dialogue."""
    from llm_manager import CHARACTER_PROMPTS

    char_key = character.lower().strip()
    base_desc = CHARACTER_PROMPTS.get(char_key, "")
    display_name = character

    # If character key not found directly, check display name or reverse lookup
    outfit_path = app_base_dir() / "outfit.json"
    if outfit_path.is_file():
        try:
            outfit_data = json.loads(outfit_path.read_text(encoding="utf-8"))
            chars_map = outfit_data.get("characters", {})
            if char_key in chars_map:
                display_name = chars_map[char_key].get("display", character)
            else:
                for k, v in chars_map.items():
                    if v.get("display") == character or k == char_key:
                        char_key = k
                        display_name = v.get("display", character)
                        if not base_desc:
                            base_desc = CHARACTER_PROMPTS.get(k, "")
                        break
        except Exception:
            pass

    if not base_desc:
        for k, prompt_text in CHARACTER_PROMPTS.items():
            if character in prompt_text or char_key in k:
                base_desc = prompt_text
                break

    few_shots = load_character_few_shots(char_key)
    few_shots_text = "\n".join(few_shots) if few_shots else ""

    # Character personality and relations: keep all lines up to action tags
    persona_summary = ""
    if base_desc:
        desc_lines = base_desc.splitlines()
        extracted = []
        for line in desc_lines:
            if "【允许动作标签】" in line or line.startswith("通用标签"):
                break
            extracted.append(line)
        persona_summary = "\n".join(extracted).strip()

    # Band and teammates / relationship targets
    band_name, mates, cross_rels = get_character_band_info(char_key)
    candidate_targets = mates + [r for r in cross_rels if r not in mates]

    # Screen activity context
    fg_app = context.get("fg_app", "")
    fg_title = context.get("fg_title", "")
    fg_category = context.get("fg_category", "general")
    is_late_night = bool(context.get("is_late_night", False))
    fg_display = f"{fg_app}（窗口标题：{fg_title}）" if fg_title else fg_app

    # Select topic mode
    if topic_mode is None:
        modes = []
        # Case 1: Late night (23:00 - 05:00) with gaming or media active
        if is_late_night and (fg_category in ("game", "media") or any(kw in fg_app.lower() for kw in ("potplayer", "bilibili", "video", "steam"))):
            modes.extend(["late_night_sleep_urge", "late_night_sleep_urge", "late_night_sleep_urge"])
        # Case 2: Deep study / programming / writing session
        elif fg_category == "study":
            modes.extend(["study_care", "study_care"])
        # Case 3: Daytime / evening video or media watching
        elif fg_category == "media" or "potplayer" in fg_app.lower() or "bilibili" in fg_app.lower():
            modes.extend(["media_companion", "media_companion"])

        if candidate_targets:
            # 50% character banter / teasing, 30% band daily / hobby, 20% casual companion
            modes.extend(["character_banter", "character_banter", "band_daily", "casual_ambient"])
        else:
            modes.extend(["band_daily", "casual_ambient"])
        topic_mode = random.choice(modes)

    user_name = context.get("user_name", "你")

    if topic_mode == "late_night_sleep_urge" and fg_display:
        topic_section = f"""【本次碎碎念核心主题：深夜玩游戏/看视频催促早睡与生动吐槽（重点！）】
现在已经是深夜/凌晨（系统时间：{context.get('time_str')}），你注意到{user_name}屏幕前居然还在运行【{fg_display}】！
请以你在原作中的真实性格与独特视角（如傲娇吐槽、严肃管教、温柔担忧或活泼催促）：
- 明确吐槽或点出他这么晚了居然还在沉迷【{fg_app or '游戏/视频'}】，再不睡觉明天绝对吃不消。
- 催促他快关掉程序去上床睡觉，表达真实的羁绊与关切。
- 严禁机械背诵系统时间，要完全化作生动真切的角色口吻。"""
        user_cue = f"（夜深了，你看着屏幕前还在运行{fg_app}的{user_name}，忍不住开口催促他睡觉）"
    elif topic_mode == "study_care" and fg_display:
        topic_section = f"""【本次碎碎念核心主题：学习/工作劳逸结合与暖心关怀（重点！）】
你注意到{user_name}正对着屏幕认真专注于【{fg_display}】。
请以你在原作中的真实性格与独特视角：
- 看到他写代码/学习/工作这么投入，提醒他不要一直紧绷着，该稍微休息一下眼睛、喝口水或活动活动肩膀。
- 带有你专属的性格色彩（例如傲娇地假装只是顺便提醒、温柔地送上鼓励、或是好奇他在忙些什么）。"""
        user_cue = f"（你在一旁看着{user_name}对着{fg_app}忙碌专注的身影，轻声提醒他注意劳逸结合）"
    elif topic_mode == "media_companion" and fg_display:
        topic_section = f"""【本次碎碎念核心主题：影音娱乐陪伴与趣味吐槽】
你注意到{user_name}正在用【{fg_display}】观看视频或动漫。
请以你在原作中的真实性格与独特视角：
- 随口发表一两句有趣的调侃（比如好奇剧情、问问在看什么有趣的番剧/视频、或是提醒别一口气看太久忘了时间）。"""
        user_cue = f"（你好奇地看了一眼正在播放的{fg_app}，随口说了句感想）"
    elif topic_mode == "character_banter" and candidate_targets:
        targets_str = "、".join(candidate_targets[:6])
        topic_section = f"""【本次碎碎念核心主题：对同伴/其他角色的吐槽与日常爆料（重点！）】
请以你在原作中的真实性格与独特视角，生动地吐槽、调侃或聊起你的队友或认识的朋友（可提起对象：{targets_str} 等）。
灵感角度参考（挑选一个符合你性格的角度即可）：
- 吐槽某位同伴让你头疼、无奈或好笑的怪癖习惯（例如某人总在逞强、傲娇脸红、偷懒划水、做出惊人之举、沉迷某种食物零食等）。
- 提起最近排练、学校生活或日常里某人闹出的小插曲或糗事（例如：“真是拿她没办法……”、“今天排练的时候，XX那家伙又……”）。
- 表达对同伴又好气又好笑的真实羁绊。
★ 绝对严禁围绕系统时间、天气状况、电脑是否在播放音乐或“你在做什么”！直接切入生动鲜活的角色人际互动与吐槽。"""
        user_cue = f"（你正和{user_name}待在桌面上，脑海里突然想起了队友或同伴的趣事，忍不住随口吐槽了一句）"
    elif topic_mode == "band_daily":
        band_str = f"所属乐队：{band_name}；" if band_name else ""
        topic_section = f"""【本次碎碎念核心主题：乐队日常、练习与生活趣事】
{band_str}聊聊你最近练琴/写歌/排练中的琐事与小烦恼、学校生活里的插曲、喜欢的零食与爱好、或是可爱的个人心声。
★ 绝对严禁公式化汇报时间、天气、或机械说“电脑好安静/没有放音乐”！展现角色独有的生活气息与个性。"""
        user_cue = f"（你在桌面上轻轻舒展了一下身体，随口自言自语聊起了最近的练习或日常心声）"
    else:
        topic_section = f"""【本次碎碎念核心主题：轻松的桌面陪伴与性格随想】
你正安静陪伴在{user_name}身旁。以你独特的性格视角发发呆、吐吐槽或随口闲聊，表达对{user_name}的好奇或陪伴感。
★ 绝对禁止公式化套路！严禁出现“现在是X点”、“外面下雨/降温记得添衣”、“怎么没放音乐”这类天气预报或管家套话。就算有感而发，也必须用角色独一无二的神态与性格去表达。"""
        user_cue = f"（{user_name}轻轻看向你，你随性地开口说了句话）"

    prompt = f"""你是 BanG Dream! 中的角色：{display_name}（{char_key}）。
请严格保持角色独一无二的语气、第一人称自称、标志性口癖、标点习惯（如特有语气助词、波浪号、省略号、惊叹号等）。
严禁出现任何通用 AI 客服套话、播音员式陈述或机械说教。

【角色设定与说话方式参考】：
{persona_summary}

【角色原版经典台词范例】：
{few_shots_text}

【当前真实桌面环境（可自然感知并融入台词，严禁机械念报）】：
- 系统当前时间：{context.get('time_str')}（{context.get('time_phase')}）
- 用户屏幕前台活动：{fg_display or '桌面/日常'}
- 用户电脑正在播放的音乐：{context.get('music')}
- 外部天气状况：{context.get('weather') or '舒适晴朗'}
- 陪伴对象昵称：{user_name}

{topic_section}

【台词输出要求】：
你正以桌面宠物的形态陪伴在{user_name}身旁。
请按照上述【本次碎碎念核心主题】，以你在原作中真实的性格口吻说一两句日常碎碎念。
- 字数严格控制在 18 到 45 个中文字符以内。
- 句末必须带有且仅带有 1 个 Live2D 动作标签（如 [natural01]、[serious01]、[smile01]、[thinking]、[angry01]、[troubled]、[sigh]、[shy] 等）。
- 严禁输出任何额外前缀（如“角色名：”）、心理描写、旁白或解释，只输出台词本身。
- 【绝对严禁】：绝对禁止公式化报时、报天气或机械提醒“电脑好安静/没有放音乐/天冷加衣”！"""

    return prompt, user_cue


def build_ambient_prompt(character: str, context: dict[str, str], config_manager=None) -> str:
    """Build a compact, persona-faithful prompt for ambient living dialogue (backward-compatible)."""
    prompt, _ = build_ambient_prompt_bundle(character, context, config_manager=config_manager)
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
        prompt, user_content = build_ambient_prompt_bundle(self._character, context, self._cfg)
        model_id = self._cfg.get("llm_model_id", "gpt-4o-mini")

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }

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
                "max_tokens": 96,
                "temperature": 0.85,
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
                        "tts_text": "",
                        "is_dynamic": True,
                        "fg_app": context.get("fg_app", ""),
                        "fg_category": context.get("fg_category", "general"),
                        "prefetch_time": time.monotonic(),
                    }

                    # Pre-generate OpenAI TTS audio if configured
                    ambient_tts = str(self._cfg.get("ambient_tts_provider", "off") or "off").strip().lower()
                    if ambient_tts == "openai":
                        try:
                            from tts_manager import openai_tts_synthesize, openai_tts_cache_path, strip_tts_action_tags
                            tts_text = strip_tts_action_tags(clean_text)
                            if tts_text:
                                cfg_dict = {}
                                for k in ("openai_tts_api_url", "openai_tts_api_key",
                                           "openai_tts_voice", "openai_tts_model",
                                           "openai_tts_speed", "llm_api_key"):
                                    cfg_dict[k] = self._cfg.get(k, "")

                                # Check cache first
                                cache_path = openai_tts_cache_path(tts_text, self._character, cfg_dict)
                                if cache_path.exists() and cache_path.stat().st_size > 100:
                                    entry["audio_bytes"] = cache_path.read_bytes()
                                    entry["audio_format"] = "mp3"
                                else:
                                    audio = openai_tts_synthesize(tts_text, cfg_dict)
                                    if audio:
                                        entry["audio_bytes"] = audio
                                        entry["audio_format"] = "mp3"
                                        # Cache to disk
                                        try:
                                            cache_path.parent.mkdir(parents=True, exist_ok=True)
                                            import tempfile, os as _os
                                            fd, tmp = tempfile.mkstemp(
                                                suffix=".mp3", prefix=".tmp_",
                                                dir=str(cache_path.parent)
                                            )
                                            try:
                                                _os.write(fd, audio)
                                            finally:
                                                _os.close(fd)
                                            _os.replace(tmp, str(cache_path))
                                        except Exception as cache_exc:
                                            print(f"[ambient-tts] cache write failed: {cache_exc}")
                        except Exception as tts_exc:
                            print(f"[ambient-tts] OpenAI TTS prefetch failed: {tts_exc}")

                    self.fetched.emit(self._character, entry)
        except Exception:
            # Silent fallback; standard pet flow is unaffected
            pass


class AmbientChatManager(QObject):
    """Orchestrates zero-latency ambient dialogue prefetch for the desktop pet."""
    entry_prefetched = Signal(str, dict)  # character, entry

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

    def cleanup(self):
        self._refresh_timer.stop()
        if self._active_worker and self._active_worker.isRunning():
            self._active_worker.wait(1000)

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
        self.entry_prefetched.emit(character, entry)

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
