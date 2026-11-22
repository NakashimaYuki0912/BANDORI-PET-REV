from __future__ import annotations

import sys
import time
from typing import Any

import psutil
from PySide6.QtCore import QObject, QTimer, Signal

try:
    import win32gui
    import win32process
except ImportError:
    win32gui = None
    win32process = None


# --- Categorization constants ---

# Executable base names (lowercase without .exe)
GAME_PROCESSES = {
    # HoYoverse
    "genshinimpact", "yuanshen", "starrail", "bh3", "zenlesszonezero", "zzz",
    # Riot Games
    "leagueclient", "leagueclientux", "league of legends", "riotclientservices", "valorant",
    # Valve & Steam
    "csgo", "cs2", "dota2", "steam", "steamwebhelper",
    # Launchers & Platforms
    "epicgameslauncher", "battle.net", "origin", "ea", "ubisoftconnect", "uplay", "wegame",
    # Popular games
    "r5apex", "overwatch", "minecraft", "palworld", "narakabladepoint",
    "cyberpunk2077", "eldenring", "blackmythwukong", "b1", "gta5", "gta_sa",
}

STUDY_PROCESSES = {
    # IDEs & Code editors
    "code", "code - oss", "devenv", "idea", "idea64", "pycharm", "pycharm64",
    "webstorm", "webstorm64", "clion", "clion64", "goland", "goland64",
    "datagrip", "rider", "rider64", "androidstudio", "androidstudio64",
    "eclipse", "sublime_text", "notepad++", "cursor", "windsurf", "zed",
    # Office & Document tools
    "winword", "word", "excel", "powerpnt", "powerpoint", "onenote",
    "wps", "wpp", "et", "acrobat", "acrord32", "foxitreader",
    # Notes & Knowledge management
    "notion", "obsidian", "typora", "logseq", "xmind", "drawio",
    # Terminals & Shells
    "windowsterminal", "wt", "cmd", "powershell", "pwsh", "bash",
    "alacritty", "wezterm", "mintty",
    # Creative / Design / Dev tools
    "blender", "photoshop", "illustrator", "figma",
}

MEDIA_PROCESSES = {
    "bilibili", "spotify", "cloudmusic", "qqmusic", "kugou", "kuwo",
    "vlc", "potplayer", "potplayermini", "potplayermini64", "mpv",
    "foobar2000", "wmplayer", "netflix", "qiyi", "youku", "tencentvideo",
}

CHAT_PROCESSES = {
    "qq", "wechat", "weixin", "wxwork", "wework", "discord", "telegram",
    "slack", "dingtalk", "feishu", "lark", "teams", "skype", "line",
}

GAME_KEYWORDS = (
    "genshin", "原神", "starrail", "星穹铁道", "崩铁", "崩坏",
    "league of legends", "leagueclient", "英雄联盟",
    "valorant", "无畏契约", "counter-strike", "cs:go", "csgo", "cs2",
    "dota 2", "dota2", "apex legends", "r5apex", "overwatch", "守望先锋",
    "minecraft", "我的世界", "steam", "epic games", "wegame",
    "black myth", "黑神话", "cyberpunk", "elden ring", "艾尔登法环",
    "palworld", "幻兽帕鲁", "naraka", "永劫无间",
)

STUDY_KEYWORDS = (
    "visual studio", "vs code", "vscode", "pycharm", "intellij", "clion",
    "webstorm", "sublime", "notion", "obsidian", "typora", "word", "excel",
    "powerpoint", "acrobat", "pdf", "latex", "overleaf", "github", "gitlab",
    "stack overflow", "leetcode", "jupyter", "terminal", "powershell",
    "documentation", "docs",
    "文档", "论文", "课件", "笔记", "学习", "教程", "手册",
)

MEDIA_KEYWORDS = (
    "bilibili", "哔哩哔哩", "youtube", "spotify", "网易云音乐", "cloudmusic",
    "qq音乐", "qqmusic", "酷狗", "酷我", "potplayer", "vlc", "foobar2000",
    "netflix", "爱奇艺", "iqiyi", "优酷", "youku", "腾讯视频",
    "视频", "短视频", "抖音", "快手", "动漫", "剧", "追番",
)

CHAT_KEYWORDS = (
    "qq", "微信", "wechat", "企业微信", "discord", "telegram",
    "slack", "dingtalk", "钉钉", "feishu", "飞书", "teams", "skype",
)


