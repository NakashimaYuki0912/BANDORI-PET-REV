"""Todo & Focus Supervision Manager for BandoriPet.

Brings together:
1. `process_supervisor.ProcessWatcher`: process & foreground window monitoring.
2. `todo_character_prompts`: persona-rich speech alerts with Live2D action tags.
3. Natural language & slash-command parsing for the compact capsule and chat window.
4. Seamless integration with PetWindow for speech bubble, Live2D actions, and TTS voice alerts.
"""

from __future__ import annotations

import re
from typing import Any
from PySide6.QtCore import QObject, Signal

from process_supervisor import ProcessWatcher, get_foreground_process_info
from todo_character_prompts import (
    generate_distraction_alert,
    generate_focus_completed_praise,
    generate_overtime_alert,
    normalize_character,
)


_CN_NUM = {
    "零": 0, "一": 1, "二": 2, "两": 2, "俩": 2, "三": 3, "四": 4,
    "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
}


def parse_cn_number(text: str) -> float | None:
    """Parse a simple Chinese number (1-99, e.g. 三十, 四十五, 十五, 二) into float."""
    s = text.strip()
    if not s:
        return None
    if s == "十":
        return 10.0
    if s.startswith("十"):
        sub = s[1:]
        return 10.0 + float(_CN_NUM.get(sub, 0))
    if "十" in s:
        parts = s.split("十", 1)
        tens = _CN_NUM.get(parts[0], 1) * 10
        units = _CN_NUM.get(parts[1], 0) if parts[1] else 0
        return float(tens + units)
    if s in _CN_NUM:
        return float(_CN_NUM[s])
    return None


def extract_duration_minutes(text: str) -> float | None:
    """Extract duration in minutes from natural language or commands.

    Examples:
    - '我要打游戏三十分钟了' -> 30.0
    - '打半小时游戏' -> 30.0
    - '写代码1小时' -> 60.0
    - '专注四十五分钟' -> 45.0
    - '玩2个半小时' -> 150.0
    - '两小时' -> 120.0
    - '45m', '30min', '15分' -> 45.0, 30.0, 15.0
    - '一刻钟' -> 15.0
    """
    s = text.strip().lower()

    # Special compound cases
    if re.search(r"(?:两|2)(?:个)?半小时", s):
        return 150.0
    if re.search(r"(?:一|1)(?:个)?半小时", s):
        return 90.0
    if re.search(r"半(?:个)?(?:小时|钟头|钟)", s):
        return 30.0
    if re.search(r"一刻钟", s):
        return 15.0

    # Hours matching: 1.5小时, 2小时, 两小时, 一个小时
    m_hr_digits = re.search(r"(\d+(?:\.\d+)?)\s*(?:个)?(?:小时|钟头|hrs?\b|h\b)", s)
    if m_hr_digits:
        return float(m_hr_digits.group(1)) * 60.0

    m_hr_cn = re.search(r"([一二两三四五六七八九十]+)\s*(?:个)?(?:小时|钟头)", s)
    if m_hr_cn:
        val = parse_cn_number(m_hr_cn.group(1))
        if val is not None:
            return val * 60.0

    # Minutes matching: 30分钟, 30m, 45分, 三十分钟, 四十五分
    m_min_digits = re.search(r"(\d+(?:\.\d+)?)\s*(?:分钟|分|mins?\b|m\b)", s)
    if m_min_digits:
        return float(m_min_digits.group(1))

    m_min_cn = re.search(r"([一二两三四五六七八九十]+)\s*(?:分钟|分)", s)
    if m_min_cn:
        val = parse_cn_number(m_min_cn.group(1))
        if val is not None:
            return val

    # Standalone slash argument like /game 30 or /study 45 or /todo overtime 10 or /todo 30
    m_standalone = re.search(
        r"(?:/(?:game|study|focus|play|游戏|学习|专注)|/todo(?:\s+(?:overtime|focus|game|study|play|游戏|学习|专注))?)\s+(\d+(?:\.\d+)?)\b",
        s,
    )
    if m_standalone:
        return float(m_standalone.group(1))

    return None


