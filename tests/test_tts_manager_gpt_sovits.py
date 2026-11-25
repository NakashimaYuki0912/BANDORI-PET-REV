import io
import json
import pathlib
import tempfile
import threading
import unittest
from unittest.mock import patch

import numpy as np
import soundfile as sf

import tts_manager
from tts_manager import (
    TTSRequestWorker,
    _build_translation_system_prompt,
    _find_referenced_characters,
    _gpt_sovits_model_paths,
    _gpt_sovits_payload,
    _iter_wav_stream_chunks,
    _pcm_to_wav_bytes,
    _select_gpt_sovits_split_params,
    _tts_api_language_code,
    collect_greeting_tts_items,
    _tts_lock,
    collect_greeting_tts_lines,
    effective_tts_voice_profile,
    split_tts_segments,
    tts_cache_path,
)


class GPTSoVITSTest(unittest.TestCase):
    def test_aya_japanese_translation_uses_unambiguous_self_name(self):
        prompt = _build_translation_system_prompt(
            "日语",
            "刚才彩又偷偷搜索了自己的名字。",
            "aya",
        )

        self.assertIn("丸山彩 (Aya Maruyama)", prompt)
        self.assertIn("写作「あや」", prompt)
        self.assertIn("不要单独写「彩」", prompt)

    def test_common_chinese_yao_is_not_mistaken_for_rana(self):
        self.assertNotIn("要乐奈", _find_referenced_characters("你要好好休息。"))
        self.assertIn("要乐奈", _find_referenced_characters("乐奈今天很有精神。"))

    def test_japanese_translation_prompt_enforces_bandori_katakana_for_bands(self):
        prompt = _build_translation_system_prompt(
            "日语",
            "Hello,Happy,World和Roselia今天的演出太棒了！",
            "kokoro",
        )

        self.assertIn("ハロー、ハッピーワールド！", prompt)
        self.assertIn("ロゼリア", prompt)
        self.assertIn("严禁保留英文拼写", prompt)
        self.assertIn("Term Japanese Speech Reference", prompt)

    def test_bandori_term_matcher_respects_word_boundaries(self):
        matched_terms = dict(tts_manager._find_referenced_bandori_terms("Hello,Happy,World在CiRCLE演出"))
        self.assertIn("Hello, Happy World!", matched_terms)
        self.assertIn("CiRCLE", matched_terms)
        unrelated = dict(tts_manager._find_referenced_bandori_terms("stay alive and bring a ring"))
        self.assertNotIn("LIVE", unrelated)
        self.assertNotIn("NFO", unrelated)

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

    def test_builds_local_model_paths_with_smart_discovery(self):
        paths = _gpt_sovits_model_paths("arisa", {"tts_gpt_sovits_root": "D:/BANDORI-GPT-SoVITS"})
        self.assertTrue(paths["gpt"].endswith("/arisa-e15.ckpt"))
        self.assertTrue(paths["sovits"].endswith("/arisa_e15_s10815.pth"))
        self.assertTrue(paths["reference"].endswith(("/arisa.wav", "/arisa.mp3")))

    def test_prefers_wav_reference_audio_over_mp3_when_available(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            wav_dir = root / "audio_reference_wav"
            wav_dir.mkdir(parents=True)
            (wav_dir / "arisa.wav").write_bytes(b"RIFF" + b"\x00" * 64)
            with patch.object(tts_manager, "app_base_dir", return_value=root):
                paths = _gpt_sovits_model_paths("arisa", {"tts_gpt_sovits_root": str(root)})
            self.assertEqual(paths["reference"], str(wav_dir / "arisa.wav").replace("\\", "/"))

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
            speed_factor=0.92,
            top_k=8,
            top_p=0.88,
            repetition_penalty=1.35,
        )

        self.assertEqual(payload["text"], "hello")
        self.assertEqual(payload["text_lang"], "ja")
        self.assertEqual(payload["ref_audio_path"], "/refs/anon.wav")
        self.assertEqual(payload["prompt_text"], "sample prompt")
        self.assertEqual(payload["prompt_lang"], "ja")
        self.assertEqual(payload["speed_factor"], 0.92)
        self.assertEqual(payload["top_k"], 8)
        self.assertEqual(payload["top_p"], 0.88)
        self.assertEqual(payload["repetition_penalty"], 1.35)
        self.assertEqual(payload["media_type"], "wav")
        self.assertFalse(payload["streaming_mode"])

    def test_global_profile_slows_default_voice(self):
        profile = effective_tts_voice_profile("kasumi", {"tts_speed_factor": 0.92})

        self.assertEqual(profile["speed_factor"], 0.92)
        self.assertEqual(profile["top_k"], 8)
        self.assertEqual(profile["top_p"], 0.88)

    def test_builtin_character_profiles_keep_requested_voice_differences(self):
        self.assertEqual(effective_tts_voice_profile("rei", {})["speed_factor"], 0.89)
        self.assertEqual(effective_tts_voice_profile("lisa", {})["speed_factor"], 0.90)
        chu2 = effective_tts_voice_profile("chu2", {})
        self.assertEqual(chu2["speed_factor"], 0.96)
        self.assertGreater(chu2["temperature"], 0.7)

    def test_default_profile_uses_conservative_temperature(self):
        self.assertEqual(effective_tts_voice_profile("kasumi", {})["temperature"], 0.60)

    def test_global_speed_preserves_builtin_character_pace_difference(self):
        self.assertAlmostEqual(
            effective_tts_voice_profile("rei", {"tts_speed_factor": 0.84})["speed_factor"],
            0.81,
        )
        self.assertAlmostEqual(
            effective_tts_voice_profile("chu2", {"tts_speed_factor": 0.84})["speed_factor"],
            0.88,
        )

    def test_saved_character_profile_overrides_builtin_defaults(self):
        profile = effective_tts_voice_profile(
            "lisa",
            {"tts_character_profiles": {"lisa": {"speed_factor": 0.87, "top_p": 0.82}}},
        )

        self.assertEqual(profile["speed_factor"], 0.87)
        self.assertEqual(profile["top_p"], 0.82)


