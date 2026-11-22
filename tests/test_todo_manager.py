from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

from PySide6.QtCore import QCoreApplication

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from todo_manager import (
    TodoSupervisionManager,
    extract_duration_minutes,
    parse_cn_number,
    parse_todo_intent,
)


class TestTodoSupervisionManager(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not QCoreApplication.instance():
            cls.app = QCoreApplication([])
        else:
            cls.app = QCoreApplication.instance()

    def setUp(self):
        self.mock_cfg = MagicMock()
        self.mgr = TodoSupervisionManager(character="yukina", config_manager=self.mock_cfg)

    def tearDown(self):
        self.mgr.cancel()

    def test_chinese_number_parsing(self):
        self.assertEqual(parse_cn_number("一"), 1.0)
        self.assertEqual(parse_cn_number("二"), 2.0)
        self.assertEqual(parse_cn_number("两"), 2.0)
        self.assertEqual(parse_cn_number("十"), 10.0)
        self.assertEqual(parse_cn_number("十五"), 15.0)
        self.assertEqual(parse_cn_number("二十"), 20.0)
        self.assertEqual(parse_cn_number("三十"), 30.0)
        self.assertEqual(parse_cn_number("四十五"), 45.0)

    def test_duration_extraction_variants(self):
        self.assertEqual(extract_duration_minutes("我要打游戏三十分钟了"), 30.0)
        self.assertEqual(extract_duration_minutes("我要打30分钟游戏"), 30.0)
        self.assertEqual(extract_duration_minutes("打半小时游戏"), 30.0)
        self.assertEqual(extract_duration_minutes("玩两小时游戏"), 120.0)
        self.assertEqual(extract_duration_minutes("写代码1小时"), 60.0)
        self.assertEqual(extract_duration_minutes("专注四十五分钟"), 45.0)
        self.assertEqual(extract_duration_minutes("学习一个半小时"), 90.0)
        self.assertEqual(extract_duration_minutes("一刻钟"), 15.0)

    def test_arisa_game_intent_and_tsundere_prompt(self):
        intent = parse_todo_intent("我要打游戏三十分钟了", character="arisa")
        self.assertIsNotNone(intent)
        self.assertEqual(intent["type"], "game")
        self.assertEqual(intent["duration"], 30.0)
        self.assertIn("拔电源", intent["message"])
        self.assertIn("angry01", intent["actions"])

    def test_video_supervision_user_sentence(self):
        sentence = "我想刷十分钟视频，如果十分钟后我依然在刷视频就记得提醒我"
        intent = parse_todo_intent(sentence, character="arisa")
        self.assertIsNotNone(intent)
        self.assertEqual(intent["type"], "game")
        self.assertEqual(intent["duration"], 10.0)
        self.assertIn("刷视频", intent["task_name"])
        self.assertIn("视频", intent["message"])
        self.assertIn("angry01", intent["actions"])

    def test_llm_tag_parsing(self):
        from todo_manager import parse_todo_tag, strip_todo_tags
        tag_str = "好啦好啦我知道了！[smile01][TODO_OVERTIME:15:刷视频]"
        mode, mins, task = parse_todo_tag(tag_str)
        self.assertEqual(mode, "overtime")
        self.assertEqual(mins, 15.0)
        self.assertEqual(task, "刷视频")
        clean = strip_todo_tags(tag_str)
        self.assertNotIn("TODO_OVERTIME", clean)
        self.assertIn("[smile01]", clean)

    def test_slash_game_command_parsing(self):
        confirmations = []
        self.mgr.confirmation_ready.connect(lambda msg, acts: confirmations.append((msg, acts)))

        handled = self.mgr.parse_text_input("/game 25m")
        self.assertTrue(handled)
        self.assertTrue(self.mgr.is_active)
        self.assertEqual(self.mgr.current_mode, "overtime")
        self.assertEqual(len(confirmations), 1)
        self.assertIn("25", confirmations[0][0])
        self.assertIn("yukina", self.mgr.get_status_info()["character"])

    def test_slash_study_command_parsing(self):
        confirmations = []
        self.mgr.confirmation_ready.connect(lambda msg, acts: confirmations.append((msg, acts)))

        handled = self.mgr.parse_text_input("/study 50")
        self.assertTrue(handled)
        self.assertTrue(self.mgr.is_active)
        self.assertEqual(self.mgr.current_mode, "focus")
        self.assertEqual(len(confirmations), 1)
        self.assertIn("50", confirmations[0][0])

    def test_natural_language_game_parsing(self):
        handled = self.mgr.parse_text_input("我要打游戏三十分钟了")
        self.assertTrue(handled)
        self.assertTrue(self.mgr.is_active)
        self.assertEqual(self.mgr.current_mode, "overtime")
        self.assertEqual(self.mgr._current_duration_minutes, 30.0)

    def test_natural_language_reversed_word_order(self):
        handled = self.mgr.parse_text_input("打半小时游戏")
        self.assertTrue(handled)
        self.assertTrue(self.mgr.is_active)
        self.assertEqual(self.mgr.current_mode, "overtime")
        self.assertEqual(self.mgr._current_duration_minutes, 30.0)

    def test_natural_language_focus_parsing(self):
        handled = self.mgr.parse_text_input("准备去学习45分钟")
        self.assertTrue(handled)
        self.assertTrue(self.mgr.is_active)
        self.assertEqual(self.mgr.current_mode, "focus")
        self.assertEqual(self.mgr._current_duration_minutes, 45.0)

    def test_cancel_command(self):
        self.mgr.start_game_supervision(30.0)
        self.assertTrue(self.mgr.is_active)

        handled = self.mgr.parse_text_input("/todo cancel")
        self.assertTrue(handled)
        self.assertFalse(self.mgr.is_active)

    def test_overtime_alert_emission(self):
        alerts = []
        self.mgr.alert_ready.connect(lambda msg, acts: alerts.append((msg, acts)))

        # Trigger simulated overtime event
        self.mgr.start_game_supervision(30.0, target_process="GenshinImpact.exe")
        self.mgr._on_overtime_detected({"name": "GenshinImpact.exe"}, elapsed_sec=600.0)

        self.assertEqual(len(alerts), 1)
        msg, acts = alerts[0]
        self.assertTrue(len(msg) > 0)
        self.assertTrue(len(acts) > 0)
        self.assertNotIn("[", msg)

    def test_distraction_alert_emission(self):
        alerts = []
        self.mgr.alert_ready.connect(lambda msg, acts: alerts.append((msg, acts)))

        self.mgr.start_focus_supervision(45.0, task_name="写代码")
        self.mgr._on_distraction_detected({"name": "bilibili.exe"}, [])

        self.assertEqual(len(alerts), 1)
        msg, acts = alerts[0]
        self.assertTrue(len(msg) > 0)
        self.assertIn("bilibili", msg)
        self.assertNotIn("[", msg)

    def test_slash_todo_overtime_and_focus_variants(self):
        # /todo overtime 10 刷视频
        intent = parse_todo_intent("/todo overtime 10 刷视频", character="arisa")
        self.assertIsNotNone(intent)
        self.assertEqual(intent["type"], "game")
        self.assertEqual(intent["duration"], 10.0)
        self.assertEqual(intent["task_name"], "刷视频")

        # /todo focus 45 写代码
        intent_f = parse_todo_intent("/todo focus 45 写代码", character="arisa")
        self.assertIsNotNone(intent_f)
        self.assertEqual(intent_f["type"], "focus")
        self.assertEqual(intent_f["duration"], 45.0)
        self.assertEqual(intent_f["task_name"], "写代码")

        # [TODO_OVERTIME:10:刷视频]
        intent_tag = parse_todo_intent("[TODO_OVERTIME:10:刷视频]", character="arisa")
        self.assertIsNotNone(intent_tag)
        self.assertEqual(intent_tag["type"], "game")
        self.assertEqual(intent_tag["duration"], 10.0)
        self.assertEqual(intent_tag["task_name"], "刷视频")

    def test_character_switching_persona(self):
        self.mgr.set_character("arisa")
        confirmations = []
        self.mgr.confirmation_ready.connect(lambda msg, acts: confirmations.append((msg, acts)))

        self.mgr.start_game_supervision(30.0)
        self.assertEqual(len(confirmations), 1)
        self.assertIn("arisa", self.mgr.get_status_info()["character"])
        self.assertIn("拔电源", confirmations[0][0])


if __name__ == "__main__":
    unittest.main()