def categorize_process(name: str, title: str) -> str:
    """Categorize a process into 'game', 'study', 'media', 'chat', or 'general'."""
    raw_name = str(name or "").strip().lower()
    if raw_name.endswith(".exe"):
        raw_name = raw_name[:-4]
    title_lower = str(title or "").strip().lower()

    # 1. Exact / well-known process names (highest priority)
    # IDEs/tools take precedence so a project named 'game.py' or 'qq_bot.py' in VS Code is still 'study'
    if raw_name in STUDY_PROCESSES:
        return "study"
    if raw_name in CHAT_PROCESSES:
        return "chat"
    if raw_name in MEDIA_PROCESSES:
        return "media"
    if raw_name in GAME_PROCESSES:
        return "game"

    # 2. Window title and process substring keywords
    # Games take priority over media/chat for title checks (e.g. YouTube playing game vs game itself)
    if any(kw in raw_name or kw in title_lower for kw in GAME_KEYWORDS):
        return "game"
    if any(kw in raw_name or kw in title_lower for kw in MEDIA_KEYWORDS):
        return "media"
    if any(kw in raw_name or kw in title_lower for kw in CHAT_KEYWORDS):
        return "chat"
    if any(kw in raw_name or kw in title_lower for kw in STUDY_KEYWORDS):
        return "study"

    return "general"


def get_foreground_process_info() -> dict[str, Any]:
    """Return info about the currently focused foreground window on Windows.

    Returns dict schema:
    {"pid": int, "name": str, "title": str, "exe": str, "category": str}
    Safely falls back on other OS, missing pywin32, permissions, or Win32 errors.
    """
    fallback: dict[str, Any] = {
        "pid": 0,
        "name": "",
        "title": "",
        "exe": "",
        "category": "general",
    }
    if sys.platform != "win32" or win32gui is None or win32process is None:
        return fallback

    try:
        hwnd = win32gui.GetForegroundWindow()
        if not hwnd:
            return fallback

        title = ""
        try:
            title = win32gui.GetWindowText(hwnd) or ""
        except Exception:
            title = ""

        pid = 0
        try:
            res = win32process.GetWindowThreadProcessId(hwnd)
            if res and len(res) >= 2:
                tid, candidate_pid = res[0], res[1]
                if tid > 0 and candidate_pid > 0:
                    pid = int(candidate_pid)
        except Exception:
            pid = 0

        if pid <= 0:
            category = categorize_process("", title)
            return {
                "pid": 0,
                "name": "",
                "title": title,
                "exe": "",
                "category": category,
            }

        name = ""
        exe = ""
        try:
            proc = psutil.Process(pid)
            name = proc.name() or ""
            try:
                exe = proc.exe() or ""
            except Exception:
                exe = ""
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
        except Exception:
            pass

        category = categorize_process(name, title)
        return {
            "pid": pid,
            "name": name,
            "title": title,
            "exe": exe,
            "category": category,
        }
    except Exception:
        return fallback


def is_process_running(target: str) -> bool:
    """Case-insensitive match against running process names, exes, or window titles."""
    if not target or not isinstance(target, str):
        return False
    target_clean = target.strip().lower()
    if not target_clean:
        return False

    # Check for media/video aliases
    if target_clean in ("视频", "刷视频", "看视频", "video", "media"):
        fg = get_foreground_process_info()
        if fg.get("category") == "media":
            return True
        fg_title = (fg.get("title") or "").lower()
        fg_name = (fg.get("name") or "").lower()
        for kw in MEDIA_KEYWORDS:
            if kw in fg_title or kw in fg_name:
                return True

    # 1. Match running processes
    try:
        for proc in psutil.process_iter(["pid", "name", "exe"]):
            try:
                p_name = (proc.info.get("name") or "").lower()
                p_exe = (proc.info.get("exe") or "").lower()

                if target_clean in p_name or target_clean in p_exe:
                    return True
                if p_name.endswith(".exe") and p_name[:-4] == target_clean:
                    return True
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
    except Exception:
        pass

    # 2. Match open window titles
    if win32gui is not None:
        try:
            matched_title = False

            def _enum_win(hwnd, _):
                nonlocal matched_title
                try:
                    if win32gui.IsWindowVisible(hwnd):
                        w_title = (win32gui.GetWindowText(hwnd) or "").lower()
                        if target_clean in w_title:
                            matched_title = True
                            return False
                except Exception:
                    pass
                return True

            win32gui.EnumWindows(_enum_win, None)
            if matched_title:
                return True
        except Exception:
            pass

    return False