class TtsCacheTest(unittest.TestCase):
    def test_daily_chat_replaces_legacy_click_lines_but_preserves_startup(self):
        greetings = {
            "daily_chat": [
                {"text": f"daily {index}", "motion": "natural01"}
                for index in range(12)
            ],
            "startup_greeting": ["legacy startup"],
            "click_responses": [{"lines": ["legacy click"]}],
            "tiers": [{"lines": ["legacy tier"]}],
        }

        self.assertEqual(
            collect_greeting_tts_lines(greetings),
            ["legacy startup", *[f"daily {index}" for index in range(12)]],
        )

    def test_pretranslated_daily_chat_items_are_marked_for_direct_tts(self):
        greetings = {
            "startup_greeting": ["legacy startup"],
            "daily_chat": [
                {"text": f"中文 {index}", "tts_text": f"日本語 {index}"}
                for index in range(12)
            ],
        }

        items = collect_greeting_tts_items(greetings)
        self.assertEqual(items[0], ("legacy startup", False))
        self.assertEqual(items[1], ("日本語 0", True))

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

    def test_cache_path_differs_when_voice_profile_changes(self):
        base = {"tts_language": "Japanese", "tts_temperature": 0.9}
        slower = {
            "tts_language": "Japanese",
            "tts_temperature": 0.9,
            "tts_character_profiles": {"kaoru": {"speed_factor": 0.88}},
        }

        self.assertNotEqual(
            tts_cache_path("hello", "kaoru", base),
            tts_cache_path("hello", "kaoru", slower),
        )

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


