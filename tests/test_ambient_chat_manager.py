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
)

class TestAmbientChatManager(unittest.TestCase):
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

    def test_build_ambient_prompt(self):
        ctx = {"time_str": "02:00", "time_phase": "深夜", "music": "None", "weather": "晴", "user_name": "TestUser"}
        prompt = build_ambient_prompt("rui", ctx)
        self.assertIn("八潮瑠唯", prompt)
        self.assertIn("02:00", prompt)
        self.assertIn("TestUser", prompt)

if __name__ == "__main__":
    unittest.main()
