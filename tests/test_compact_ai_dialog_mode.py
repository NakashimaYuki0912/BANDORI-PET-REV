import os
import sys
import tempfile
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from PySide6.QtWidgets import QApplication
from config_manager import ConfigManager, DEFAULTS
from i18n_manager import set_language, current_language


class TestCompactAIDialogMode(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not QApplication.instance():
            cls.app = QApplication([])
        else:
            cls.app = QApplication.instance()

    def setUp(self):
        self.orig_lang = current_language()
        set_language("zh_CN")

        self.tmp_dir = tempfile.TemporaryDirectory()
        self.tmp_config_path = Path(self.tmp_dir.name) / "config.json"
        self.cfg = ConfigManager(path=self.tmp_config_path)
        self.cfg.set("compact_ai_show_chat_output", False)
        self.mock_model_mgr = MagicMock()
        self.mock_model_mgr.get_display_name.return_value = "Kasumi"

        self.db_patcher = patch("compact_ai_window.DatabaseManager")
        self.mock_db_cls = self.db_patcher.start()
        self.mock_db = MagicMock()
        self.mock_db.get_last_conversation.return_value = None
        self.mock_db.get_relationship_state.return_value = {
            "affection": 50,
            "trust": 50,
            "familiarity": 50,
            "mood": "calm",
            "mood_intensity": 50,
        }
        self.mock_db.get_character_memories.return_value = []
        self.mock_db_cls.return_value = self.mock_db

        from compact_ai_window import CompactAIWindow
        self.win = CompactAIWindow("kasumi", self.mock_model_mgr, self.cfg)

    def tearDown(self):
        self.win.close()
        self.win.deleteLater()
        self.db_patcher.stop()
        self.tmp_dir.cleanup()
        set_language(self.orig_lang)

    # 1. 测试 CompactAIWindow 默认对话模式为 "short_term"
    def test_default_dialog_mode_is_short_term(self):
        self.assertIn("compact_ai_dialog_mode", DEFAULTS)
        self.assertEqual(DEFAULTS["compact_ai_dialog_mode"], "short_term")
        self.assertEqual(self.win._dialog_mode, "short_term")

        # Config 为 None 或未设定时，默认也应为 short_term
        from compact_ai_window import CompactAIWindow
        win_no_cfg = CompactAIWindow("kasumi", self.mock_model_mgr, None)
        try:
            self.assertEqual(win_no_cfg._dialog_mode, "short_term")
        finally:
            win_no_cfg.close()
            win_no_cfg.deleteLater()

    # 2. 测试 toggle_dialog_mode() 切换与 UI 元素更新（⚡ 短期 vs 💬 长期，tooltip，input placeholder）
    def test_toggle_dialog_mode_toggles_and_updates_ui(self):
        # 初始 short_term 模式
        self.assertEqual(self.win._dialog_mode, "short_term")
        self.assertEqual(self.win._mode_button.text(), "⚡ 短期")
        self.assertIn("短期对话", self.win._mode_button.toolTip())
        self.assertIn("发完即隐", self.win._input.placeholderText())

        # 切换到 long_term
        self.win.toggle_dialog_mode()
        self.assertEqual(self.win._dialog_mode, "long_term")
        self.assertEqual(self.cfg.get("compact_ai_dialog_mode"), "long_term")
        self.assertEqual(self.win._mode_button.text(), "💬 长期")
        self.assertIn("长期对话", self.win._mode_button.toolTip())
        self.assertIn("连续对话", self.win._input.placeholderText())

        # 再次切换回到 short_term
        self.win.toggle_dialog_mode()
        self.assertEqual(self.win._dialog_mode, "short_term")
        self.assertEqual(self.cfg.get("compact_ai_dialog_mode"), "short_term")
        self.assertEqual(self.win._mode_button.text(), "⚡ 短期")
        self.assertIn("短期对话", self.win._mode_button.toolTip())
        self.assertIn("发完即隐", self.win._input.placeholderText())

    # 3. 测试 set_dialog_mode("long_term") 时：自动调用 ensure_context_loaded()，最多恢复 20 条消息，_should_show_chat_output() 返回 True
    def test_set_dialog_mode_long_term_loads_context_and_enables_output(self):
        self.mock_db.get_last_conversation.return_value = {"id": 100, "title": "History"}
        # 数据库中存在 30 条对话记录
        self.mock_db.get_messages.return_value = [
            {"role": "user" if i % 2 == 0 else "assistant", "content": f"msg_{i}"}
            for i in range(30)
        ]
        self.win._history.clear()

        with patch.object(self.win, "ensure_context_loaded", wraps=self.win.ensure_context_loaded) as spy_ensure:
            self.win.set_dialog_mode("long_term")
            spy_ensure.assert_called_once()

        # 验证 context history 最多恢复 20 条消息（即最近的 20 条 msg_10 到 msg_29）
        self.assertEqual(len(self.win._history), 20)
        self.assertEqual(self.win._history[0]["content"], "msg_10")
        self.assertEqual(self.win._history[-1]["content"], "msg_29")

        # 即使配置 compact_ai_show_chat_output 为 False，long_term 下也返回 True
        self.assertFalse(self.cfg.get("compact_ai_show_chat_output", False))
        self.assertTrue(self.win._should_show_chat_output())

    # 4. 测试 set_dialog_mode("short_term") 时：_should_show_chat_output() 遵循配置
    def test_set_dialog_mode_short_term_chat_output_follows_config(self):
        self.win.set_dialog_mode("short_term")

        # 默认配置为 False
        self.cfg.set("compact_ai_show_chat_output", False)
        self.assertFalse(self.win._should_show_chat_output())

        # 配置设为 True
        self.cfg.set("compact_ai_show_chat_output", True)
        self.assertTrue(self.win._should_show_chat_output())

    # 5. 测试短期模式下 send_message() 窗口被 hide()，长期模式下不会被 hide()
    @patch("compact_ai_window.LLMStreamWorker")
    def test_send_message_short_term_hides_window(self, mock_worker_cls):
        mock_worker = MagicMock()
        mock_worker_cls.return_value = mock_worker

        self.cfg.set("llm_api_url", "https://api.openai.com/v1/chat/completions")
        self.cfg.set("llm_api_key", "sk-mock-key")
        self.cfg.set("llm_model_id", "gpt-4o-mini")

        self.win.set_dialog_mode("short_term")
        self.win.show()
        self.assertTrue(self.win.isVisible())

        self.win._input.setPlainText("你好香澄！")
        with patch.object(self.win, "hide", wraps=self.win.hide) as spy_hide:
            self.win.send_message()
            spy_hide.assert_called_once()
            self.assertFalse(self.win.isVisible())

    @patch("compact_ai_window.LLMStreamWorker")
    def test_send_message_long_term_does_not_hide_window(self, mock_worker_cls):
        mock_worker = MagicMock()
        mock_worker_cls.return_value = mock_worker

        self.cfg.set("llm_api_url", "https://api.openai.com/v1/chat/completions")
        self.cfg.set("llm_api_key", "sk-mock-key")
        self.cfg.set("llm_model_id", "gpt-4o-mini")

        self.win.set_dialog_mode("long_term")
        self.win.show()
        self.assertTrue(self.win.isVisible())

        self.win._input.setPlainText("你好香澄！")
        with patch.object(self.win, "hide", wraps=self.win.hide) as spy_hide:
            self.win.send_message()
            spy_hide.assert_not_called()
            self.assertTrue(self.win.isVisible())

    # 6. 测试 _build_messages() 中的 history_limit
    def test_build_messages_history_limit(self):
        # 准备 25 条历史消息
        self.win._history = [
            {"role": "user" if i % 2 == 0 else "assistant", "content": f"msg_{i}"}
            for i in range(25)
        ]

        # long_term 模式下保留最多 20 条消息上下文
        self.win.set_dialog_mode("long_term")
        messages_long = self.win._build_messages()
        # messages[0] 是 system prompt，其余是历史消息
        self.assertEqual(messages_long[0]["role"], "system")
        chat_msgs_long = messages_long[1:]
        self.assertEqual(len(chat_msgs_long), 20)
        self.assertIn("msg_5", chat_msgs_long[0]["content"])
        self.assertIn("msg_24", chat_msgs_long[-1]["content"])

        # short_term 模式下保留最多 8 条消息上下文
        self.win.set_dialog_mode("short_term")
        messages_short = self.win._build_messages()
        self.assertEqual(messages_short[0]["role"], "system")
        chat_msgs_short = messages_short[1:]
        self.assertEqual(len(chat_msgs_short), 8)
        self.assertIn("msg_17", chat_msgs_short[0]["content"])
        self.assertIn("msg_24", chat_msgs_short[-1]["content"])


if __name__ == "__main__":
    unittest.main()
