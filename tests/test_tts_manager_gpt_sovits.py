import pathlib
import threading
import unittest

from tts_manager import (
    TTSRequestWorker,
    _gpt_sovits_model_paths,
    _gpt_sovits_payload,
    _tts_api_language_code,
    _tts_lock,
    collect_greeting_tts_lines,
    split_tts_segments,
    tts_cache_path,
)


class GPTSoVITSTest(unittest.TestCase):
    def test_builds_standard_remote_model_paths(self):
        paths = _gpt_sovits_model_paths("kaoru", {})

        self.assertEqual(
            paths["gpt"],
            "/home/kirby/minecraft/bandori-tts/GPT-SoVITS/GPT_weights_v2/kaoru-e15.ckpt",
        )
        self.assertEqual(
            paths["sovits"],
            "/home/kirby/minecraft/bandori-tts/GPT-SoVITS/SoVITS_weights_v2/kaoru_e15_s6675.pth",
        )
        self.assertEqual(
            paths["reference"],
            "/home/kirby/minecraft/bandori-tts/audio_reference_wav/kaoru.wav",
        )

    def test_builds_special_case_remote_model_paths(self):
        cases = {
            "ran": ("ran-chitchai-e10.ckpt", "ran-chitchai_e15_s8310.pth"),
            "rimi": ("rimi-e10.ckpt", "rimi_e15_s7545.pth"),
            "rinko": ("rinko-e5.ckpt", "rinko_e15_s7215.pth"),
            "kasumi": ("kasumi-e5.ckpt", "kasumi_e15_s11190.pth"),
        }

        for character, (gpt_file, sovits_file) in cases.items():
            with self.subTest(character=character):
                paths = _gpt_sovits_model_paths(character, {})
                self.assertTrue(paths["gpt"].endswith(f"/GPT_weights_v2/{gpt_file}"))
                self.assertTrue(paths["sovits"].endswith(f"/SoVITS_weights_v2/{sovits_file}"))

    def test_maps_settings_languages_to_api_codes(self):
        self.assertEqual(_tts_api_language_code("Japanese"), "ja")
        self.assertEqual(_tts_api_language_code("Chinese"), "zh")
        self.assertEqual(_tts_api_language_code("English"), "en")

    def test_builds_v2_tts_payload(self):
        payload = _gpt_sovits_payload(
            text="hello",
            text_language="Japanese",
            reference_path="/refs/anon.wav",
            prompt_text="sample prompt",
            temperature=0.9,
        )

        self.assertEqual(payload["text"], "hello")
        self.assertEqual(payload["text_lang"], "ja")
        self.assertEqual(payload["ref_audio_path"], "/refs/anon.wav")
        self.assertEqual(payload["prompt_text"], "sample prompt")
        self.assertEqual(payload["prompt_lang"], "ja")
        self.assertEqual(payload["media_type"], "wav")
        self.assertFalse(payload["streaming_mode"])