def parse_todo_tag(text: str) -> tuple[str, float, str] | None:
    """Parse [TODO_OVERTIME:10:刷视频] or [TODO_FOCUS:45:学习] or [TODO_CANCEL] from text."""
    m = re.search(r"\[TODO_(OVERTIME|FOCUS|CANCEL)(?::(\d+(?:\.\d+)?))?(?::([^\]]+))?\]", text)
    if not m:
        return None
    mode = m.group(1).lower()
    mins = float(m.group(2)) if m.group(2) else (30.0 if mode == "overtime" else 45.0)
    task = m.group(3) or ("游戏" if mode == "overtime" else "学习")
    return mode, mins, task


def strip_todo_tags(text: str) -> str:
    """Remove [TODO_...] tags from assistant reply before display or TTS."""
    return re.sub(r"\[TODO_[^\]]+\]", "", text).strip()


def get_game_confirmation(character: str, task_name: str, mins: float) -> tuple[str, list[str]]:
    char = normalize_character(character)
    display_task = task_name or "游戏"
    is_video = any(kw in display_task for kw in ("视频", "b站", "bilibili", "动漫", "剧", "抖音", "快手", "油管"))

    if char == "arisa":
        if is_video:
            return f"哼，计时{mins:.0f}分钟！响了就把视频关掉，别顺手又点开下一条，不然我可直接拔电源！[angry01]", ["angry01"]
        return f"哼，计时{mins:.0f}分钟对吧？到点要是还没退出【{display_task}】，可别怪我直接拔电源！[angry01]", ["angry01"]
    elif char == "yukina":
        if is_video:
            return f"【{display_task}】时间设定：{mins:.0f}分钟。到点必须立刻停止播放，听明白了吗？[serious01]", ["serious01"]
        return f"已设定【{display_task}】监督：{mins:.0f}分钟。到时如果还没放下，可别怪我严厉。[serious01]", ["serious01"]
    elif char == "tomorin":
        if is_video:
            return f"好的……{mins:.0f}分钟后如果你还在看视频，我会提醒你的……要注意保护眼睛哦。[smile01]", ["smile01"]
        return f"好的……{mins:.0f}分钟的【{display_task}】时间。约定好了，到时间一定要注意休息哦……[smile01]", ["smile01"]
    elif char == "anon":
        if is_video:
            return f"收到！爱音专属防沉迷计时器启动：{mins:.0f}分钟！看视频超时可是会被我疯狂弹窗吐槽的哦！[wink]", ["wink"]
        return f"收到！爱音专属计时器启动：{mins:.0f}分钟！超时的话我可会在旁边大声提醒你的哦！[wink]", ["wink"]
    elif char == "soyo":
        return f"好的，那就约好{mins:.0f}分钟哦。要好好遵守我们的约定呢。[smile01]", ["smile01"]
    elif char == "taki":
        if is_video:
            return f"计时{mins:.0f}分钟。一到时间就把视频关了，别让我催第二遍。[serious01]", ["serious01"]
        return f"计时{mins:.0f}分钟。时间一到立刻停下【{display_task}】，别让我催你第二遍。[serious01]", ["serious01"]
    elif char == "rana":
        return f"{mins:.0f}分钟，记住了。超时的话……抹茶芭菲加倍。[niya]", ["niya"]
    elif char == "moca":
        return f"收到~ {mins:.0f}分钟的摩卡特别监督。超时的话，你的面包就归我了哦~[smile01]", ["smile01"]
    elif char == "lisa":
        return f"好的好的，那就约好{mins:.0f}分钟哦！姐姐我会好好盯着你的，别想偷懒~[wink]", ["wink"]
    elif char == "sayo":
        return f"监督时间设定为{mins:.0f}分钟。必须严格遵守时间，不要有任何懈怠。[serious01]", ["serious01"]
    elif char == "hina":
        return f"噜——！{mins:.0f}分钟计时开始！等时间到了看你怎么求饶~ 鲁鲁鲁~[smile01]", ["smile01"]
    elif char == "aya":
        return f"呜哇，{mins:.0f}分钟！彩也会在旁边为你努力计时的，千万别超时呀！[shame01]", ["shame01"]
    elif char == "kokoro":
        return f"哇哈哈！{mins:.0f}分钟的大冒险！让我们充满笑容地遵守约定吧！[smile01]", ["smile01"]
    elif char == "ran":
        return f"……{mins:.0f}分钟。一如既往，到点了就自己自觉停下。[serious01]", ["serious01"]
    else:
        return f"好呀！【{display_task}】设定{mins:.0f}分钟！香澄在旁边为你加油！[smile01]", ["smile01"]


