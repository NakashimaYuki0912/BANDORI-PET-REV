import unittest
from unittest.mock import MagicMock, call, patch
import json
import os
import sys
import time

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from PySide6.QtWidgets import QApplication

from config_manager import ConfigManager, DEFAULT_CONFIG, DEFAULTS
from ambient_chat_manager import (
    parse_dialogue_motion,
    parse_ambient_story_segments,
    build_ambient_prompt_bundle,
    build_ambient_prompt,
    AmbientChatManager,
    AmbientPrefetchWorker,
)


class TestAmbientStoryMode(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not QApplication.instance():
            cls.app = QApplication([])

    def test_config_defaults(self):
        """Verify new story mode config items are present with correct default values."""
        self.assertIn("ambient_story_mode_enabled", DEFAULT_CONFIG)
        self.assertTrue(DEFAULT_CONFIG["ambient_story_mode_enabled"])
        self.assertEqual(DEFAULT_CONFIG["ambient_story_probability"], 0.30)

        # Test reading through ConfigManager instance with default config
        cfg = ConfigManager("nonexistent_default_test.json")
        self.assertTrue(cfg.get("ambient_story_mode_enabled"))
        self.assertAlmostEqual(cfg.get("ambient_story_probability"), 0.30)

    def test_prompt_construction_story_mode(self):
        """Verify prompt construction differentiates single-line and story mode."""
        ctx = {"time_str": "15:00", "time_phase": "下午", "music": "无", "user_name": "TestUser"}

        # 1. Standard mode
        prompt_std, cue_std = build_ambient_prompt_bundle("kasumi", ctx, story_mode=False)
        self.assertIn("18 到 45 个中文字符", prompt_std)
        self.assertNotIn("JSON 字符串数组", prompt_std)

        # 2. Story mode
        prompt_story, cue_story = build_ambient_prompt_bundle("kasumi", ctx, story_mode=True)
        self.assertIn("连贯微故事", prompt_story)
        self.assertIn("JSON 字符串数组", prompt_story)
        self.assertIn("2 到 4 句连贯", prompt_story)
        self.assertIn("15 到 35 个中文字符", prompt_story)
        self.assertIn("Live2D 动作标签", prompt_story)
        self.assertIn("微故事", cue_story)

        # 3. Backward compatible build_ambient_prompt
        prompt_compat = build_ambient_prompt("kasumi", ctx, story_mode=True)
        self.assertIn("JSON 字符串数组", prompt_compat)

        context = {
            "time_phase": "夜晚", "weather": "小雨", "music": "练习曲",
            "fg_title": "未公开文档标题",
        }
        contextual_story = build_ambient_prompt("kasumi", context, story_mode=True)
        self.assertIn("小雨", contextual_story)
        self.assertIn("练习曲", contextual_story)
        self.assertIn("夜晚", contextual_story)
        self.assertNotIn("未公开文档标题", contextual_story)

    def test_parse_story_segments_layer1_clean_json(self):
        """Verify Layer 1 JSON array parsing for clean array."""
        raw = '["今天排练完回去的路上，看到一家新开的面包店呢。[smile01]", "本来想买牛角包的，结果居然全卖光了……[sigh]", "明天一定要更早去排队！[angry01]"]'
        segments = parse_ambient_story_segments(raw)
        self.assertEqual(len(segments), 3)
        self.assertEqual(segments[0]["text"], "今天排练完回去的路上，看到一家新开的面包店呢。")
        self.assertEqual(segments[0]["motion"], "smile01")
        self.assertEqual(segments[1]["text"], "本来想买牛角包的，结果居然全卖光了……")
        self.assertEqual(segments[1]["motion"], "sigh")
        self.assertEqual(segments[2]["text"], "明天一定要更早去排队！")
        self.assertEqual(segments[2]["motion"], "angry01")

    def test_parse_story_segments_layer1_markdown_codeblock(self):
        """Verify Layer 1 JSON array parsing wrapped in markdown code blocks."""
        raw = """```json
[
  "有咲，今天天气真好，去买个面包吧！[smile01]",
  "诶？你问为什么又是面包？因为好吃嘛！[shy]"
]
```"""
        segments = parse_ambient_story_segments(raw)
        self.assertEqual(len(segments), 2)
        self.assertEqual(segments[0]["text"], "有咲，今天天气真好，去买个面包吧！")
        self.assertEqual(segments[0]["motion"], "smile01")
        self.assertEqual(segments[1]["text"], "诶？你问为什么又是面包？因为好吃嘛！")
        self.assertEqual(segments[1]["motion"], "shy")

    def test_parse_story_segments_layer1_extra_text(self):
        """Verify Layer 1 parsing when extra text surrounds the JSON block."""
        raw = """这是生成的台词：
```json
[
  "刚才看到日菜了。[surprised]",
  "果然又拉着我说了一大堆关于吉他的事情。[sigh]"
]
```
希望满意！"""
        segments = parse_ambient_story_segments(raw)
        self.assertEqual(len(segments), 2)
        self.assertEqual(segments[0]["motion"], "surprised")
        self.assertEqual(segments[1]["motion"], "sigh")

    def test_parse_story_segments_layer2_numbered_fallback(self):
        """Verify Layer 2 fallback regex parsing when LLM outputs numbered items instead of JSON."""
        raw = """1. 今天在排练室练习了很久。[smile01]
2. 有咲又做好了美味的饼干给大家呢。[wink]
3. 下次还要一起继续加油！[kime]"""
        segments = parse_ambient_story_segments(raw)
        self.assertEqual(len(segments), 3)
        self.assertEqual(segments[0]["text"], "今天在排练室练习了很久。")
        self.assertEqual(segments[0]["motion"], "smile01")
        self.assertEqual(segments[1]["text"], "有咲又做好了美味的饼干给大家呢。")
        self.assertEqual(segments[1]["motion"], "wink")
        self.assertEqual(segments[2]["text"], "下次还要一起继续加油！")
        self.assertEqual(segments[2]["motion"], "kime")

    def test_parse_story_segments_layer2_chinese_numbering_and_dashes(self):
        """Verify Layer 2 fallback regex parsing for Chinese numbering and dash lists."""
        raw = """1、今天在河边练习吉他。[natural01]
2、微风吹过来感觉特别舒服。[smile01]"""
        segments = parse_ambient_story_segments(raw)
        self.assertEqual(len(segments), 2)
        self.assertEqual(segments[0]["text"], "今天在河边练习吉他。")
        self.assertEqual(segments[0]["motion"], "natural01")
        self.assertEqual(segments[1]["text"], "微风吹过来感觉特别舒服。")
        self.assertEqual(segments[1]["motion"], "smile01")

        raw_dashes = """- 第一段台词内容。[serious01]
- 第二段台词内容。[wink]"""
        segments_d = parse_ambient_story_segments(raw_dashes)
        self.assertEqual(len(segments_d), 2)
        self.assertEqual(segments_d[0]["text"], "第一段台词内容。")
        self.assertEqual(segments_d[0]["motion"], "serious01")

    def test_speech_bubble_hidden_signal(self):
        """Verify SpeechBubble emits bubble_hidden on hide()."""
        from pet_window import SpeechBubble
        bubble = SpeechBubble()
        emitted = []
        bubble.bubble_hidden.connect(lambda: emitted.append(True))
        bubble.hide()
        self.assertEqual(len(emitted), 1)

    def test_pet_window_continues_story_when_each_audio_clip_finishes(self):
        from pet_window import PetWindow

        with patch.object(PetWindow, "__init__", lambda self: None):
            pet = PetWindow()
            pet._cfg = {"ambient_proactive_chat_enabled": True}
            pet._current_char = "kasumi"
            pet._active_story_queue = []
            pet._tts_generation = 0
            pet._last_user_interaction_at = time.monotonic() - 30.0
            pet._last_ambient_proactive_spoken_at = time.monotonic() - 2000.0
            pet._ambient_proactive_cooldown_seconds = 1000.0
            pet.isVisible = MagicMock(return_value=True)
            pet._is_pet_dragging = MagicMock(return_value=False)
            pet._radial_menu = None
            pet._speech_bubble = MagicMock()
            pet._speech_bubble.isVisible.return_value = False
            pet._tts_player = MagicMock()
            pet._tts_player.is_idle.return_value = True
            pet._tts_player.enqueue.return_value = True
            pet._active_speech_worker = None
            pet._pet_bubble_anchor = MagicMock(return_value=(100, 100))
            pet._start_click_motion = MagicMock()
            pet._current_motion_names = MagicMock(
                return_value=["kasumi_natural01", "kasumi_smile01", "kasumi_thinking"],
            )

            audio = self._story_audio()
            segments = [
                {"text": "第一段", "motion": "smile01", "audio_bytes": audio},
                {"text": "第二段", "motion": "thinking", "expression": "surprised", "audio_bytes": audio},
                {"text": "第三段", "motion": "unknown", "audio_bytes": audio},
            ]
            pet._ambient_chat_manager = MagicMock()
            pet._ambient_chat_manager.pop_ambient_entry.return_value = {
                "is_story": True, "segments": segments,
            }

            pet._check_ambient_proactive_thought()

            pet._tts_player.enqueue.assert_called_once_with(audio, "wav")
            pet._speech_bubble.show_text.assert_called_once_with("第一段", (100, 100))
            pet._start_click_motion.assert_called_once_with("kasumi_smile01", "")
            self.assertEqual(
                [segment["motion"] for segment in pet._active_story_queue],
                ["kasumi_thinking", "kasumi_natural01"],
            )

            pet._ambient_chat_manager.pop_ambient_entry.reset_mock()
            pet._check_ambient_proactive_thought()
            pet._ambient_chat_manager.pop_ambient_entry.assert_not_called()

            pet._speech_bubble.isVisible.return_value = True
            pet._on_pet_tts_playback_finished()

            self.assertEqual(pet._tts_player.enqueue.call_count, 2)
            pet._speech_bubble.show_text.assert_called_with("第二段", (100, 100))
            pet._start_click_motion.assert_called_with("kasumi_thinking", "surprised")

            before_last_segment = time.monotonic()
            pet._on_pet_tts_playback_finished()

            self.assertEqual(
                pet._speech_bubble.show_text.call_args_list,
                [call("第一段", (100, 100)), call("第二段", (100, 100)), call("第三段", (100, 100))],
            )
            pet._start_click_motion.assert_called_with("kasumi_natural01", "")
            self.assertFalse(pet._active_story_queue)
            self.assertGreaterEqual(pet._last_ambient_proactive_spoken_at, before_last_segment)
            self.assertTrue(900.0 <= pet._ambient_proactive_cooldown_seconds <= 1500.0)

            pet._on_pet_tts_playback_finished()
            self.assertEqual(pet._tts_player.enqueue.call_args_list, [call(audio, "wav")] * 3)

    def test_user_interaction_aborts_remaining_story_segments(self):
        from pet_window import PetWindow

        with patch.object(PetWindow, "__init__", lambda self: None):
            pet = PetWindow()
            pet._active_story_queue = [{"text": "第二段", "audio_bytes": self._story_audio()}]
            pet._play_prepared_story_segment = MagicMock()

            pet._note_user_interaction()
            pet._on_pet_tts_playback_finished()

            self.assertFalse(pet._active_story_queue)
            pet._play_prepared_story_segment.assert_not_called()

    def test_ambient_prefetch_worker_story_mode_payload_and_parse(self):
        """Verify AmbientPrefetchWorker handles story_mode max_tokens and parses multi-segment entry."""
        cfg = {
            "llm_api_url": "https://api.test.com/v1/chat/completions",
            "llm_api_key": "test-key",
            "llm_model_id": "test-model",
            "ambient_tts_provider": "off",
            "tts_enabled": True,
            "tts_language": "Japanese",
        }

        worker = AmbientPrefetchWorker("kasumi", cfg, story_mode=True)
        results = []
        worker.fetched.connect(lambda char, entry: results.append((char, entry)))

        mock_resp_data = {
            "choices": [{
                "message": {
                    "content": '["第一句微故事[smile01]", "第二句微故事[wink]"]'
                }
            }]
        }

        audio = self._story_audio()
        with (
            patch("urllib.request.urlopen") as mock_urlopen,
            patch("ambient_chat_manager.gather_desktop_context", return_value={}),
            patch(
                "tts_manager.CachedTTSRequestWorker.load_or_generate_audio", return_value=audio,
            ) as synthesize,
        ):
            mock_cm = MagicMock()
            mock_cm.__enter__.return_value.read.return_value = json.dumps(mock_resp_data).encode("utf-8")
            mock_urlopen.return_value = mock_cm

            worker.run()

            self.assertEqual(synthesize.call_count, 2)
            request = mock_urlopen.call_args.args[0]
            self.assertEqual(json.loads(request.data)["max_tokens"], 384)
            self.assertEqual(len(results), 1)
            char, entry = results[0]
            self.assertEqual(char, "kasumi")
            self.assertTrue(entry.get("is_story"))
            self.assertEqual(len(entry.get("segments", [])), 2)
            self.assertEqual(entry["text"], "第一句微故事")
            self.assertEqual(entry["motion"], "smile01")
            self.assertEqual(entry["segments"][1]["text"], "第二句微故事")
            self.assertEqual(entry["segments"][1]["motion"], "wink")
            self.assertTrue(all(seg["audio_bytes"] == audio for seg in entry["segments"]))


    def test_realtime_story_keeps_chinese_text_and_uses_japanese_audio(self):
        cfg = {
            "llm_api_url": "https://api.openai.com/v1/responses",
            "llm_api_key": "test-key",
            "ambient_tts_provider": "realtime",
            "tts_enabled": False,
        }
        story = [
            {"text": "今天香澄把拨片夹头发里了。[surprised01]", "tts_text": "今日さ、香澄が髪にピック挟んでたんだよ。"},
            {"text": "她还找了整整半天。[sigh]", "tts_text": "それなのに、ずっと探してたんだよ。"},
        ]
        worker = AmbientPrefetchWorker("arisa", cfg, story_mode=True)
        entries = []
        worker.fetched.connect(lambda _, entry: entries.append(entry))
        audio = self._story_audio()
        with (
            patch("ambient_chat_manager.gather_desktop_context", return_value={}),
            patch("realtime_story_tts.post_openai_story_json", return_value={"output_text": json.dumps(story)}) as chat,
            patch("realtime_story_tts.prepare_realtime_story_audio", return_value=[audio, audio]) as voice,
            patch("tts_manager.CachedTTSRequestWorker.load_or_generate_audio") as sovits,
        ):
            worker.run()
            sovits.assert_not_called()
            self.assertIn("对应日文", chat.call_args.args[2]["input"][1]["content"].replace("的", ""))
            self.assertEqual(voice.call_args.args[0], [line["tts_text"] for line in story])
            self.assertEqual([line["motion"] for line in entries[0]["segments"]], ["surprised01", "sigh"])
            self.assertEqual(entries[0]["segments"][0]["text"], "今天香澄把拨片夹头发里了。")
            self.assertTrue(all(line["audio_bytes"] == audio for line in entries[0]["segments"]))

            entries.clear()
            voice.side_effect = TimeoutError
            worker.run()
            self.assertFalse(entries)

            voice.side_effect = None
            voice.return_value = [audio]
            worker.run()
            self.assertFalse(entries)

            voice.reset_mock()
            story[1]["tts_text"] = "这段没有日本语配音"
            chat.return_value = {"output_text": json.dumps(story)}
            worker.run()
            voice.assert_not_called()
            self.assertFalse(entries)

    def test_realtime_accumulates_pcm_and_requires_a_completed_response(self):
        import base64
        import io
        import wave
        from realtime_story_tts import RealtimeStorySpeech

        speech = RealtimeStorySpeech("test-key", lambda: False)
        pcm = b"\x10\x00" * 200
        audio_event = {"type": "response.output_audio.delta", "delta": base64.b64encode(pcm).decode()}
        with (
            patch.object(speech._socket, "sendTextMessage", return_value=100) as send,
            patch.object(speech, "_next_event", side_effect=[
                audio_event, audio_event, {"type": "response.done", "response": {"status": "completed"}},
                audio_event, {"type": "response.done", "response": {"status": "incomplete"}},
            ]),
        ):
            audio = speech.synthesize("それ、ちょっと待って。")
            body = json.loads(send.call_args.args[0])["response"]
            self.assertEqual(body["conversation"], "none")
            self.assertEqual(body["output_modalities"], ["audio"])
            self.assertEqual(body["input"][0]["content"][0]["text"], "それ、ちょっと待って。")
            with wave.open(io.BytesIO(audio), "rb") as wav:
                self.assertEqual(wav.getframerate(), 24000)
                self.assertEqual(wav.readframes(wav.getnframes()), pcm * 2)
            with self.assertRaisesRegex(ValueError, "Incomplete Realtime speech"):
                speech.synthesize("もう一回だよ。")

    def test_partial_tts_story_is_never_published(self):
        cfg = {
            "llm_api_url": "https://example.test/v1/chat/completions",
            "llm_api_key": "test-key",
            "ambient_tts_provider": "openai",
        }
        worker = AmbientPrefetchWorker("kasumi", cfg, story_mode=True)
        received = []
        worker.fetched.connect(lambda char, entry: received.append(entry))
        response = {"choices": [{"message": {"content": '["排练后有咲请我喝茶[smile01]", "我差点把糖碰翻了[troubled]"]'}}]}
        with (
            patch("ambient_chat_manager.gather_desktop_context", return_value={}),
            patch("urllib.request.urlopen") as chat,
            patch("tts_manager.openai_tts_cache_path") as cache,
            patch("ambient_chat_manager.tempfile.NamedTemporaryFile"),
            patch("ambient_chat_manager.os.replace"),
            patch("tts_manager.openai_tts_synthesize", side_effect=[self._story_audio(), None]) as synthesize,
        ):
            chat.return_value.__enter__.return_value.read.return_value = json.dumps(response).encode()
            cache.return_value.read_bytes.side_effect = FileNotFoundError
            worker.run()
        self.assertEqual(synthesize.call_count, 2)
        self.assertFalse(received)

    @staticmethod
    def _story_audio():
        import io
        import wave

        audio = io.BytesIO()
        with wave.open(audio, "wb") as stream:
            stream.setparams((1, 2, 8000, 0, "NONE", "not compressed"))
            stream.writeframes(b"\x10\x00" * 400)
        return audio.getvalue()

    def test_ready_story_waits_for_local_random_delay(self):
        manager = AmbientChatManager(None)
        self.addCleanup(manager.cleanup)
        audio = self._story_audio()
        story = {"is_story": True, "segments": [
            {"text": "起因", "motion": "natural01", "audio_bytes": audio},
            {"text": "结尾", "motion": "smile01", "audio_bytes": audio},
        ]}
        with (
            patch("ambient_chat_manager.time.monotonic", return_value=100.0) as now,
            patch("ambient_chat_manager.random.uniform", return_value=45.0),
            patch.object(manager, "trigger_prefetch"),
        ):
            manager._on_entry_fetched("kasumi", story)
            self.assertFalse(manager.pop_ambient_entry("kasumi"))
            now.return_value = 144.0
            self.assertFalse(manager.pop_ambient_entry("kasumi"))
            now.return_value = 145.0
            self.assertEqual(manager.pop_ambient_entry("kasumi")["segments"], story["segments"])
            self.assertFalse(manager.pop_ambient_entry("kasumi"))

            manually_started = []
            manager.manual_story_ready.connect(lambda char, entry: manually_started.append((char, entry)))
            manager._on_entry_fetched("kasumi", story)
            self.assertTrue(manager.request_story("kasumi"))
            self.assertEqual(manually_started, [("kasumi", story)])
            self.assertFalse(manager.pop_ambient_entry("kasumi"))

            self.assertFalse(manager.request_story("kasumi"))
            manager.trigger_prefetch.assert_called_with("kasumi", story_mode=True)
            manager._on_entry_fetched("kasumi", story)
            self.assertEqual(manually_started, [("kasumi", story), ("kasumi", story)])


if __name__ == "__main__":
    unittest.main()
