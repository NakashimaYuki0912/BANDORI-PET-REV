import unittest
from unittest.mock import MagicMock, patch
import os
import sys
import io

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from tts_manager import openai_tts_synthesize, openai_tts_cache_path
from ambient_chat_manager import AmbientPrefetchWorker
from PySide6.QtWidgets import QApplication

class TestOpenAITTS(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not QApplication.instance():
            cls.app = QApplication([])

    def test_openai_tts_cache_path(self):
        config = {
            "openai_tts_voice": "nova",
            "openai_tts_model": "tts-1-hd",
            "openai_tts_speed": 1.1,
        }
        p1 = openai_tts_cache_path("你好世界", "kasumi", config)
        p2 = openai_tts_cache_path("你好世界", "kasumi", config)
        p3 = openai_tts_cache_path("你好世界", "yukina", config)
        self.assertEqual(p1, p2)
        self.assertNotEqual(p1, p3)
        self.assertTrue(str(p1).endswith(".mp3"))

    @patch("urllib.request.urlopen")
    def test_openai_tts_synthesize_success(self, mock_urlopen):
        fake_mp3 = b"ID3" + b"\x00" * 150
        mock_resp = MagicMock()
        mock_resp.read.return_value = fake_mp3
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        config = {
            "openai_tts_api_url": "https://api.openai.com/v1",
            "openai_tts_api_key": "sk-test123456",
            "openai_tts_voice": "alloy",
            "openai_tts_model": "tts-1",
        }
        res = openai_tts_synthesize("今天天气真好", config)
        self.assertIsNotNone(res)
        self.assertEqual(res, fake_mp3)

    def test_openai_tts_synthesize_no_key(self):
        config = {
            "openai_tts_api_url": "https://api.openai.com/v1",
            "openai_tts_api_key": "",
            "llm_api_key": "",
        }
        res = openai_tts_synthesize("今天天气真好", config)
        self.assertIsNone(res)

    @patch("urllib.request.urlopen")
    def test_ambient_prefetch_worker_with_openai_tts(self, mock_urlopen):
        fake_llm_resp = io.BytesIO(b'{"choices": [{"message": {"content": "\xe4\xbb\x8a\xe5\xa4\xa9\xe4\xb9\x9f\xe8\xa6\x81\xe5\x8a\xa0\xe6\xb2\xb9\xe5\x95\xa6\xef\xbc\x81[smile01]"}}]}')
        fake_mp3_resp = io.BytesIO(b"ID3" + b"\x00" * 150)

        # First call is LLM chat completion, second call is OpenAI TTS
        mock_urlopen.side_effect = [fake_llm_resp, fake_mp3_resp]

        cfg = {
            "llm_api_url": "https://api.openai.com/v1/chat/completions",
            "llm_api_key": "sk-test",
            "llm_model_id": "gpt-4o-mini",
            "ambient_tts_provider": "openai",
            "openai_tts_api_key": "sk-test",
        }
        worker = AmbientPrefetchWorker("kasumi", cfg)
        fetched_entries = []
        worker.fetched.connect(lambda char, entry: fetched_entries.append((char, entry)))

        worker.run()
        self.assertEqual(len(fetched_entries), 1)
        char, entry = fetched_entries[0]
        self.assertEqual(char, "kasumi")
        self.assertEqual(entry["text"], "今天也要加油啦！")
        self.assertEqual(entry["motion"], "smile01")
        self.assertIn("audio_bytes", entry)
        self.assertEqual(entry["audio_format"], "mp3")
        self.assertTrue(len(entry["audio_bytes"]) > 100)

if __name__ == "__main__":
    unittest.main()
