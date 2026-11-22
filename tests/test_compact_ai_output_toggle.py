import os
import sys
import unittest
from unittest.mock import MagicMock, patch

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from PySide6.QtWidgets import QApplication
from config_manager import ConfigManager


class TestCompactAIOutputToggle(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not QApplication.instance():
            cls.app = QApplication([])
        else:
            cls.app = QApplication.instance()

    def setUp(self):
        self.cfg = ConfigManager()
        self.cfg.set("compact_ai_show_chat_output", False)
        self.mock_model_mgr = MagicMock()
        self.db_patcher = patch("compact_ai_window.DatabaseManager")
        self.mock_db_cls = self.db_patcher.start()
        self.mock_db = MagicMock()
        self.mock_db.get_last_conversation.return_value = None
        self.mock_db_cls.return_value = self.mock_db

        from compact_ai_window import CompactAIWindow
        self.win = CompactAIWindow("kasumi", self.mock_model_mgr, self.cfg)

    def tearDown(self):
        self.win.close()
        self.win.deleteLater()
        self.db_patcher.stop()

    def test_default_config_show_chat_output_false(self):
        from config_manager import DEFAULTS
        self.assertIn("compact_ai_show_chat_output", DEFAULTS)
        self.assertFalse(DEFAULTS["compact_ai_show_chat_output"])

    def test_output_collapsed_when_empty(self):
        # When empty and chat output is disabled, output height should be 0 and hidden
        target_h = self.win._target_output_height()
        self.assertEqual(target_h, 0)
        self.win._update_output_height(animated=False)
        self.assertFalse(self.win._output.isVisible())

    def test_chat_response_does_not_fill_output_when_toggle_is_false(self):
        self.win._worker = MagicMock()
        replies_emitted = []
        self.win.assistant_reply_finished.connect(lambda t, a: replies_emitted.append((t, a)))

        with unittest.mock.patch.object(self.win, "sender", return_value=self.win._worker):
            self.win._on_chunk_received("你好呀！[smile01]", "")
            # Output in window should remain empty
            self.assertEqual(self.win._output.toPlainText().strip(), "")

            self.win._on_response_finished("你好呀！[smile01]", "", [])
            # Reply must be emitted for speech bubble
            self.assertEqual(len(replies_emitted), 1)
            self.assertEqual(replies_emitted[0][0], "你好呀！")
            # Output in window must still remain empty to avoid double bubble
            self.assertEqual(self.win._output.toPlainText().strip(), "")

    def test_chat_response_fills_output_when_toggle_is_true(self):
        self.cfg.set("compact_ai_show_chat_output", True)
        self.win._worker = MagicMock()

        with unittest.mock.patch.object(self.win, "sender", return_value=self.win._worker):
            self.win._on_chunk_received("你好呀！[smile01]", "")
            self.assertIn("你好呀！", self.win._output.toPlainText())

            self.win._on_response_finished("你好呀！[smile01]", "", [])
            self.assertEqual(self.win._output.toPlainText().strip(), "你好呀！")

    def test_default_capsule_style_is_frosted_acrylic(self):
        from config_manager import DEFAULTS
        self.assertIn("compact_ai_capsule_style", DEFAULTS)
        self.assertEqual(DEFAULTS["compact_ai_capsule_style"], "frosted_acrylic")

    def test_frosted_acrylic_theme_palette(self):
        self.cfg.set("compact_ai_capsule_style", "frosted_acrylic")
        self.win.refresh_theme()
        # In frosted acrylic mode, panel is white acrylic (R=255, G=255, B=255)
        self.assertEqual(self.win._panel_color.red(), 255)
        self.assertEqual(self.win._panel_color.green(), 255)
        self.assertEqual(self.win._panel_color.blue(), 255)

    def test_todo_command_intercepted(self):
        mock_todo = MagicMock()
        mock_todo.parse_text_input.return_value = True
        self.win.set_todo_manager(mock_todo)
        self.win._input.setPlainText("/game 30m")
        self.win.send_message()

        mock_todo.parse_text_input.assert_called_once_with("/game 30m")
        # Input should be cleared
        self.assertEqual(self.win._input.toPlainText(), "")


if __name__ == "__main__":
    unittest.main()