def get_focus_confirmation(character: str, task_name: str, mins: float) -> tuple[str, list[str]]:
    char = normalize_character(character)
    display_task = task_name or "学习"
    if char == "arisa":
        return f"好、好吧……{mins:.0f}分钟专心{display_task}。要是敢中途摸鱼，我可绝对会狠狠说你的！[angry01]", ["angry01"]
    elif char == "yukina":
        return f"专注模式开启：【{display_task}】{mins:.0f}分钟。展现出你的觉悟，不要让我抓到你开小差。[serious01]", ["serious01"]
    elif char == "tomorin":
        return f"专注【{display_task}】{mins:.0f}分钟……我会在这里静静陪着你，一起加油吧……[smile01]", ["smile01"]
    elif char == "anon":
        return f"很好很好！【{display_task}】{mins:.0f}分钟！爱音雷达全开，偷看其他东西可是会被当场抓包的！[jaan]", ["jaan"]
    elif char == "soyo":
        return f"开启专注模式了呢。接下来的{mins:.0f}分钟，素世会在旁边看着你认真努力的样子哦。[smile01]", ["smile01"]
    elif char == "taki":
        return f"【{display_task}】{mins:.0f}分钟，集中精神一口气做完。敢切到别的地方偷懒我就敲你桌面。[serious01]", ["serious01"]
    elif char == "rana":
        return f"{mins:.0f}分钟专注……做完了，给我好吃的。[smile01]", ["smile01"]
    elif char == "moca":
        return f"摩卡式专注法！这{mins:.0f}分钟好好加油，摸鱼的话面包会被没收哦~[smile01]", ["smile01"]
    elif char == "lisa":
        return f"专注时间{mins:.0f}分钟！累了有莉莎姐给你烤曲奇，但现在可不能偷看其他窗口哦~[wink]", ["wink"]
    elif char == "sayo":
        return f"心无杂念，全身心投入这{mins:.0f}分钟。切忌半途而废与散漫。[serious01]", ["serious01"]
    elif char == "hina":
        return f"想要一口气搞定对吧？{mins:.0f}分钟！日菜会一直好奇地盯着屏幕看哦！[smile01]", ["smile01"]
    elif char == "aya":
        return f"彩的元气应援！这{mins:.0f}分钟好好加油，要是偷懒彩可是会哭的哦！[shame01]", ["shame01"]
    elif char == "kokoro":
        return f"全世界都会为专注的你加油！这{mins:.0f}分钟全力以赴，把不可能变成可能！[smile01]", ["smile01"]
    elif char == "ran":
        return f"……{mins:.0f}分钟。不管做什么，都别三心二意，一如既往地坚持。[serious01]", ["serious01"]
    else:
        return f"闪闪发光的专注时间！【{display_task}】{mins:.0f}分钟，全力冲刺！[gattsu]", ["gattsu"]


