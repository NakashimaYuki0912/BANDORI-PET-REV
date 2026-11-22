from __future__ import annotations

import os
import sys
import time
import unittest
from unittest.mock import MagicMock, patch

from PySide6.QtCore import QCoreApplication

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import process_supervisor
from process_supervisor import (
    ProcessWatcher,
    categorize_process,
    find_matching_processes,
    get_foreground_process_info,
    is_process_running,
)


class TestProcessCategorization(unittest.TestCase):
    """Test process and window title categorization across categories."""

    def test_games_categorization(self):
        # By process name
        self.assertEqual(categorize_process("GenshinImpact.exe", ""), "game")
        self.assertEqual(categorize_process("YuanShen.exe", "原神"), "game")
        self.assertEqual(categorize_process("StarRail.exe", ""), "game")
        self.assertEqual(categorize_process("LeagueClient.exe", "League of Legends"), "game")
        self.assertEqual(categorize_process("steam.exe", "Steam"), "game")
        self.assertEqual(categorize_process("cs2.exe", "Counter-Strike 2"), "game")
        self.assertEqual(categorize_process("Overwatch.exe", ""), "game")
        self.assertEqual(categorize_process("VALORANT.exe", ""), "game")
        self.assertEqual(categorize_process("EpicGamesLauncher.exe", ""), "game")

        # By title (e.g. running in browser or launcher)
        self.assertEqual(categorize_process("chrome.exe", "原神 - 官方网站"), "game")
        self.assertEqual(categorize_process("msedge.exe", "崩坏：星穹铁道 抽卡模拟器"), "game")
        self.assertEqual(categorize_process("launcher.exe", "Minecraft 1.20.1"), "game")

    def test_study_categorization(self):
        # Code editors and IDEs
        self.assertEqual(categorize_process("Code.exe", "test.py - VS Code"), "study")
        self.assertEqual(categorize_process("devenv.exe", "Solution - Microsoft Visual Studio"), "study")
        self.assertEqual(categorize_process("idea64.exe", "Project - IntelliJ IDEA"), "study")
        self.assertEqual(categorize_process("pycharm64.exe", ""), "study")
        self.assertEqual(categorize_process("cursor.exe", ""), "study")

        # Office & documents
        self.assertEqual(categorize_process("WINWORD.EXE", "Document1 - Word"), "study")
        self.assertEqual(categorize_process("EXCEL.EXE", "Sheet1 - Excel"), "study")
        self.assertEqual(categorize_process("POWERPNT.EXE", "Presentation1"), "study")
        self.assertEqual(categorize_process("Acrobat.exe", "Paper.pdf"), "study")
        self.assertEqual(categorize_process("wps.exe", "文档1"), "study")

        # Notes & terminals
        self.assertEqual(categorize_process("notion.exe", "Notion"), "study")
        self.assertEqual(categorize_process("obsidian.exe", "Daily Notes"), "study")
        self.assertEqual(categorize_process("typora.exe", "README.md"), "study")
        self.assertEqual(categorize_process("powershell.exe", "Windows PowerShell"), "study")
        self.assertEqual(categorize_process("cmd.exe", "Command Prompt"), "study")
        self.assertEqual(categorize_process("WindowsTerminal.exe", ""), "study")

        # By title in browser
        self.assertEqual(categorize_process("chrome.exe", "GitHub - HELPMEEADICE/BANDORI-PET-REV"), "study")
        self.assertEqual(categorize_process("chrome.exe", "Python Documentation - Multiprocessing"), "study")
        self.assertEqual(categorize_process("chrome.exe", "Stack Overflow - Where Developers Learn"), "study")

    def test_media_categorization(self):
        self.assertEqual(categorize_process("bilibili.exe", "哔哩哔哩"), "media")
        self.assertEqual(categorize_process("Spotify.exe", "Spotify Free"), "media")
        self.assertEqual(categorize_process("cloudmusic.exe", "网易云音乐"), "media")
        self.assertEqual(categorize_process("qqmusic.exe", "QQ音乐"), "media")
        self.assertEqual(categorize_process("vlc.exe", "VLC media player"), "media")
        self.assertEqual(categorize_process("PotPlayer64.exe", "PotPlayer"), "media")

        # By title in browser
        self.assertEqual(categorize_process("chrome.exe", "【BanG Dream!】Ave Mujica 第1话 - 哔哩哔哩"), "media")
        self.assertEqual(categorize_process("msedge.exe", "YouTube - Live Music Stream"), "media")

    def test_chat_categorization(self):
        self.assertEqual(categorize_process("QQ.exe", "QQ"), "chat")
        self.assertEqual(categorize_process("WeChat.exe", "微信"), "chat")
        self.assertEqual(categorize_process("Discord.exe", "Discord"), "chat")
        self.assertEqual(categorize_process("Telegram.exe", "Telegram"), "chat")
        self.assertEqual(categorize_process("Slack.exe", "Slack"), "chat")
        self.assertEqual(categorize_process("DingTalk.exe", "钉钉"), "chat")
        self.assertEqual(categorize_process("Feishu.exe", "飞书"), "chat")

    def test_general_categorization(self):
        self.assertEqual(categorize_process("explorer.exe", "Downloads"), "general")
        self.assertEqual(categorize_process("notepad.exe", "Untitled - Notepad"), "general")
        self.assertEqual(categorize_process("calc.exe", "Calculator"), "general")
        self.assertEqual(categorize_process("", ""), "general")

    def test_study_priority_over_title_keywords(self):
        # A file named 'game.py' or 'qq_bot.py' in VS Code must remain 'study'
        self.assertEqual(categorize_process("Code.exe", "game.py - BANDORI-PET-REV - Visual Studio Code"), "study")
        self.assertEqual(categorize_process("idea64.exe", "qq_bot.kt - IntelliJ IDEA"), "study")