class TtsCacheTest(unittest.TestCase):
    def test_collects_startup_click_and_tiers_in_order_deduped(self):
        greetings = {
            "startup_greeting": ["hello", "world"],
            "click_responses": [
                {"lines": ["click one", "hello"]},        # "hello" is a dup
                {"lines": ["click two"]},
            ],
            "tiers": [
                {"lines": ["tier one", "click one"]},     # "click one" is a dup
            ],
        }
        lines = collect_greeting_tts_lines(greetings)
        self.assertEqual(
            lines,
            ["hello", "world", "click one", "click two", "tier one"],
        )

    def test_skips_empty_and_whitespace_only_lines(self):
        greetings = {
            "startup_greeting": ["  ", "", "valid"],
            "click_responses": [],
            "tiers": [],
        }
        lines = collect_greeting_tts_lines(greetings)
        self.assertEqual(lines, ["valid"])

    def test_handles_missing_keys_gracefully(self):
        lines = collect_greeting_tts_lines({})
        self.assertEqual(lines, [])

    def test_cache_path_is_deterministic(self):
        config = {"tts_language": "Japanese", "tts_temperature": 0.9}
        p1 = tts_cache_path("hello", "kaoru", config)
        p2 = tts_cache_path("hello", "kaoru", config)
        self.assertEqual(p1, p2)

    def test_cache_path_differs_by_character(self):
        config = {"tts_language": "Japanese", "tts_temperature": 0.9}
        p1 = tts_cache_path("hi", "kaoru", config)
        p2 = tts_cache_path("hi", "ran", config)
        self.assertNotEqual(p1, p2)

    def test_cache_path_differs_by_language(self):
        config_ja = {"tts_language": "Japanese", "tts_temperature": 0.9}
        config_zh = {"tts_language": "Chinese", "tts_temperature": 0.9}
        p1 = tts_cache_path("hi", "kaoru", config_ja)
        p2 = tts_cache_path("hi", "kaoru", config_zh)
        self.assertNotEqual(p1, p2)

    def test_cache_path_differs_by_text(self):
        config = {"tts_language": "Japanese", "tts_temperature": 0.9}
        p1 = tts_cache_path("hi", "kaoru", config)
        p2 = tts_cache_path("bye", "kaoru", config)
        self.assertNotEqual(p1, p2)

    def test_cache_path_ends_with_wav(self):
        config = {"tts_language": "Japanese", "tts_temperature": 0.9}
        p = tts_cache_path("test", "kaoru", config)
        self.assertTrue(str(p).endswith(".wav"))

    def test_cache_path_is_in_tts_cache_dir(self):
        config = {"tts_language": "Japanese", "tts_temperature": 0.9}
        p = tts_cache_path("test", "kaoru", config)
        self.assertIn("tts_cache", p.parts)
        self.assertIn("gpt_sovits", p.parts)
        self.assertIn("kaoru", p.parts)

    def test_cache_path_uses_reference_character_when_set(self):
        """tts_cache_path should use config['tts_reference_character'] if provided."""
        config_with_ref = {
            "tts_language": "Japanese",
            "tts_temperature": 0.9,
            "tts_reference_character": "ran",
        }
        p_ref = tts_cache_path("hello", "kaoru", config_with_ref)
        # Cache dir should use the reference character, not the display character
        self.assertIn("ran", p_ref.parts)
        self.assertNotIn("kaoru", p_ref.parts)

    def test_cache_path_falls_back_to_character_when_reference_empty(self):
        """When tts_reference_character is empty, fall back to character."""
        config_no_ref = {
            "tts_language": "Japanese",
            "tts_temperature": 0.9,
            "tts_reference_character": "",
        }
        p = tts_cache_path("hello", "kaoru", config_no_ref)
        self.assertIn("kaoru", p.parts)


class TtsSegmentSplitTest(unittest.TestCase):
    def test_splits_chinese_and_japanese_sentence_endings(self):
        text = "你好呀。今日はいい天気ですね！继续聊吗？"

        self.assertEqual(
            split_tts_segments(text),
            ["你好呀。", "今日はいい天気ですね！", "继续聊吗？"],
        )

    def test_strips_action_tags_and_empty_segments(self):
        text = "[smile]  第一段。\n\n[DONE]\n第二段！"

        self.assertEqual(split_tts_segments(text), ["第一段。", "第二段！"])

    def test_splits_long_segment_by_soft_punctuation(self):
        text = "前半部分很长很长很长很长很长很长很长很长很长，后半部分也很长很长很长很长很长。"

        segments = split_tts_segments(text, max_chars=24)

        self.assertGreater(len(segments), 1)
        self.assertTrue(all(len(segment) <= 32 for segment in segments))


class TtsLockTest(unittest.TestCase):
    def test_module_lock_is_threading_lock(self):
        self.assertIsInstance(_tts_lock, type(threading.Lock()))

    def test_worker_has_generate_audio_bytes_method(self):
        self.assertTrue(callable(getattr(TTSRequestWorker, "_generate_audio_bytes", None)))


if __name__ == "__main__":
    unittest.main()