def parse_todo_intent(text: str, character: str = "kasumi") -> dict | None:
    """Parse text into a structured todo intent dict, or None if not a todo command."""
    raw = text.strip()
    if not raw:
        return None
    lower = raw.lower()
    char = normalize_character(character)

    # 0. Direct action tag from LLM output, e.g. [TODO_OVERTIME:10:刷视频] or [TODO_FOCUS:45:学习] or [TODO_CANCEL]
    m_tag = re.search(r"\[TODO_(OVERTIME|FOCUS|CANCEL)(?::(\d+(?:\.\d+)?))?(?::([^\]]+))?\]", raw)
    if m_tag:
        tag_mode = m_tag.group(1).upper()
        if tag_mode == "CANCEL":
            return {"type": "cancel", "message": "已停止当前的监督任务。[nod]", "actions": ["nod"]}
        tag_mins = float(m_tag.group(2)) if m_tag.group(2) else (30.0 if tag_mode == "OVERTIME" else 45.0)
        tag_task = m_tag.group(3) or ("游戏" if tag_mode == "OVERTIME" else "学习")
        if tag_mode == "OVERTIME":
            msg, acts = get_game_confirmation(char, tag_task, tag_mins)
            return {"type": "game", "duration": tag_mins, "task_name": tag_task, "message": msg, "actions": acts}
        else:
            msg, acts = get_focus_confirmation(char, tag_task, tag_mins)
            return {"type": "focus", "duration": tag_mins, "task_name": tag_task, "message": msg, "actions": acts}

    # 1. Stop / Cancel
    if lower in (
        "/todo stop", "/todo cancel", "/todo 停止", "/todo 取消",
        "/game stop", "/study stop", "/focus stop", "/stop", "/cancel",
        "停止监督", "取消监督", "别监督了", "停止计时", "取消计时",
    ):
        return {
            "type": "cancel",
            "message": "已停止当前的监督任务。[nod]",
            "actions": ["nod"],
        }

    # 2. Status
    if lower in ("/todo status", "/todo", "/todo 状态", "/game status", "/study status", "监督状态", "剩余时间"):
        return {
            "type": "status",
            "message": "查询监督状态",
            "actions": ["nod"],
        }

    # 3. Entertainment & Overtime keywords (games, video, stream, social, relaxing)
    is_game_slash = bool(re.match(r"^/(?:game|play|游戏|todo\s+(?:overtime|game|play|游戏))\b", lower))
    entertainment_keywords = [
        "视频", "刷视频", "短视频", "看视频", "看剧", "追番", "看动漫", "动漫", "电影", "看电影",
        "b站", "bilibili", "哔哩哔哩", "抖音", "快手", "油管", "youtube", "tiktok", "小红书",
        "摸鱼", "刷手机", "刷网页", "看网页", "逛淘宝", "逛街", "水群", "闲逛", "发呆",
        "游戏", "手游", "端游", "steam", "原神", "崩铁", "星铁", "绝区零",
        "lol", "英雄联盟", "王者", "王者荣耀", "瓦", "瓦罗兰特", "无畏契约",
        "cs", "csgo", "cs2", "apex", "鸣潮", "方舟", "明日方舟", "开黑", "打本",
    ]
    matched_ent_kw = None
    for kw in entertainment_keywords:
        if kw in lower:
            matched_ent_kw = kw
            break

    # Overtime conditional patterns: e.g. "如果... 后我依然在... 就记得提醒我", "还在... 就叫我"
    has_overtime_condition = bool(re.search(r"(?:依然|还在|还|到点|超时).*?(?:在|看|刷|玩)?.*?(?:提醒|叫|催|说)", lower))

    # 4. Study / Focus intent
    is_study_slash = bool(re.match(r"^/(?:study|focus|学习|专注|todo\s+(?:focus|study|学习|专注))\b", lower))
    study_keywords = [
        "学习", "学一会儿", "看书", "写代码", "敲代码", "编程", "写作业", "做作业",
        "做题", "复习", "备考", "背单词", "背书", "写论文", "工作", "办公", "专注", "码字",
    ]
    has_study_kw = any(kw in lower for kw in study_keywords)

    # 5. Supervision verbs
    supervise_verbs = ["监督", "提醒", "叫我", "计时", "倒计时", "定时", "代办", "看着我"]
    has_supervise_verb = any(v in lower for v in supervise_verbs)

    dur = extract_duration_minutes(lower)

    m_slash_task = re.search(
        r"^/(?:game|play|游戏|study|focus|学习|专注|todo\s+(?:overtime|focus|game|study|play|游戏|学习|专注))\s+\d+(?:\.\d+)?(?:m|min|mins|分|分钟)?\s+([^\s]+)",
        raw,
    )
    explicit_task = m_slash_task.group(1).strip() if m_slash_task else None

    # Overtime / Entertainment Intent (handles video, game, browsing, or explicit conditional overtime)
    if is_game_slash or (matched_ent_kw is not None and (dur is not None or has_supervise_verb)) or (has_overtime_condition and dur is not None):
        mins = dur if dur is not None else 30.0
        if explicit_task:
            task_label = explicit_task
        elif matched_ent_kw and any(v in matched_ent_kw for v in ("视频", "b站", "bilibili", "抖音", "看剧", "油管")):
            task_label = "刷视频"
        elif matched_ent_kw:
            task_label = matched_ent_kw
        else:
            task_label = "摸鱼"
        msg, acts = get_game_confirmation(char, task_label, mins)
        return {
            "type": "game",
            "duration": mins,
            "task_name": task_label,
            "message": msg,
            "actions": acts,
        }

    # Study / Focus intent
    if is_study_slash or (has_study_kw and (dur is not None or has_supervise_verb)):
        mins = dur if dur is not None else 45.0
        task_label = explicit_task if explicit_task else "学习"
        msg, acts = get_focus_confirmation(char, task_label, mins)
        return {
            "type": "focus",
            "duration": mins,
            "task_name": task_label,
            "message": msg,
            "actions": acts,
        }

    # Generic supervision request with duration (e.g. "监督我30分钟", "计时20分钟", "定时半小时")
    if has_supervise_verb and dur is not None:
        mins = dur
        msg, acts = get_focus_confirmation(char, "任务", mins)
        return {
            "type": "focus",
            "duration": mins,
            "task_name": "任务",
            "message": msg,
            "actions": acts,
        }

    return None


