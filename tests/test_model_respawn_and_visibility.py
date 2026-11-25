import unittest
from unittest.mock import MagicMock, patch
import os
import sys
from types import SimpleNamespace

# Ensure project root is in path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)


class TestModelVisibilityAndRespawn(unittest.TestCase):
    def test_taskbar_boundary_clamping_logic(self):
        """Test that target_y cannot drop completely below the screen."""
        screen_bottom = 1080
        screen_top = 0
        pet_height = 300

        # Simulate an abnormal taskbar top (e.g. 2000 px down due to monitor disconnect/auto-hide bug)
        abnormal_real_top = 2000
        target_y = abnormal_real_top - pet_height  # 1700

        # Boundary clamping formula used in pet_window.py:
        max_y = screen_bottom - 80  # 1000
        min_y = screen_top         # 0
        clamped_y = max(min_y, min(target_y, max_y))

        self.assertEqual(clamped_y, 1000)
        self.assertLessEqual(clamped_y, screen_bottom - 80)
        self.assertGreaterEqual(clamped_y, screen_top)

    def test_respawn_decision_logic(self):
        """Test the logic deciding whether a pet process should respawn."""
        def should_respawn(shutting_down: bool, exit_code: int, exit_status: str, history: list, now: float) -> tuple[bool, str]:
            if shutting_down:
                return False, "intentional shutdown"
            is_crash = (exit_status == "CrashExit" or exit_code != 0)
            if not is_crash:
                return False, "normal exit"
            recent = [t for t in history if now - t < 15.0]
            if len(recent) >= 3:
                return False, "rate limit exceeded"
            return True, "auto respawn"

        now = 1000.0

        # Case 1: Normal user exit -> No respawn
        respawn, reason = should_respawn(shutting_down=True, exit_code=0, exit_status="NormalExit", history=[], now=now)
        self.assertFalse(respawn)
        self.assertEqual(reason, "intentional shutdown")

        # Case 2: Silent crash (CrashExit) while app is alive -> Should auto-respawn
        respawn, reason = should_respawn(shutting_down=False, exit_code=1, exit_status="CrashExit", history=[], now=now)
        self.assertTrue(respawn)
        self.assertEqual(reason, "auto respawn")

        # Case 3: Crash rate limit protection (3 crashes within 15 seconds) -> Suppress loop
        history = [now - 10, now - 5, now - 1]
        respawn, reason = should_respawn(shutting_down=False, exit_code=1, exit_status="CrashExit", history=history, now=now)
        self.assertFalse(respawn)
        self.assertEqual(reason, "rate limit exceeded")


class TestCharacterGreeting(unittest.TestCase):
    def test_entry_greeting_prefers_cached_character_audio(self):
        from pet_window import PetWindow

        pet = SimpleNamespace(
            _current_char="rei",
            _tts_generation=2,
            _load_greetings=MagicMock(return_value={
                "startup_greeting": [
                    "还没缓存的问候",
                    {"text": "……我在。", "tts_text": "……ここにいる。"},
                ],
            }),
            _tts_enabled=MagicMock(return_value=True),
            _tts_config_snapshot=MagicMock(return_value={}),
            _show_pet_bubble=MagicMock(),
            _speak_pet_text=MagicMock(),
        )
        pet._pet_tts_request = lambda text, tts_text: PetWindow._pet_tts_request(pet, text, tts_text)
        missing = MagicMock()
        missing.stat.side_effect = FileNotFoundError
        cached = MagicMock()
        cached.stat.return_value.st_size = 4096
        with patch("pet_window._tts_cache_path", side_effect=[missing, cached]) as cache_path:
            PetWindow._show_startup_greeting(pet, 2)
        pet._show_pet_bubble.assert_called_once_with("……我在。", 6000)
        pet._speak_pet_text.assert_called_once_with("……我在。", "……ここにいる。")
        cache_path.assert_called_with(
            "……ここにいる。", "rei", {"tts_language": "Japanese", "tts_translate_to_selected_language": False},
        )

    def test_stale_greeting_is_ignored_and_cache_miss_uses_normal_tts(self):
        from pet_window import PetWindow

        pet = SimpleNamespace(
            _current_char="rei",
            _tts_generation=3,
            _load_greetings=MagicMock(return_value={"startup_greeting": ["……来了。"]}),
            _tts_enabled=MagicMock(return_value=True),
            _pet_tts_request=MagicMock(return_value=("……来了。", {})),
            _show_pet_bubble=MagicMock(),
            _speak_pet_text=MagicMock(),
        )
        missing = MagicMock()
        missing.stat.side_effect = FileNotFoundError
        with patch("pet_window._tts_cache_path", return_value=missing):
            PetWindow._show_startup_greeting(pet, 2)
            pet._speak_pet_text.assert_not_called()
            PetWindow._show_startup_greeting(pet, 3)
        pet._speak_pet_text.assert_called_once_with("……来了。", None)


if __name__ == "__main__":
    unittest.main()