def find_matching_processes(keyword: str) -> list[dict[str, Any]]:
    """Find active processes whose name, executable path, or window title contains keyword."""
    if not keyword or not isinstance(keyword, str):
        return []
    kw = keyword.strip().lower()
    if not kw:
        return []

    # Map visible window titles to process IDs
    pid_to_title: dict[int, str] = {}
    if win32gui is not None and win32process is not None:
        try:
            def _enum_win(hwnd, _):
                try:
                    if win32gui.IsWindowVisible(hwnd):
                        w_title = (win32gui.GetWindowText(hwnd) or "").strip()
                        if w_title:
                            res = win32process.GetWindowThreadProcessId(hwnd)
                            if res and len(res) >= 2 and res[1] > 0:
                                pid = int(res[1])
                                if pid not in pid_to_title:
                                    pid_to_title[pid] = w_title
                except Exception:
                    pass
                return True

            win32gui.EnumWindows(_enum_win, None)
        except Exception:
            pass

    results: list[dict[str, Any]] = []
    seen_pids = set()

    try:
        for proc in psutil.process_iter(["pid", "name", "exe"]):
            try:
                pid = proc.info.get("pid")
                if pid is None or pid in seen_pids:
                    continue
                p_name = proc.info.get("name") or ""
                p_exe = proc.info.get("exe") or ""
                p_title = pid_to_title.get(pid, "")

                name_lower = p_name.lower()
                exe_lower = p_exe.lower()
                title_lower = p_title.lower()

                if kw in name_lower or kw in exe_lower or kw in title_lower:
                    seen_pids.add(pid)
                    cat = categorize_process(p_name, p_title)
                    results.append({
                        "pid": pid,
                        "name": p_name,
                        "title": p_title,
                        "exe": p_exe,
                        "category": cat,
                    })
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
    except Exception:
        pass

    # Include any windows that matched keyword even if process_iter missed them
    for w_pid, w_title in pid_to_title.items():
        if w_pid not in seen_pids and kw in w_title.lower():
            seen_pids.add(w_pid)
            p_name = ""
            p_exe = ""
            try:
                p = psutil.Process(w_pid)
                p_name = p.name() or ""
                try:
                    p_exe = p.exe() or ""
                except Exception:
                    p_exe = ""
            except Exception:
                pass
            cat = categorize_process(p_name, w_title)
            results.append({
                "pid": w_pid,
                "name": p_name,
                "title": w_title,
                "exe": p_exe,
                "category": cat,
            })

    return results


# --- Dual property & method wrappers ---

class CallableBool(int):
    """Integer subclass behaving as bool that can also be called as a zero-arg function."""

    def __new__(cls, val: Any) -> CallableBool:
        return super().__new__(cls, 1 if bool(val) else 0)

    def __call__(self) -> bool:
        return bool(self)


class CallableFloat(float):
    """Float subclass that can also be called as a zero-arg function."""

    def __call__(self) -> float:
        return float(self)


class CallableStr(str):
    """String subclass that can also be called as a zero-arg function."""

    def __call__(self) -> str:
        return str(self)


# --- ProcessWatcher Engine ---

