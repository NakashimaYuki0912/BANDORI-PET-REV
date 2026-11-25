"""Regression coverage for ordered chat-TTS prefetching without GUI imports."""

import ast
import unittest
from pathlib import Path


def _window_method(class_name: str, name: str, file_name: str = "chat_window.py", extra_ns: dict | None = None):
    source = Path(__file__).resolve().parents[1] / file_name
    tree = ast.parse(source.read_text(encoding="utf-8"))
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == class_name)
    method = next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == name)
    module = ast.Module(body=[method], type_ignores=[])
    ast.fix_missing_locations(module)
    namespace = {"TTSRequestWorker": _FakeWorker}
    if extra_ns:
        namespace.update(extra_ns)
    exec(compile(module, str(source), "exec"), namespace)
    return namespace[name]


def _chat_window_method(name: str):
    return _window_method("ChatWindow", name, "chat_window.py")


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


class CompactAiTtsQueueTest(unittest.TestCase):
    def test_compact_ai_window_serializes_workers_and_streams_multiple_chunks_in_order(self):
        speak = _window_method(
            "CompactAIWindow",
            "_speak_tts_text",
            "compact_ai_window.py",
            {"split_tts_segments": lambda text: ["seg0", "seg1"]},
        )
        start_next = _window_method("CompactAIWindow", "_start_next_tts_worker", "compact_ai_window.py")
        on_ready = _window_method("CompactAIWindow", "_on_tts_audio_ready", "compact_ai_window.py")
        enqueue_ready = _window_method("CompactAIWindow", "_enqueue_ready_tts_audio", "compact_ai_window.py")
        on_finished = _window_method("CompactAIWindow", "_on_tts_worker_finished", "compact_ai_window.py")
        _FakeWorker.started_sequences.clear()

        enqueued = []

        class Player:
            def enqueue(self, audio, media_type):
                enqueued.append((audio, media_type))

        class Window:
            _tts_workers = {}
            _tts_worker = None
            _tts_pending_segments = []
            _tts_pending_audio = {}
            _tts_completed_sequences = set()
            _tts_next_enqueue_sequence = 0
            _tts_total_sequences = 0
            _tts_generation = 0
            _tts_playing_character = ""
            _tts_player = Player()
            _current_sender = None

            def _tts_enabled(self):
                return True

            def _clean_tts_payload(self, text):
                return text

            def _reset_tts(self, stop_player=True):
                del stop_player
                self._tts_generation += 1
                self._tts_workers.clear()
                self._tts_pending_segments.clear()
                self._tts_pending_audio.clear()
                self._tts_completed_sequences.clear()
                self._tts_next_enqueue_sequence = 0

            def _tts_config_snapshot(self):
                return {}

            def _start_next_tts_worker(self):
                start_next(self)

            def _on_tts_audio_ready(self, seq, gen, audio, fmt):
                on_ready(self, seq, gen, audio, fmt)

            def _enqueue_ready_tts_audio(self):
                enqueue_ready(self)

            def _on_tts_error(self, msg):
                pass

            def _on_tts_worker_finished(self):
                on_finished(self)

            def sender(self):
                return self._current_sender

        win = Window()
        speak(win, "seg0。seg1。", "arisa")

        # Only sequence 0 starts immediately; sequence 1 waits in _tts_pending_segments
        self.assertEqual(_FakeWorker.started_sequences, [0])
        self.assertEqual(len(win._tts_pending_segments), 1)

        # Sequence 0 streams two chunks before finishing
        w0 = win._tts_workers[0]
        win._current_sender = w0
        on_ready(win, 0, win._tts_generation, b"chunk0a", "wav")
        on_ready(win, 0, win._tts_generation, b"chunk0b", "wav")
        self.assertEqual(enqueued, [(b"chunk0a", "wav"), (b"chunk0b", "wav")])
        self.assertEqual(win._tts_next_enqueue_sequence, 0)

        # When sequence 0 finishes, sequence 1 starts and plays next
        on_finished(win)
        self.assertEqual(win._tts_next_enqueue_sequence, 1)
        self.assertEqual(_FakeWorker.started_sequences, [0, 1])

        w1 = win._tts_workers[1]
        win._current_sender = w1
        on_ready(win, 1, win._tts_generation, b"chunk1a", "wav")
        on_finished(win)
        self.assertEqual(enqueued, [(b"chunk0a", "wav"), (b"chunk0b", "wav"), (b"chunk1a", "wav")])
        self.assertEqual(win._tts_next_enqueue_sequence, 2)
