import unittest
from unittest.mock import MagicMock, patch
import os
import sys

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from PySide6.QtWidgets import QApplication

class TestAmbientSchemeB(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not QApplication.instance():
            cls.app = QApplication([])

    def test_deliver_proactive_entry_tts_disabled(self):
        """When TTS is disabled, show bubble immediately without waiting."""
        from pet_window import PetWindow
        with patch.object(PetWindow, "__init__", lambda self: None):
            pet = PetWindow()
            pet._cfg = MagicMock()
            pet._cfg.get.return_value = False
            pet._tts_enabled = MagicMock(return_value=False)
            pet._speech_bubble = MagicMock()
            pet._pet_bubble_anchor = MagicMock(return_value=(100, 100))
            pet._start_click_motion = MagicMock()

            entry = {"text": "测试闲聊台词", "motion": "smile01", "expression": ""}
            pet._deliver_ambient_proactive_entry(entry)

            pet._speech_bubble.show_text.assert_called_once_with("测试闲聊台词", (100, 100))
            pet._start_click_motion.assert_called_once_with("smile01", "")


if __name__ == "__main__":
    unittest.main()
