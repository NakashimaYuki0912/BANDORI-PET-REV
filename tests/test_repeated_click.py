import pathlib
import tempfile
import unittest

from repeated_click import (
    DEFAULT_POKE_COOLDOWN,
    DEFAULT_POKE_INTERVAL,
    DEFAULT_POKE_THRESHOLD,
    character_default_repeated_click_entries,
    extract_action_tags,
    find_repeated_click_audio,
    normalize_repeated_click_entry,
    repeated_click_entries,
)
from tts_manager import collect_greeting_tts_items, collect_greeting_tts_lines


class RepeatedClickNormalizationTest(unittest.TestCase):
    def test_normalizes_string_entry_with_action_tag(self):
        norm = normalize_repeated_click_entry("喂！别一直戳我啊！很烦耶！[angry01]")
        self.assertIsNotNone(norm)
        self.assertEqual(norm["display_text"], "喂！别一直戳我啊！很烦耶！")
        self.assertEqual(norm["motion"], "angry01")
        self.assertEqual(norm["tts_text"], "喂！别一直戳我啊！很烦耶！")

    def test_normalizes_dict_entry_with_pretranslated_tts(self):
        raw = {
            "text": "不要一直点我啦！[angry01]",
            "tts_text": "もう、ずっとつつかないでよっ！",
            "motion": "angry01",
            "expression": "angry",
            "audio": "poke_01.wav",
        }
        norm = normalize_repeated_click_entry(raw)
        self.assertIsNotNone(norm)
        self.assertEqual(norm["display_text"], "不要一直点我啦！")
        self.assertEqual(norm["tts_text"], "もう、ずっとつつかないでよっ！")
        self.assertEqual(norm["motion"], "angry01")
        self.assertEqual(norm["expression"], "angry")
        self.assertEqual(norm["audio"], "poke_01.wav")

    def test_ignores_empty_or_invalid_entries(self):
        self.assertIsNone(normalize_repeated_click_entry(""))
        self.assertIsNone(normalize_repeated_click_entry("   "))
        self.assertIsNone(normalize_repeated_click_entry({}))
        self.assertIsNone(normalize_repeated_click_entry({"text": "  "}))
        self.assertIsNone(normalize_repeated_click_entry(12345))


class RepeatedClickPoolsTest(unittest.TestCase):
    def test_all_major_characters_have_custom_repeated_click_pools(self):
        chars = [
            "kasumi", "arisa", "tae", "rimi", "saaya",
            "yukina", "sayo", "lisa", "ako", "rinko",
            "ran", "moca", "himari", "tomoe", "tsugumi",
            "kokoro", "kaoru", "hagumi", "kanon", "misaki",
            "aya", "hina", "chisato", "maya", "eve",
            "tomorin", "anon", "rana", "soyo", "taki",
            "sakiko", "mutsumi", "uika", "umiri", "nyamu",
        ]
        for char in chars:
            with self.subTest(character=char):
                entries = character_default_repeated_click_entries(char)
                self.assertGreaterEqual(len(entries), 2)
                for entry in entries:
                    self.assertTrue(bool(entry["display_text"]))
                    self.assertTrue(bool(entry["tts_text"]))
                    self.assertNotIn("[", entry["display_text"])

    def test_unknown_character_falls_back_to_default_pool(self):
        entries = character_default_repeated_click_entries("unknown_xyz")
        self.assertGreaterEqual(len(entries), 3)
        for entry in entries:
            self.assertTrue(bool(entry["display_text"]))
            self.assertTrue(bool(entry["tts_text"]))

    def test_greetings_custom_repeated_click_overrides_defaults(self):
        custom_greetings = {
            "repeated_click": [
                {
                    "text": "自定义戳戳台词一[angry01]",
                    "tts_text": "カスタムボイス1",
                },
                {
                    "text": "自定义戳戳台词二[shame01]",
                    "tts_text": "カスタムボイス2",
                },
            ]
        }
        entries = repeated_click_entries(custom_greetings, "kasumi")
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0]["display_text"], "自定义戳戳台词一")
        self.assertEqual(entries[0]["motion"], "angry01")
        self.assertEqual(entries[1]["tts_text"], "カスタムボイス2")

    def test_greetings_poke_key_also_supported(self):
        custom_greetings = {
            "poke": [
                "别戳了很痒的[smile01]",
            ]
        }
        entries = repeated_click_entries(custom_greetings, "kasumi")
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["display_text"], "别戳了很痒的")
        self.assertEqual(entries[0]["motion"], "smile01")


