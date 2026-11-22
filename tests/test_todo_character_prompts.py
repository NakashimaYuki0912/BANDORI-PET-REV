import os
import sys
import time
import unittest
from unittest.mock import MagicMock

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from todo_character_prompts import (
    extract_action_tags,
    strip_action_tags,
    split_dialogue_and_actions,
    format_alert_with_tags,
    normalize_character,
    generate_overtime_alert,
    generate_distraction_alert,
    generate_focus_completed_praise,
)


class TestTodoCharacterPrompts(unittest.TestCase):
    def test_extract_and_strip_action_tags(self):
        # Single tag
        text1 = "立刻把游戏关掉！[serious01]"
        self.assertEqual(extract_action_tags(text1), ["serious01"])
        self.assertEqual(strip_action_tags(text1), "立刻把游戏关掉！")

        # Multiple tags
        text2 = "太棒了，完成得很好！[smile01][gattsu]"
        self.assertEqual(extract_action_tags(text2), ["smile01", "gattsu"])
        self.assertEqual(strip_action_tags(text2), "太棒了，完成得很好！")

        # Exp and dash tags
        text3 = "不要让我失望。[yukina_serious.exp]"
        self.assertEqual(extract_action_tags(text3), ["yukina_serious.exp"])
        self.assertEqual(strip_action_tags(text3), "不要让我失望。")

        # No tag
        text4 = "普通的提醒文本，没有任何标签。"
        self.assertEqual(extract_action_tags(text4), [])
        self.assertEqual(strip_action_tags(text4), "普通的提醒文本，没有任何标签。")

        # DONE tag ignored
        text5 = "回复完成[DONE][serious01]"
        self.assertEqual(extract_action_tags(text5), ["serious01"])
        self.assertEqual(strip_action_tags(text5), "回复完成")

        # Recombine with format_alert_with_tags
        formatted = format_alert_with_tags("请关掉游戏", ["serious01", "pui"])
        self.assertEqual(formatted, "请关掉游戏 [serious01][pui]")

    def test_character_normalization(self):
        self.assertEqual(normalize_character("yukina"), "yukina")
        self.assertEqual(normalize_character("YUKINA"), "yukina")
        self.assertEqual(normalize_character("凑友希那"), "yukina")
        self.assertEqual(normalize_character("湊友希那"), "yukina")
        self.assertEqual(normalize_character("友希那"), "yukina")

        self.assertEqual(normalize_character("kasumi"), "kasumi")
        self.assertEqual(normalize_character("户山香澄"), "kasumi")
        self.assertEqual(normalize_character("香澄"), "kasumi")

        self.assertEqual(normalize_character("tomorin"), "tomorin")
        self.assertEqual(normalize_character("高松灯"), "tomorin")

        self.assertEqual(normalize_character("anon"), "anon")
        self.assertEqual(normalize_character("千早爱音"), "anon")

        self.assertEqual(normalize_character("soyo"), "soyo")
        self.assertEqual(normalize_character("长崎素世"), "soyo")

        self.assertEqual(normalize_character("taki"), "taki")
        self.assertEqual(normalize_character("椎名立希"), "taki")

        self.assertEqual(normalize_character("rana"), "rana")
        self.assertEqual(normalize_character("要乐奈"), "rana")

        self.assertEqual(normalize_character("aya"), "aya")
        self.assertEqual(normalize_character("丸山彩"), "aya")

        self.assertEqual(normalize_character("kokoro"), "kokoro")
        self.assertEqual(normalize_character("弦卷心"), "kokoro")

        self.assertEqual(normalize_character("ran"), "ran")
        self.assertEqual(normalize_character("美竹兰"), "ran")

        self.assertEqual(normalize_character("sayo"), "sayo")
        self.assertEqual(normalize_character("冰川纱夜"), "sayo")

        self.assertEqual(normalize_character("hina"), "hina")
        self.assertEqual(normalize_character("冰川日菜"), "hina")

        # Fallback
        self.assertEqual(normalize_character("nonexistent_unknown_character"), "default")
        self.assertEqual(normalize_character(""), "default")
        self.assertEqual(normalize_character(None), "default")

    def test_overtime_alerts_for_major_characters(self):
        characters = [
            "yukina", "kasumi", "tomorin", "anon", "soyo",
            "taki", "rana", "aya", "kokoro", "ran", "sayo", "hina",
            "default",
        ]
        for char in characters:
            with self.subTest(character=char):
                spoken_text, action_tags = generate_overtime_alert(
                    character=char,
                    task_name="原神游戏时间",
                    elapsed_minutes=20,
                    process_name="GenshinImpact.exe",
                    template_index=0,
                )
                self.assertIsInstance(spoken_text, str)
                self.assertTrue(len(spoken_text) > 0)
                self.assertIsInstance(action_tags, list)
                self.assertTrue(len(action_tags) >= 1)
                # Spoken text should NOT contain bracketed action tags
                self.assertNotIn("[", spoken_text)
                self.assertNotIn("]", spoken_text)
                # Spoken text should mention elapsed time and process name
                self.assertIn("20", spoken_text)
                self.assertIn("GenshinImpact.exe", spoken_text)
                # Action tags should be valid identifiers
                for tag in action_tags:
                    self.assertTrue(tag.isalnum() or "_" in tag or "." in tag)

    def test_distraction_alerts_for_major_characters(self):
        characters = [
            "yukina", "kasumi", "tomorin", "anon", "soyo",
            "taki", "rana", "aya", "kokoro", "ran", "sayo", "hina",
            "default",
        ]
        for char in characters:
            with self.subTest(character=char):
                spoken_text, action_tags = generate_distraction_alert(
                    character=char,
                    planned_task="Python 编程学习",
                    current_app="Bilibili",
                    template_index=0,
                )
                self.assertIsInstance(spoken_text, str)
                self.assertTrue(len(spoken_text) > 0)
                self.assertIsInstance(action_tags, list)
                self.assertTrue(len(action_tags) >= 1)
                # Spoken text should NOT contain bracketed action tags
                self.assertNotIn("[", spoken_text)
                self.assertNotIn("]", spoken_text)
                # Should mention planned task and distracting app
                self.assertIn("Python 编程学习", spoken_text)
                self.assertIn("Bilibili", spoken_text)

    def test_focus_completed_praise_for_major_characters(self):
        characters = [
            "yukina", "kasumi", "tomorin", "anon", "soyo",
            "taki", "rana", "aya", "kokoro", "ran", "sayo", "hina",
            "default",
        ]
        for char in characters:
            with self.subTest(character=char):
                spoken_text, action_tags = generate_focus_completed_praise(
                    character=char,
                    task_name="BandoriPet 核心模块开发",
                    duration_minutes=45,
                    template_index=0,
                )
                self.assertIsInstance(spoken_text, str)
                self.assertTrue(len(spoken_text) > 0)
                self.assertIsInstance(action_tags, list)
                self.assertTrue(len(action_tags) >= 1)
                # Spoken text should NOT contain bracketed action tags
                self.assertNotIn("[", spoken_text)
                self.assertNotIn("]", spoken_text)
                # Should mention duration
                self.assertIn("45", spoken_text)

    def test_character_persona_distinctive_traits(self):
        # 1. Yukina: 顶峰 / 觉悟 / 自律
        y_text, y_tags = generate_overtime_alert("yukina", "练习", 15, "Game.exe", template_index=0)
        self.assertTrue("顶峰" in y_text or "自律" in y_text or "觉悟" in y_text)
        self.assertIn("serious", y_tags[0])

        # 2. Kasumi: 闪闪发光 / 香澄 / 哔哔
        k_text, k_tags = generate_overtime_alert("kasumi", "休息", 10, "Game.exe", template_index=0)
        self.assertTrue("香澄" in k_text or "闪闪发光" in k_text or "哔哔" in k_text)

        # 3. Tomorin: 停下来 / 迷茫 / 难受
        t_text, t_tags = generate_overtime_alert("tomorin", "休息", 10, "Game.exe", template_index=0)
        self.assertTrue("停下来" in t_text or "身体" in t_text or "难受" in t_text or "迷茫" in t_text)

        # 4. Anon: 爱音大人 / 监督 / 小本本 / 大叉
        a_text, a_tags = generate_overtime_alert("anon", "休息", 15, "Game.exe", template_index=0)
        self.assertTrue("爱音" in a_text or "监督" in a_text or "大叉" in a_text)
        self.assertIn("angry", a_tags[0])

        # 5. Soyo: 约定 / 伤心 / 为什么
        s_text, s_tags = generate_overtime_alert("soyo", "休息", 12, "Game.exe", template_index=0)
        self.assertTrue("约定" in s_text or "伤心" in s_text or "为什么" in s_text)
        self.assertTrue(any(tag in ("sad01", "serious01", "odoodo") for tag in s_tags))

        # 6. Taki: 磨蹭 / 借口 / 咖啡 / 叹气
        tk_text, tk_tags = generate_overtime_alert("taki", "休息", 15, "Game.exe", template_index=0)
        self.assertTrue("磨蹭" in tk_text or "耗着" in tk_text or "干正事" in tk_text)
        self.assertTrue(any(tag in ("pui", "sigh", "angry01") for tag in tk_tags))

        # 7. Rana: 短句 / 芭菲 / 喵
        r_text, r_tags = generate_overtime_alert("rana", "休息", 15, "Game.exe", template_index=0)
        self.assertTrue("芭菲" in r_text or "喵" in r_text or "超了" in r_text)

        # 8. Aya: 彩前辈 / 哭 / 偶像 / 生气
        ay_text, ay_tags = generate_overtime_alert("aya", "休息", 15, "Game.exe", template_index=0)
        self.assertTrue("彩前辈" in ay_text or "彩彩" in ay_text or "偶像" in ay_text)
        self.assertTrue(any(tag in ("cry01", "surprised01", "angry01") for tag in ay_tags))

        # 9. Kokoro: 冒险 / 笑容 / 宝藏 / 快乐
        ko_text, ko_tags = generate_overtime_alert("kokoro", "休息", 15, "Game.exe", template_index=0)
        self.assertTrue("冒险" in ko_text or "笑容" in ko_text or "宝箱" in ko_text)

        # 10. Ran: 一如既往 / 夕阳 / 关了
        rn_text, rn_tags = generate_overtime_alert("ran", "休息", 15, "Game.exe", template_index=0)
        self.assertTrue("适可而止" in rn_text or "操心" in rn_text or "一如既往" in rn_text)

        # 11. Sayo: 自律 / 纪律 / 偏差
        sy_text, sy_tags = generate_overtime_alert("sayo", "休息", 15, "Game.exe", template_index=0)
        self.assertTrue("自律" in sy_text or "纪律" in sy_text or "偏差" in sy_text or "时间管理" in sy_text)

        # 12. Hina: Boppin / 噜~ / 天才
        h_text, h_tags = generate_overtime_alert("hina", "休息", 15, "Game.exe", template_index=0)
        self.assertTrue("噜" in h_text or "Boppin" in h_text or "日菜" in h_text)

    def test_chinese_name_input_works(self):
        # Testing Chinese character names
        text, tags = generate_overtime_alert("凑友希那", "练琴", 10, "Steam.exe")
        self.assertNotIn("[", text)
        self.assertTrue(len(tags) > 0)

        text2, tags2 = generate_distraction_alert("千早爱音", "记单词", "TikTok")
        self.assertNotIn("[", text2)
        self.assertIn("TikTok", text2)

        text3, tags3 = generate_focus_completed_praise("长崎素世", "复习", 30)
        self.assertNotIn("[", text3)
        self.assertTrue(len(tags3) > 0)

    def test_llm_generation_success_path(self):
        mock_llm = MagicMock()
        mock_llm.generate_alert.return_value = "你超时太久了，快点关掉！[angry01]"

        spoken, tags = generate_overtime_alert(
            character="yukina",
            task_name="打机",
            elapsed_minutes=30,
            process_name="Apex.exe",
            llm_manager=mock_llm,
        )
        self.assertEqual(spoken, "你超时太久了，快点关掉！")
        self.assertEqual(tags, ["angry01"])
        mock_llm.generate_alert.assert_called_once()

    def test_llm_generation_timeout_fallback(self):
        # LLM that blocks for 5 seconds (exceeding 2.5s timeout)
        def slow_llm(*args, **kwargs):
            time.sleep(5.0)
            return "我很慢很慢才返回[serious01]"

        start = time.time()
        spoken, tags = generate_overtime_alert(
            character="yukina",
            task_name="玩游戏",
            elapsed_minutes=15,
            process_name="Game.exe",
            llm_manager=slow_llm,
            template_index=0,
        )
        elapsed = time.time() - start

        # Should finish around 2.5s (allow small buffer, e.g. < 3.2s)
        self.assertLess(elapsed, 3.5)
        # Should fall back to offline template
        self.assertNotIn("我很慢很慢才返回", spoken)
        self.assertTrue(len(spoken) > 0)
        self.assertTrue(len(tags) > 0)

    def test_llm_generation_exception_fallback(self):
        def failing_llm(*args, **kwargs):
            raise RuntimeError("API connection failed")

        spoken, tags = generate_distraction_alert(
            character="anon",
            planned_task="作业",
            current_app="WeChat",
            llm_manager=failing_llm,
            template_index=0,
        )
        # Immediately falls back to offline template
        self.assertIn("作业", spoken)
        self.assertIn("WeChat", spoken)
        self.assertTrue(len(tags) > 0)

    def test_edge_case_inputs(self):
        # Empty process_name
        spoken1, tags1 = generate_overtime_alert("yukina", "", 0, "", template_index=0)
        self.assertIsInstance(spoken1, str)
        self.assertNotIn("{}", spoken1)
        self.assertTrue(len(tags1) > 0)

        # Negative elapsed_minutes
        spoken2, tags2 = generate_overtime_alert("kasumi", "任务", -10, "App", template_index=0)
        self.assertIn("1", spoken2)

        # Empty planned_task and current_app
        spoken3, tags3 = generate_distraction_alert("tomorin", "", "", template_index=0)
        self.assertIsInstance(spoken3, str)
        self.assertTrue(len(tags3) > 0)

        # Empty task_name and 0 duration
        spoken4, tags4 = generate_focus_completed_praise("soyo", "", 0, template_index=0)
        self.assertIsInstance(spoken4, str)
        self.assertTrue(len(tags4) > 0)


if __name__ == "__main__":
    unittest.main()
