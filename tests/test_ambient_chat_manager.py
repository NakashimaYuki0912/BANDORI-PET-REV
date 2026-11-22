import unittest
from unittest.mock import MagicMock, patch
import os
import sys

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from ambient_chat_manager import (
    parse_dialogue_motion,
    gather_desktop_context,
    load_character_few_shots,
    build_ambient_prompt,
    AmbientChatManager,
)
from PySide6.QtWidgets import QApplication

class TestAmbientChatManager(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not QApplication.instance():
            cls.app = QApplication([])

    def test_parse_dialogue_motion(self):
        text1 = "……还没休息吗？现在已经很晚了，继续盯着屏幕会增加疲劳。[natural01]"
        clean, motion = parse_dialogue_motion(text1)
        self.assertEqual(clean, "……还没休息吗？现在已经很晚了，继续盯着屏幕会增加疲劳。")
        self.assertEqual(motion, "natural01")

        text2 = "普通台词没有动作标签。"
        clean2, motion2 = parse_dialogue_motion(text2)
        self.assertEqual(clean2, "普通台词没有动作标签。")
        self.assertEqual(motion2, "")

    def test_gather_desktop_context(self):
        ctx = gather_desktop_context()
        self.assertIn("time_str", ctx)
        self.assertIn("time_phase", ctx)
        self.assertIn("music", ctx)
        self.assertIn("user_name", ctx)

    def test_load_character_few_shots_rui(self):
        samples = load_character_few_shots("rui")
        self.assertTrue(len(samples) > 0)
        self.assertTrue(any("效率" in s or "感情" in s for s in samples))

    def test_load_character_few_shots_kasumi(self):
        samples = load_character_few_shots("kasumi")
        self.assertTrue(len(samples) > 0)
        self.assertTrue(any("闪闪发光" in s or "心动" in s or "香澄" in s for s in samples))

    def test_load_character_few_shots_chinese_name(self):
        samples = load_character_few_shots("千早爱音")
        self.assertTrue(len(samples) > 0)

    def test_build_ambient_prompt(self):
        ctx = {"time_str": "02:00", "time_phase": "深夜", "music": "None", "weather": "晴", "user_name": "TestUser"}
        prompt = build_ambient_prompt("rui", ctx)
        self.assertIn("八潮瑠唯", prompt)
        self.assertIn("02:00", prompt)
        self.assertIn("TestUser", prompt)
        self.assertIn("说话方式", prompt)
        self.assertIn("绝对禁止", prompt)

    def test_character_banter_topic_generation(self):
        from ambient_chat_manager import build_ambient_prompt_bundle, get_character_band_info
        band_name, mates, cross_rels = get_character_band_info("mashiro")
        self.assertEqual(band_name, "Morfonica")
        self.assertTrue(len(mates) > 0)
        self.assertTrue(any("二叶筑紫" in m or "桐谷透子" in m for m in mates))

        ctx = {"time_str": "20:30", "time_phase": "夜晚", "music": "None", "weather": "凉爽", "user_name": "Lawrance"}
        prompt, user_cue = build_ambient_prompt_bundle("mashiro", ctx, topic_mode="character_banter")
        self.assertIn("仓田真白", prompt)
        self.assertIn("吐槽", prompt)
        self.assertIn("绝对严禁", prompt)
        self.assertTrue("透子" in prompt or "筑紫" in prompt or "七深" in prompt or "瑠唯" in prompt)

    def test_entry_prefetched_signal_and_pool(self):
        manager = AmbientChatManager(None)
        received = []
        manager.entry_prefetched.connect(lambda char, entry: received.append((char, entry)))

        entry = {"text": "测试台词", "motion": "smile01", "expression": "", "tts_text": "", "is_dynamic": True}
        manager._on_entry_fetched("rui", entry)

        self.assertEqual(len(received), 1)
        self.assertEqual(received[0][0], "rui")
        self.assertEqual(received[0][1]["text"], "测试台词")

        popped = manager.pop_ambient_entry("rui")
        self.assertIsNotNone(popped)
        self.assertEqual(popped["text"], "测试台词")
        manager.cleanup()


if __name__ == "__main__":
    unittest.main()
