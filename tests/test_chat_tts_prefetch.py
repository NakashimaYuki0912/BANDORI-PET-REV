"""Regression coverage for ordered chat-TTS prefetching without GUI imports."""

import ast
import unittest
from pathlib import Path


def _chat_window_method(name: str):
    source = Path(__file__).resolve().parents[1] / "chat_window.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    chat_window = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "ChatWindow")
    method = next(node for node in chat_window.body if isinstance(node, ast.FunctionDef) and node.name == name)
    module = ast.Module(body=[method], type_ignores=[])
    ast.fix_missing_locations(module)
    namespace = {"TTSRequestWorker": _FakeWorker}
    exec(compile(module, str(source), "exec"), namespace)
    return namespace[name]


class _Signal:
    def connect(self, _slot):
        pass


class _FakeWorker:
    started_sequences: list[int] = []

    def __init__(self, sequence, generation, text, character, config, parent):
        self.sequence = sequence
        self.generation = generation
        self.audio_ready = _Signal()
        self.error = _Signal()
        self.finished = _Signal()

    def start(self):
        self.started_sequences.append(self.sequence)


class _PlayingPlayer:
    def is_idle(self):
        return False


class ChatTtsPrefetchTest(unittest.TestCase):
    def test_prefetches_next_sentence_while_current_sentence_is_playing(self):
        start_next = _chat_window_method("_start_next_tts_request")
        _FakeWorker.started_sequences.clear()

        class Window:
            _tts_active_workers = {}
            _tts_playing_sequence = 0
            _tts_player = _PlayingPlayer()
            _tts_queue = [(1, "second sentence", "lisa")]
            _tts_next_play_sequence = 0
            _tts_next_request_sequence = 1
            _tts_generation = 7
            _tts_max_parallel = 1

            def _tts_config_snapshot(self):
                return {}

            def _on_tts_audio_ready(self):
                pass

            def _on_tts_error(self):
                pass

            def _on_tts_worker_finished(self):
                pass

        window = Window()
        start_next(window)

        self.assertEqual(_FakeWorker.started_sequences, [1])
        self.assertIn(1, window._tts_active_workers)

    def test_chat_tts_snapshot_keeps_voice_profile_settings(self):
        snapshot = _chat_window_method("_tts_config_snapshot")

        class Config:
            values = {
                "tts_speed_factor": 0.88,
                "tts_character_profiles": {"lisa": {"speed_factor": 0.86}},
            }

            def get(self, key, default=None):
                return self.values.get(key, default)

        class Window:
            _cfg = Config()

        result = snapshot(Window())

        self.assertEqual(result["tts_speed_factor"], 0.88)
        self.assertEqual(result["tts_character_profiles"]["lisa"]["speed_factor"], 0.86)

    def test_prefetch_respects_the_single_request_limit(self):
        start_next = _chat_window_method("_start_next_tts_request")
        _FakeWorker.started_sequences.clear()

        class Window:
            _tts_active_workers = {0: object()}
            _tts_playing_sequence = 0
            _tts_player = _PlayingPlayer()
            _tts_queue = [(1, "second sentence", "lisa")]
            _tts_next_play_sequence = 0
            _tts_next_request_sequence = 1
            _tts_generation = 7
            _tts_max_parallel = 1

            def _tts_config_snapshot(self):
                return {}

            def _on_tts_audio_ready(self):
                pass

            def _on_tts_error(self):
                pass

            def _on_tts_worker_finished(self):
                pass

        start_next(Window())

        self.assertEqual(_FakeWorker.started_sequences, [])