class TtsSpeedOptimizationTest(unittest.TestCase):
    def test_short_sentence_uses_cut0_without_batching(self):
        self.assertEqual(_select_gpt_sovits_split_params("なるほど、「愛してる」ってことね。", streaming=True), ("cut0", 1))
        self.assertEqual(_select_gpt_sovits_split_params("なるほど、「愛してる」ってことね。", streaming=False), ("cut0", 1))

    def test_long_text_uses_cut2_and_batch_when_non_streaming(self):
        long_text = "あ" * 65
        self.assertEqual(_select_gpt_sovits_split_params(long_text, streaming=True), ("cut2", 1))
        self.assertEqual(_select_gpt_sovits_split_params(long_text, streaming=False), ("cut2", 4))

    def test_iter_wav_stream_chunks_wraps_raw_pcm_across_odd_boundaries(self):
        sample_rate = 32000
        pcm = (np.arange(3000, dtype=np.int16) * 3).tobytes()
        empty_header = _pcm_to_wav_bytes(b"", sample_rate=sample_rate, channels=1, sample_width=2)
        stream_bytes = empty_header + pcm
        # Split into odd-sized chunks to verify header & 2-byte sample framing
        fragments = [
            stream_bytes[:17],
            stream_bytes[17:45],
            stream_bytes[45:4150],
            stream_bytes[4150:],
        ]

        class FakeStreamResponse:
            def iter_content(self, chunk_size=None):
                del chunk_size
                return iter(fragments)

            def close(self):
                pass

        wav_chunks = list(_iter_wav_stream_chunks(FakeStreamResponse(), min_chunk_bytes=2048))
        self.assertGreaterEqual(len(wav_chunks), 2)

        decoded = []
        for chunk in wav_chunks:
            data, sr = sf.read(io.BytesIO(chunk), dtype="int16")
            self.assertEqual(sr, sample_rate)
            decoded.append(data)
        reconstructed = np.concatenate(decoded).tobytes()
        self.assertEqual(reconstructed, pcm)

    def test_ensure_weights_skips_reload_when_local_yaml_matches(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = pathlib.Path(tmp) / "runtime"
            cfg_dir = runtime / "GPT_SoVITS" / "configs"
            cfg_dir.mkdir(parents=True)
            gpt = f"{tmp}/arisa-e15.ckpt".replace("\\", "/")
            sovits = f"{tmp}/arisa_e15_s10815.pth".replace("\\", "/")
            (cfg_dir / "bandoripet_local.yaml").write_text(
                "custom:\n"
                "  device: cuda\n"
                f"  t2s_weights_path: {gpt}\n"
                f"  vits_weights_path: {sovits}\n",
                encoding="utf-8",
            )
            url = f"http://127.0.0.1:9880/{abs(hash(tmp))}/"
            worker = TTSRequestWorker(
                0,
                0,
                "hello",
                "arisa",
                {"tts_api_url": url, "tts_gpt_sovits_runtime": str(runtime)},
            )
            with (
                patch.object(tts_manager, "_current_gpt_sovits_weights", None),
                patch.object(worker, "_set_gpt_sovits_weight") as mock_set,
            ):
                worker._ensure_gpt_sovits_weights({"gpt": gpt, "sovits": sovits})
                mock_set.assert_not_called()

    def test_ensure_weights_only_reloads_changed_component_across_processes(self):
        with tempfile.TemporaryDirectory() as tmp:
            url = f"http://127.0.0.1:9880/{abs(hash(tmp))}/"
            worker = TTSRequestWorker(0, 0, "hello", "arisa", {"tts_api_url": url})
            gpt_a = "/weights/a.ckpt"
            sovits_a = "/weights/a.pth"
            gpt_b = "/weights/b.ckpt"
            tts_manager._write_tts_state_weights(url, gpt_a, sovits_a)
            try:
                with (
                    patch.object(tts_manager, "_current_gpt_sovits_weights", None),
                    patch.object(worker, "_set_gpt_sovits_weight") as mock_set,
                ):
                    worker._ensure_gpt_sovits_weights({"gpt": gpt_b, "sovits": sovits_a})
                    mock_set.assert_called_once_with("set_gpt_weights", gpt_b)
            finally:
                _, state_path, _ = tts_manager._tts_ipc_paths(url)
                state_path.unlink(missing_ok=True)

    def test_streaming_worker_sends_cut0_and_streaming_mode_and_reuses_session(self):
        sample_rate = 32000
        pcm = (np.ones(2500, dtype=np.int16) * 7).tobytes()
        stream_bytes = _pcm_to_wav_bytes(b"", sample_rate=sample_rate) + pcm
        posts = []

        class FakeResponse:
            status_code = 200
            content = b""

            def iter_content(self, chunk_size=None):
                del chunk_size
                yield stream_bytes[:44]
                yield stream_bytes[44:]

            def close(self):
                pass

        class FakeSession:
            def post(self, url, json=None, stream=False, timeout=300):
                posts.append((url, json, stream, timeout))
                return FakeResponse()

        with tempfile.TemporaryDirectory() as tmp:
            url = f"http://127.0.0.1:9880/{abs(hash(tmp))}/"
            tts_manager._write_tts_state_weights(url, "/w/g.ckpt", "/w/s.pth")
            worker = TTSRequestWorker(
                3,
                9,
                "你好呀，今天天气真好。",
                "arisa",
                {
                    "tts_api_url": url,
                    "tts_language": "Japanese",
                    "tts_translate_to_selected_language": False,
                    "tts_streaming": True,
                    "tts_custom_weights": {
                        "arisa": {"gpt": "/w/g.ckpt", "sovits": "/w/s.pth", "reference": "/w/r.wav"}
                    },
                },
            )
            emitted = []
            worker.audio_ready.connect(lambda seq, gen, audio, fmt: emitted.append((seq, gen, audio, fmt)))
            try:
                with patch.object(tts_manager, "_get_tts_session", return_value=FakeSession()):
                    worker.run()
            finally:
                _, state_path, _ = tts_manager._tts_ipc_paths(url)
                state_path.unlink(missing_ok=True)

        self.assertEqual(len(posts), 1)
        self.assertTrue(posts[0][2])  # stream=True
        self.assertEqual(posts[0][1]["text_split_method"], "cut0")
        self.assertTrue(posts[0][1]["streaming_mode"])
        self.assertEqual(len(emitted), 1)
        self.assertEqual((emitted[0][0], emitted[0][1], emitted[0][3]), (3, 9, "wav"))
        data, sr = sf.read(io.BytesIO(emitted[0][2]), dtype="int16")
        self.assertEqual(sr, sample_rate)
        self.assertEqual(data.tobytes(), pcm)


if __name__ == "__main__":
    unittest.main()