class ProcessWatcher(QObject):
    """Non-blocking process & window supervision engine powered by PySide6 QTimer."""

    overtime_detected = Signal(dict, float)
    distraction_detected = Signal(dict, list)
    focus_completed = Signal(float)
    watch_tick = Signal(float, float)

    MODE_IDLE = "idle"
    MODE_OVERTIME = "overtime"
    MODE_FOCUS = "focus"

    def __init__(self, parent: QObject | None = None, check_interval_ms: int = 2000):
        super().__init__(parent)
        self._check_interval_ms = max(100, int(check_interval_ms))
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_tick)

        self._mode = self.MODE_IDLE
        self._target = ""
        self._duration_seconds = 0.0
        self._start_time = 0.0
        self._allowed_keywords: list[str] = []
        self._grace_period_seconds = 10.0
        self._distraction_start_time: float | None = None
        self._distraction_alerted = False
        self._last_overtime_alert_time: float = 0.0
        self._overtime_cooldown_seconds: float = 60.0

    @property
    def is_active(self) -> CallableBool:
        return CallableBool(self._mode != self.MODE_IDLE and self._timer.isActive())

    @property
    def remaining_seconds(self) -> CallableFloat:
        if self._mode == self.MODE_IDLE or self._start_time <= 0:
            return CallableFloat(0.0)
        elapsed = time.time() - self._start_time
        return CallableFloat(max(0.0, self._duration_seconds - elapsed))

    @property
    def current_mode(self) -> CallableStr:
        return CallableStr(self._mode)

    def start_overtime_watch(self, target: str, duration_seconds: float) -> None:
        """Count down duration_seconds. When timer expires, checks if target is still running.

        If target is running or in foreground, emits overtime_detected periodically until closed.
        """
        self.cancel()
        self._mode = self.MODE_OVERTIME
        self._target = str(target or "").strip()
        self._duration_seconds = max(0.0, float(duration_seconds))
        self._start_time = time.time()
        self._last_overtime_alert_time = 0.0
        self._timer.start(self._check_interval_ms)
        self.watch_tick.emit(self._duration_seconds, self._duration_seconds)

    def start_focus_watch(
        self,
        allowed_keywords: list[str],
        duration_seconds: float,
        grace_period_seconds: float = 10.0,
    ) -> None:
        """Watch foreground window during focus session.

        If user leaves allowed apps into a distracting category for longer than grace_period_seconds,
        emits distraction_detected. If duration finishes cleanly, emits focus_completed.
        """
        self.cancel()
        self._mode = self.MODE_FOCUS
        self._allowed_keywords = [str(k).strip() for k in allowed_keywords if str(k).strip()]
        self._duration_seconds = max(0.0, float(duration_seconds))
        self._grace_period_seconds = max(0.0, float(grace_period_seconds))
        self._start_time = time.time()
        self._distraction_start_time = None
        self._distraction_alerted = False
        self._timer.start(self._check_interval_ms)
        self.watch_tick.emit(self._duration_seconds, self._duration_seconds)

    def cancel(self) -> None:
        """Stop watcher timer and reset all supervision states."""
        if self._timer.isActive():
            self._timer.stop()
        self._mode = self.MODE_IDLE
        self._target = ""
        self._duration_seconds = 0.0
        self._start_time = 0.0
        self._allowed_keywords = []
        self._grace_period_seconds = 10.0
        self._distraction_start_time = None
        self._distraction_alerted = False
        self._last_overtime_alert_time = 0.0

    def tick(self) -> None:
        """Execute a single manual tick (useful for test step simulation)."""
        self._on_tick()

    def _on_tick(self) -> None:
        if self._mode == self.MODE_OVERTIME:
            self._handle_overtime_tick()
        elif self._mode == self.MODE_FOCUS:
            self._handle_focus_tick()

    def _handle_overtime_tick(self) -> None:
        now = time.time()
        elapsed = now - self._start_time
        remaining = max(0.0, self._duration_seconds - elapsed)
        self.watch_tick.emit(remaining, self._duration_seconds)

        if elapsed >= self._duration_seconds:
            # Overtime check
            fg_info = get_foreground_process_info()
            is_fg = self._is_target_match(self._target, fg_info)
            is_running = is_fg or is_process_running(self._target)

            if is_running:
                if self._last_overtime_alert_time <= 0 or (now - self._last_overtime_alert_time >= self._overtime_cooldown_seconds):
                    self._last_overtime_alert_time = now
                    if is_fg:
                        info = fg_info
                    else:
                        matches = find_matching_processes(self._target)
                        info = matches[0] if matches else {
                            "pid": 0,
                            "name": self._target,
                            "title": "",
                            "exe": "",
                            "category": categorize_process(self._target, ""),
                        }
                    self.overtime_detected.emit(info, elapsed)
            else:
                # Target process has closed
                self.cancel()

    def _handle_focus_tick(self) -> None:
        now = time.time()
        elapsed = now - self._start_time
        remaining = max(0.0, self._duration_seconds - elapsed)
        self.watch_tick.emit(remaining, self._duration_seconds)

        if elapsed >= self._duration_seconds:
            self.focus_completed.emit(self._duration_seconds)
            self.cancel()
            return

        fg_info = get_foreground_process_info()
        is_allowed = self._is_allowed_process(fg_info, self._allowed_keywords)

        if is_allowed:
            self._distraction_start_time = None
            self._distraction_alerted = False
        else:
            cat = fg_info.get("category", "general")
            # Distracting categories: game, media, chat
            if cat in {"game", "media", "chat"}:
                if self._distraction_start_time is None:
                    self._distraction_start_time = now
                else:
                    distraction_elapsed = now - self._distraction_start_time
                    if distraction_elapsed >= self._grace_period_seconds:
                        if not self._distraction_alerted:
                            self.distraction_detected.emit(fg_info, list(self._allowed_keywords))
                            self._distraction_alerted = True
            else:
                # Neutral / general windows
                self._distraction_start_time = None
                self._distraction_alerted = False

    def _is_target_match(self, target: str, proc_info: dict[str, Any]) -> bool:
        if not target or not proc_info:
            return False
        t = target.strip().lower()
        if not t:
            return False
        name = (proc_info.get("name") or "").lower()
        title = (proc_info.get("title") or "").lower()
        exe = (proc_info.get("exe") or "").lower()

        if t in name or t in title or t in exe:
            return True
        if name.endswith(".exe") and name[:-4] == t:
            return True
        return False

    def _is_allowed_process(self, proc_info: dict[str, Any], allowed_keywords: list[str]) -> bool:
        if not proc_info:
            return True
        # If window is blank/desktop with no process name or title, do not flag as distraction
        if not proc_info.get("name") and not proc_info.get("title"):
            return True

        cat = (proc_info.get("category") or "").lower()
        name = (proc_info.get("name") or "").lower()
        title = (proc_info.get("title") or "").lower()
        exe = (proc_info.get("exe") or "").lower()

        for kw in allowed_keywords:
            k = kw.strip().lower()
            if not k:
                continue
            if k == cat:
                return True
            if k in name or k in title or k in exe:
                return True
            if name.endswith(".exe") and name[:-4] == k:
                return True
        return False