class TestForegroundDetection(unittest.TestCase):
    """Test get_foreground_process_info with mocked Win32 & psutil calls."""

    @patch("process_supervisor.win32gui")
    @patch("process_supervisor.win32process")
    @patch("process_supervisor.psutil.Process")
    @patch("process_supervisor.sys")
    def test_get_foreground_process_success(self, mock_sys, mock_psutil_proc, mock_win32proc, mock_win32gui):
        mock_sys.platform = "win32"
        mock_win32gui.GetForegroundWindow.return_value = 12345
        mock_win32gui.GetWindowText.return_value = "main.py - Visual Studio Code"
        mock_win32proc.GetWindowThreadProcessId.return_value = (100, 4321)

        mock_proc_instance = MagicMock()
        mock_proc_instance.name.return_value = "Code.exe"
        mock_proc_instance.exe.return_value = "C:\\Users\\User\\AppData\\Local\\Programs\\Microsoft VS Code\\Code.exe"
        mock_psutil_proc.return_value = mock_proc_instance

        info = get_foreground_process_info()
        self.assertEqual(info["pid"], 4321)
        self.assertEqual(info["name"], "Code.exe")
        self.assertEqual(info["title"], "main.py - Visual Studio Code")
        self.assertIn("Code.exe", info["exe"])
        self.assertEqual(info["category"], "study")

    @patch("process_supervisor.win32gui", None)
    def test_get_foreground_process_no_win32gui_fallback(self):
        info = get_foreground_process_info()
        self.assertEqual(info["pid"], 0)
        self.assertEqual(info["name"], "")
        self.assertEqual(info["title"], "")
        self.assertEqual(info["exe"], "")
        self.assertEqual(info["category"], "general")

    @patch("process_supervisor.win32gui")
    @patch("process_supervisor.sys")
    def test_get_foreground_process_no_active_window(self, mock_sys, mock_win32gui):
        mock_sys.platform = "win32"
        mock_win32gui.GetForegroundWindow.return_value = 0
        info = get_foreground_process_info()
        self.assertEqual(info["pid"], 0)
        self.assertEqual(info["name"], "")

    @patch("process_supervisor.win32gui")
    @patch("process_supervisor.win32process")
    @patch("process_supervisor.psutil.Process")
    @patch("process_supervisor.sys")
    def test_get_foreground_process_access_denied_handled(self, mock_sys, mock_psutil_proc, mock_win32proc, mock_win32gui):
        mock_sys.platform = "win32"
        mock_win32gui.GetForegroundWindow.return_value = 999
        mock_win32gui.GetWindowText.return_value = "Protected Window"
        mock_win32proc.GetWindowThreadProcessId.return_value = (50, 8888)

        mock_psutil_proc.side_effect = process_supervisor.psutil.AccessDenied()

        info = get_foreground_process_info()
        self.assertEqual(info["pid"], 8888)
        self.assertEqual(info["title"], "Protected Window")
        self.assertEqual(info["name"], "")
        self.assertEqual(info["exe"], "")


