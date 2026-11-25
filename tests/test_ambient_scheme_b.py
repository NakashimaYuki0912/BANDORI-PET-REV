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

    def test_ambient_bubble_waits_for_playable_audio(self):
        from pet_window import PetWindow

        with patch.object(PetWindow, "__init__", lambda self: None):
            pet = PetWindow()
            pet._focus_mode = False
            pet._current_char = "kokoro"
            pet._tts_generation = 0
            pet._speech_bubble = MagicMock()
            pet._pet_bubble_anchor = MagicMock(return_value=(100, 100))
            pet._start_click_motion = MagicMock()
            pet._ensure_tts_player = MagicMock()
            pet._tts_player = MagicMock()
            pet.isVisible = MagicMock(return_value=True)
            pet._tts_enabled = MagicMock(return_value=True)
            pet._tts_config_snapshot = MagicMock(return_value={})
            entry = {"text": "打起精神吧！", "tts_text": "元気を出して！", "motion": "smile01"}
            with patch("pet_window._CachedTTSRequestWorker") as worker:
                pet._deliver_ambient_proactive_entry(entry)

            worker.assert_called_once_with(
                1, 1, "元気を出して！", "kokoro",
                {"tts_language": "Japanese", "tts_translate_to_selected_language": False},
                play_when_ready=True, parent=pet,
            )
            pet._speech_bubble.show_text.assert_not_called()
            pet._tts_player.enqueue.return_value = False
            pet._on_ambient_audio_ready(1, 1, b"unplayable", "wav")
            pet._speech_bubble.show_text.assert_not_called()

            pet._tts_player.enqueue.return_value = True
            pet._deliver_ambient_proactive_entry({**entry, "audio_bytes": b"ready", "audio_format": "wav"})
            pet._tts_player.enqueue.assert_called_with(b"ready", "wav")
            pet._speech_bubble.show_text.assert_called_once_with("打起精神吧！", (100, 100))
            pet._start_click_motion.assert_called_once_with("smile01", "")

    def test_focus_cancels_pending_ambient_speech_and_keeps_manual_audio(self):
        from pet_window import PetWindow

        with patch.object(PetWindow, "__init__", lambda self: None):
            pet = PetWindow()
            pet._focus_mode = False
            pet._cfg = MagicMock()
            pet._ambient_chat_manager = MagicMock()
            pet._tts_generation = 8
            pet._ambient_speech_generation = 8
            pet._pending_ambient_entry = {"text": "来休息一下吧"}
            pet._active_story_queue = [{"text": "下一段"}]
            pet._radial_menu = None
            pet._tts_player = MagicMock()
            pet._speech_bubble = MagicMock()
            pet._play_ambient_entry = MagicMock()

            pet._apply_focus_mode(True)
            pet._on_ambient_audio_ready(8, 8, b"late audio", "wav")
            pet._check_ambient_proactive_thought()
            pet._ambient_chat_manager.set_paused.assert_called_once_with(True)
            pet._ambient_chat_manager.pop_ambient_entry.assert_not_called()
            pet._play_ambient_entry.assert_not_called()
            pet._tts_player.stop.assert_called_once()
            self.assertFalse(pet._active_story_queue)

            pet._apply_focus_mode(False)
            pet._tts_player.stop.reset_mock()
            pet._apply_focus_mode(True)
            pet._tts_player.stop.assert_not_called()


if __name__ == "__main__":
    unittest.main()