class TodoSupervisionManager(QObject):
    """Orchestrates todo supervision, timers, process monitoring, and alert delivery."""

    # text, action_tags
    alert_ready = Signal(str, list)
    # feedback_message, action_tags (for immediate confirmation to user)
    confirmation_ready = Signal(str, list)
    # remaining_seconds, total_seconds
    tick = Signal(float, float)
    # status dict
    status_changed = Signal(dict)

    def __init__(self, character: str = "kasumi", config_manager=None, parent=None):
        super().__init__(parent)
        self._character = normalize_character(character)
        self._cfg = config_manager
        self._watcher = ProcessWatcher(self)
        self._watcher.overtime_detected.connect(self._on_overtime_detected)
        self._watcher.distraction_detected.connect(self._on_distraction_detected)
        self._watcher.focus_completed.connect(self._on_focus_completed)
        self._watcher.watch_tick.connect(self._on_watch_tick)

        self._current_task_name = ""
        self._current_duration_minutes = 0.0
        self._current_target_process = ""
        self._allowed_keywords = []

    def set_character(self, character: str):
        self._character = normalize_character(character)

    @property
    def is_active(self) -> bool:
        return self._watcher.is_active

    @property
    def current_mode(self) -> str:
        return self._watcher.current_mode

    @property
    def current_task_name(self) -> str:
        return self._current_task_name

    def get_status_info(self) -> dict:
        return {
            "active": self.is_active,
            "mode": self.current_mode,
            "task_name": self._current_task_name,
            "duration_minutes": self._current_duration_minutes,
            "remaining_seconds": self._watcher.remaining_seconds,
            "character": self._character,
        }

    # =========================================================================
    # Task Starting & Stopping
    # =========================================================================

    def start_game_supervision(
        self,
        duration_minutes: float = 30.0,
        task_name: str = "游戏",
        target_process: str = "",
    ) -> tuple[str, list[str]]:
        """Start a countdown for game/video/entertainment."""
        mins = max(0.5, float(duration_minutes))
        duration_sec = mins * 60.0
        self._current_duration_minutes = mins
        self._current_task_name = task_name or "游戏"

        if not target_process:
            fg = get_foreground_process_info()
            cat = fg.get("category")
            if cat in ("game", "media"):
                target_process = fg.get("name") or fg.get("title") or ("视频" if cat == "media" else "game")
            elif "视频" in self._current_task_name:
                target_process = "视频"
            else:
                target_process = "game"
        self._current_target_process = target_process

        self._watcher.start_overtime_watch(target_process, duration_sec)
        self.status_changed.emit(self.get_status_info())

        msg, actions = get_game_confirmation(self._character, self._current_task_name, mins)
        self.confirmation_ready.emit(msg, actions)
        return msg, actions

    def start_focus_supervision(
        self,
        duration_minutes: float = 45.0,
        task_name: str = "学习",
        allowed_keywords: list[str] | None = None,
        grace_period_seconds: float = 10.0,
    ) -> tuple[str, list[str]]:
        """Start a focus session (e.g. studying / coding)."""
        mins = max(0.5, float(duration_minutes))
        duration_sec = mins * 60.0
        self._current_duration_minutes = mins
        self._current_task_name = task_name or "学习"

        keywords = list(allowed_keywords) if allowed_keywords else []
        keywords.extend(["study", "code", "doc", "notes", "word", "pdf", "terminal", "powershell", task_name.lower()])
        self._allowed_keywords = keywords

        self._watcher.start_focus_watch(keywords, duration_sec, grace_period_seconds=grace_period_seconds)
        self.status_changed.emit(self.get_status_info())

        msg, actions = get_focus_confirmation(self._character, self._current_task_name, mins)
        self.confirmation_ready.emit(msg, actions)
        return msg, actions

    def cancel(self) -> tuple[str, list[str]]:
        """Cancel the active supervision task."""
        if not self.is_active:
            msg = "当前没有正在进行的监督任务哦。"
            self.confirmation_ready.emit(msg, [])
            return msg, []

        self._watcher.cancel()
        self.status_changed.emit(self.get_status_info())
        msg = f"已停止【{self._current_task_name}】的监督任务。[nod]"
        actions = ["nod"]
        self.confirmation_ready.emit(msg, actions)
        return msg, actions

    # =========================================================================
    # Internal Watcher Event Handlers
    # =========================================================================

    def _on_overtime_detected(self, proc_info: dict, elapsed_sec: float):
        elapsed_min = max(1, int(round(elapsed_sec / 60.0)))
        proc_name = proc_info.get("name") or proc_info.get("title") or self._current_target_process or "任务"

        spoken_text, actions = generate_overtime_alert(
            character=self._character,
            task_name=self._current_task_name,
            elapsed_minutes=elapsed_min,
            process_name=proc_name,
            llm_manager=self._cfg,
        )
        self.alert_ready.emit(spoken_text, actions)

    def _on_distraction_detected(self, distraction_info: dict, allowed_keywords: list):
        current_app = distraction_info.get("name") or distraction_info.get("title") or "其他应用"

        spoken_text, actions = generate_distraction_alert(
            character=self._character,
            planned_task=self._current_task_name,
            current_app=current_app,
            llm_manager=self._cfg,
        )
        self.alert_ready.emit(spoken_text, actions)

    def _on_focus_completed(self, total_sec: float):
        total_min = max(1, int(round(total_sec / 60.0)))

        spoken_text, actions = generate_focus_completed_praise(
            character=self._character,
            task_name=self._current_task_name,
            duration_minutes=total_min,
            llm_manager=self._cfg,
        )
        self.alert_ready.emit(spoken_text, actions)
        self.status_changed.emit(self.get_status_info())

    def _on_watch_tick(self, remaining_sec: float, total_sec: float):
        self.tick.emit(remaining_sec, total_sec)

    # =========================================================================
    # Capsule & Chat Input Parsing
    # =========================================================================

    def parse_text_input(self, text: str) -> bool:
        """Parse natural language or slash command from user input."""
        intent = parse_todo_intent(text, self._character)
        if intent is None:
            return False

        itype = intent.get("type")
        if itype == "cancel":
            self.cancel()
            return True
        elif itype == "status":
            if not self.is_active:
                self.confirmation_ready.emit("当前没有运行中的监督任务。可以使用例如 `/game 30m` 或 `/study 45m` 开启。", ["smile01"])
            else:
                rem_m = int(self._watcher.remaining_seconds // 60)
                rem_s = int(self._watcher.remaining_seconds % 60)
                info = f"当前正在监督【{self._current_task_name}】（模式：{self.current_mode}），剩余时间：{rem_m}分{rem_s}秒。"
                self.confirmation_ready.emit(info, ["nod"])
            return True
        elif itype == "game":
            self.start_game_supervision(intent["duration"], task_name=intent.get("task_name", "游戏"))
            return True
        elif itype == "focus":
            self.start_focus_supervision(intent["duration"], task_name=intent.get("task_name", "学习"))
            return True

        return False