class TestProcessRunningAndMatching(unittest.TestCase):
    """Test is_process_running and find_matching_processes."""

    @patch("process_supervisor.psutil.process_iter")
    def test_is_process_running_by_name(self, mock_proc_iter):
        p1 = MagicMock()
        p1.info = {"pid": 101, "name": "GenshinImpact.exe", "exe": "D:\\Genshin\\GenshinImpact.exe"}
        p2 = MagicMock()
        p2.info = {"pid": 102, "name": "Code.exe", "exe": "C:\\VSCode\\Code.exe"}
        mock_proc_iter.return_value = [p1, p2]

        self.assertTrue(is_process_running("GenshinImpact.exe"))
        self.assertTrue(is_process_running("genshinimpact"))
        self.assertTrue(is_process_running("code"))
        self.assertFalse(is_process_running("StarRail.exe"))
        self.assertFalse(is_process_running(""))

    @patch("process_supervisor.win32gui")
    @patch("process_supervisor.psutil.process_iter")
    def test_is_process_running_by_window_title(self, mock_proc_iter, mock_win32gui):
        mock_proc_iter.return_value = []
        mock_win32gui.IsWindowVisible.return_value = True
        mock_win32gui.GetWindowText.return_value = "原神 - Genshin Impact"

        def fake_enum(cb, param):
            cb(555, param)

        mock_win32gui.EnumWindows.side_effect = fake_enum

        self.assertTrue(is_process_running("genshin"))
        self.assertTrue(is_process_running("原神"))

    @patch("process_supervisor.psutil.process_iter")
    @patch("process_supervisor.win32gui", None)
    def test_find_matching_processes(self, mock_proc_iter):
        p1 = MagicMock()
        p1.info = {"pid": 201, "name": "Discord.exe", "exe": "C:\\Discord\\Discord.exe"}
        p2 = MagicMock()
        p2.info = {"pid": 202, "name": "Spotify.exe", "exe": "C:\\Spotify\\Spotify.exe"}
        mock_proc_iter.return_value = [p1, p2]

        matches = find_matching_processes("discord")
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["pid"], 201)
        self.assertEqual(matches[0]["name"], "Discord.exe")
        self.assertEqual(matches[0]["category"], "chat")

        self.assertEqual(find_matching_processes(""), [])