class RepeatedClickAudioResolutionTest(unittest.TestCase):
    def test_finds_explicit_audio_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            base_dir = pathlib.Path(tmp_dir)
            audio_dir = base_dir / "characters" / "kasumi" / "repeated_clicks"
            audio_dir.mkdir(parents=True, exist_ok=True)
            wav_file = audio_dir / "poke_01.wav"
            wav_file.write_bytes(b"RIFF dummy wav data")

            entry = {"audio": "poke_01.wav"}
            found = find_repeated_click_audio(entry, "kasumi", base_dir=base_dir)
            self.assertIsNotNone(found)
            self.assertEqual(found.resolve(), wav_file.resolve())

    def test_finds_audio_file_from_repeated_clicks_folder_when_audio_not_specified(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            base_dir = pathlib.Path(tmp_dir)
            audio_dir = base_dir / "characters" / "arisa" / "repeated_clicks"
            audio_dir.mkdir(parents=True, exist_ok=True)
            mp3_file = audio_dir / "voice_01.mp3"
            mp3_file.write_bytes(b"dummy mp3 data")

            entry = {"text": "别戳我"}
            found = find_repeated_click_audio(entry, "arisa", base_dir=base_dir)
            self.assertIsNotNone(found)
            self.assertEqual(found.resolve(), mp3_file.resolve())

    def test_returns_none_when_no_audio_file_exists(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            base_dir = pathlib.Path(tmp_dir)
            entry = {"text": "别戳我"}
            found = find_repeated_click_audio(entry, "arisa", base_dir=base_dir)
            self.assertIsNone(found)


class RepeatedClickTTSPrewarmTest(unittest.TestCase):
    def test_collects_repeated_click_items_for_tts_prewarm(self):
        greetings = {
            "startup_greeting": ["欢迎回来！"],
            "repeated_click": [
                {
                    "text": "不要一直点我啦！[angry01]",
                    "tts_text": "もう、ずっとつつかないでよっ！",
                }
            ],
            "daily_chat": [
                {"text": "日常1", "tts_text": "日常1_JA"}
            ],
        }
        items = collect_greeting_tts_items(greetings)
        texts = [text for text, _pre in items]
        self.assertIn("欢迎回来！", texts)
        self.assertIn("もう、ずっとつつかないでよっ！", texts)
        self.assertIn("日常1_JA", texts)

        # Pretranslated check for the repeated click line
        repeated_item = [item for item in items if item[0] == "もう、ずっとつつかないでよっ！"][0]
        self.assertTrue(repeated_item[1])

    def test_prewarms_character_defaults_when_char_passed(self):
        import pathlib
        greetings = {"startup_greeting": ["欢迎！"]}
        items = collect_greeting_tts_items(greetings, character="kasumi", base_dir=pathlib.Path("/mock_empty_dir"))
        texts = [text for text, _pre in items]
        self.assertIn("欢迎！", texts)
        # Should contain Kasumi's Japanese poke lines
        self.assertTrue(any("つつかないで" in t or "やり返しちゃう" in t for t in texts))


class PetWindowClickInteractionTest(unittest.TestCase):
    def setUp(self):
        from pet_window import PetWindow

        class MockPet:
            def __init__(self):
                self._radial_menu = None
                self._pixel_mode = False
                self._poke_click_count = 0
                self._last_poke_click_time = 0.0
                self._last_poke_response_time = 0.0
                self._last_poke_entry_index = -1
                self._poke_threshold = DEFAULT_POKE_THRESHOLD
                self._poke_interval = DEFAULT_POKE_INTERVAL
                self._poke_cooldown = DEFAULT_POKE_COOLDOWN
                self.motion_calls = []
                self.response_calls = 0

            def _note_user_interaction(self):
                pass

            def _refresh_topmost_for_interaction(self, force=True):
                pass

            def _trigger_click_motion(self, x: float, y: float, area_name: str = ""):
                self.motion_calls.append((x, y, area_name))

            def _trigger_repeated_click_response(self):
                self.response_calls += 1

        self.mock_pet = MockPet()
        self.mock_pet._on_click = PetWindow._on_click.__get__(self.mock_pet)
        self.on_click = self.mock_pet._on_click
        self.on_double_click = PetWindow._on_double_click.__get__(self.mock_pet)
        self.mock_pet._live2d_widget = type("MockWidget", (), {"hit_area_name_at": lambda s, x, y: "head"})()

    def test_single_click_triggers_motion_without_dialogue(self):
        self.on_click(100.0, 150.0, "head")
        self.assertEqual(len(self.mock_pet.motion_calls), 1)
        self.assertEqual(self.mock_pet.motion_calls[0], (100.0, 150.0, "head"))
        self.assertEqual(self.mock_pet.response_calls, 0)
        self.assertEqual(self.mock_pet._poke_click_count, 1)

    def test_double_click_forwards_to_on_click_without_legacy_dialogue(self):
        self.on_double_click(120.0, 180.0)
        self.assertEqual(len(self.mock_pet.motion_calls), 1)
        self.assertEqual(self.mock_pet.motion_calls[0], (120.0, 180.0, "head"))
        self.assertEqual(self.mock_pet.response_calls, 0)
        self.assertEqual(self.mock_pet._poke_click_count, 1)

    def test_repeated_clicks_reach_threshold_and_trigger_response(self):
        for _ in range(DEFAULT_POKE_THRESHOLD):
            self.on_click(100.0, 150.0, "head")

        self.assertEqual(len(self.mock_pet.motion_calls), DEFAULT_POKE_THRESHOLD)
        self.assertEqual(self.mock_pet.response_calls, 1)
        # Streak resets after triggering
        self.assertEqual(self.mock_pet._poke_click_count, 0)

    def test_spaced_clicks_reset_counter_and_do_not_trigger(self):
        # First click
        self.on_click(100.0, 150.0, "head")
        self.assertEqual(self.mock_pet._poke_click_count, 1)

        # Simulate delay exceeding poke_interval
        self.mock_pet._last_poke_click_time -= (DEFAULT_POKE_INTERVAL + 1.0)
        self.on_click(100.0, 150.0, "head")
        # Counter resets to 1 instead of incrementing to 2
        self.assertEqual(self.mock_pet._poke_click_count, 1)
        self.assertEqual(self.mock_pet.response_calls, 0)


if __name__ == "__main__":
    unittest.main()