class TestProcessWatcher(unittest.TestCase):
    """Test ProcessWatcher state transitions, timers, and signals."""

    @classmethod
    def setUpClass(cls):
        if not QCoreApplication.instance():
            cls.app = QCoreApplication([])
        else:
            cls.app = QCoreApplication.instance()

    def setUp(self):
        self.watcher = ProcessWatcher(check_interval_ms=100)

    def tearDown(self):
        self.watcher.cancel()

    def test_initial_properties_and_callability(self):
        # Attribute and zero-arg method access must both work cleanly
        self.assertFalse(self.watcher.is_active)
        self.assertFalse(self.watcher.is_active())
        self.assertEqual(self.watcher.current_mode, "idle")
        self.assertEqual(self.watcher.current_mode(), "idle")
        self.assertEqual(self.watcher.remaining_seconds, 0.0)
        self.assertEqual(self.watcher.remaining_seconds(), 0.0)

    @patch("process_supervisor.time.time")
    def test_start_overtime_watch_and_ticks(self, mock_time):
        mock_time.return_value = 1000.0
        ticks = []
        self.watcher.watch_tick.connect(lambda r, t: ticks.append((r, t)))

        self.watcher.start_overtime_watch("GenshinImpact.exe", 1800.0)
        self.assertTrue(self.watcher.is_active)
        self.assertTrue(self.watcher.is_active())
        self.assertEqual(self.watcher.current_mode(), "overtime")
        self.assertGreater(len(ticks), 0)
        self.assertEqual(ticks[0], (1800.0, 1800.0))

        # Advance time by 300 seconds
        mock_time.return_value = 1300.0
        self.watcher.tick()
        self.assertAlmostEqual(self.watcher.remaining_seconds(), 1500.0)

    @patch("process_supervisor.get_foreground_process_info")
    @patch("process_supervisor.is_process_running")
    @patch("process_supervisor.time.time")
    def test_overtime_expiration_and_alerts(self, mock_time, mock_is_running, mock_get_fg):
        mock_time.return_value = 1000.0
        overtime_alerts = []
        self.watcher.overtime_detected.connect(lambda info, elapsed: overtime_alerts.append((info, elapsed)))

        mock_get_fg.return_value = {
            "pid": 5001,
            "name": "GenshinImpact.exe",
            "title": "原神",
            "exe": "D:\\Genshin\\GenshinImpact.exe",
            "category": "game",
        }
        mock_is_running.return_value = True

        self.watcher.start_overtime_watch("GenshinImpact.exe", 60.0)

        # Before expiration (t=1030s)
        mock_time.return_value = 1030.0
        self.watcher.tick()
        self.assertEqual(len(overtime_alerts), 0)

        # At expiration (t=1065s) -> target is running in fg -> alert emitted
        mock_time.return_value = 1065.0
        self.watcher.tick()
        self.assertEqual(len(overtime_alerts), 1)
        self.assertEqual(overtime_alerts[0][0]["name"], "GenshinImpact.exe")
        self.assertAlmostEqual(overtime_alerts[0][1], 65.0)

        # Periodic check afterwards (after cooldown): target still running -> another alert emitted
        mock_time.return_value = 1130.0
        self.watcher.tick()
        self.assertEqual(len(overtime_alerts), 2)

        # Target closes -> next tick detects target is no longer running -> stops watcher
        mock_get_fg.return_value = {"pid": 100, "name": "explorer.exe", "title": "", "exe": "", "category": "general"}
        mock_is_running.return_value = False
        mock_time.return_value = 1075.0
        self.watcher.tick()

        self.assertFalse(self.watcher.is_active())
        self.assertEqual(self.watcher.current_mode(), "idle")

    @patch("process_supervisor.get_foreground_process_info")
    @patch("process_supervisor.time.time")
    def test_focus_watch_completion(self, mock_time, mock_get_fg):
        mock_time.return_value = 2000.0
        focus_done = []
        self.watcher.focus_completed.connect(lambda d: focus_done.append(d))

        mock_get_fg.return_value = {
            "pid": 300,
            "name": "Code.exe",
            "title": "main.py - BandoriPet",
            "exe": "C:\\VSCode\\Code.exe",
            "category": "study",
        }

        self.watcher.start_focus_watch(allowed_keywords=["study", "code"], duration_seconds=120.0)
        self.assertTrue(self.watcher.is_active())
        self.assertEqual(self.watcher.current_mode(), "focus")

        # Advance to completion (t=2125s)
        mock_time.return_value = 2125.0
        self.watcher.tick()

        self.assertEqual(len(focus_done), 1)
        self.assertEqual(focus_done[0], 120.0)
        self.assertFalse(self.watcher.is_active())
        self.assertEqual(self.watcher.current_mode(), "idle")

    @patch("process_supervisor.get_foreground_process_info")
    @patch("process_supervisor.time.time")
    def test_focus_watch_distraction_and_grace_period(self, mock_time, mock_get_fg):
        mock_time.return_value = 3000.0
        distractions = []
        self.watcher.distraction_detected.connect(lambda info, allowed: distractions.append((info, allowed)))

        allowed = ["study", "Code"]
        self.watcher.start_focus_watch(allowed_keywords=allowed, duration_seconds=300.0, grace_period_seconds=10.0)

        # In allowed app (t=3000)
        mock_get_fg.return_value = {
            "pid": 301,
            "name": "Code.exe",
            "title": "work.py",
            "exe": "C:\\VSCode\\Code.exe",
            "category": "study",
        }
        self.watcher.tick()
        self.assertEqual(len(distractions), 0)

        # Switch to game (t=3005) -> begins grace period
        mock_time.return_value = 3005.0
        game_info = {
            "pid": 401,
            "name": "GenshinImpact.exe",
            "title": "原神",
            "exe": "D:\\Genshin\\GenshinImpact.exe",
            "category": "game",
        }
        mock_get_fg.return_value = game_info
        self.watcher.tick()
        self.assertEqual(len(distractions), 0)

        # Still in grace period (t=3012 -> 7s elapsed < 10s)
        mock_time.return_value = 3012.0
        self.watcher.tick()
        self.assertEqual(len(distractions), 0)

        # Grace period exceeded (t=3016 -> 11s elapsed >= 10s) -> distraction_detected emitted
        mock_time.return_value = 3016.0
        self.watcher.tick()
        self.assertEqual(len(distractions), 1)
        self.assertEqual(distractions[0][0]["name"], "GenshinImpact.exe")
        self.assertEqual(distractions[0][1], allowed)

        # Returning to allowed app clears distraction
        mock_time.return_value = 3020.0
        mock_get_fg.return_value = {
            "pid": 301,
            "name": "Code.exe",
            "title": "work.py",
            "exe": "C:\\VSCode\\Code.exe",
            "category": "study",
        }
        self.watcher.tick()
        self.assertEqual(len(distractions), 1)

    def test_cancel_stops_and_resets(self):
        self.watcher.start_overtime_watch("LeagueClient.exe", 600.0)
        self.assertTrue(self.watcher.is_active())

        self.watcher.cancel()
        self.assertFalse(self.watcher.is_active())
        self.assertEqual(self.watcher.current_mode(), "idle")
        self.assertEqual(self.watcher.remaining_seconds(), 0.0)


if __name__ == "__main__":
    unittest.main()
