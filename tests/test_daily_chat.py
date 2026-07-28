import json
import pathlib
import tempfile
import unittest

from daily_chat import (
    complete_daily_chat_entries,
    daily_chat_entries,
    daily_chat_tts_texts,
    daily_chat_texts,
)
from tools.import_daily_chat import (
    CHARACTER_NAME_TO_KEY,
    build_daily_chat_entries,
    normalize_character_name,
    parse_daily_chat_source,
    sync_daily_chat,
)


PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]


class DailyChatRuntimeTest(unittest.TestCase):
    def test_normalizes_string_and_object_entries(self):
        greetings = {
            "daily_chat": [
                "  plain text  ",
                {"text": "object text", "motion": "smile01", "expression": "happy"},
                {"text": "  "},
                123,
            ]
        }

        self.assertEqual(
            daily_chat_entries(greetings),
            [
                {"text": "plain text", "tts_text": "plain text", "motion": "", "expression": ""},
                {"text": "object text", "tts_text": "object text", "motion": "smile01", "expression": "happy"},
            ],
        )
        self.assertEqual(
            daily_chat_texts(greetings),
            ["plain text", "object text"],
        )
        self.assertEqual(
            daily_chat_tts_texts(greetings),
            ["plain text", "object text"],
        )

    def test_keeps_pretranslated_tts_text_separate_from_display_text(self):
        greetings = {
            "daily_chat": [
                {"text": "中文气泡", "tts_text": "日本語の音声"},
            ]
        }

        self.assertEqual(daily_chat_texts(greetings), ["中文气泡"])
        self.assertEqual(daily_chat_tts_texts(greetings), ["日本語の音声"])

    def test_rejects_non_list_daily_chat_value(self):
        self.assertEqual(daily_chat_entries({"daily_chat": "not a list"}), [])

    def test_incomplete_or_duplicate_pool_falls_back(self):
        incomplete = {"daily_chat": [f"line {index}" for index in range(11)]}
        duplicate = {"daily_chat": ["same line"] * 12}
        extra_invalid = {
            "daily_chat": [f"line {index}" for index in range(12)] + [None]
        }
        complete = {"daily_chat": [f"line {index}" for index in range(12)]}

        self.assertEqual(complete_daily_chat_entries(incomplete), [])
        self.assertEqual(complete_daily_chat_entries(duplicate), [])
        self.assertEqual(complete_daily_chat_entries(extra_invalid), [])
        self.assertEqual(len(complete_daily_chat_entries(complete)), 12)

    def test_all_40_character_files_have_24_unique_daily_lines(self):
        keys = tuple(CHARACTER_NAME_TO_KEY.values())
        self.assertEqual(len(keys), 40)
        self.assertEqual(len(set(keys)), 40)

        for key in keys:
            with self.subTest(character=key):
                path = PROJECT_ROOT / "characters" / key / "greetings.json"
                greetings = json.loads(path.read_text(encoding="utf-8"))
                texts = daily_chat_texts(greetings)
                self.assertEqual(len(texts), 24)
                self.assertEqual(len(set(texts)), 24)

    def test_kokoro_and_aya_keep_their_japanese_signature_lines(self):
        expected_lines = {
            "kokoro": "ハッピー！ラッキー！スマイル！イェーイ！",
            "aya": "まんまるお山に彩りを！丸山彩です！",
        }

        for key, expected_line in expected_lines.items():
            with self.subTest(character=key):
                path = PROJECT_ROOT / "characters" / key / "greetings.json"
                greetings = json.loads(path.read_text(encoding="utf-8"))
                texts = daily_chat_texts(greetings)
                self.assertTrue(any(expected_line in text for text in texts))


class DailyChatImporterTest(unittest.TestCase):
    def test_normalizes_stage_names_and_the_soyo_name_variant(self):
        self.assertEqual(normalize_character_name("和奏瑞依（LAYER）"), "和奏瑞依")
        self.assertEqual(normalize_character_name("朝日六花（LOCK）"), "朝日六花")
        self.assertEqual(normalize_character_name("长崎爽世"), "长崎素世")

    def test_parser_requires_exactly_12_lines_per_character(self):
        fixture = ["【户山香澄】"]
        fixture.extend(f"香澄台词 {index}" for index in range(12))
        fixture.extend(["", "================", "【长崎爽世】"])
        fixture.extend(f"素世台词 {index}" for index in range(12))

        with tempfile.TemporaryDirectory() as temp_dir:
            path = pathlib.Path(temp_dir) / "daily.txt"
            path.write_text("\n".join(fixture), encoding="utf-8")
            parsed = parse_daily_chat_source(
                path,
                name_to_key={"户山香澄": "kasumi", "长崎素世": "soyo"},
            )

        self.assertEqual(len(parsed["kasumi"]), 12)
        self.assertEqual(parsed["soyo"][0], "素世台词 0")

    def test_build_entries_cycles_only_neutral_existing_actions(self):
        greetings = {
            "click_responses": [
                {"motion": "angry01", "lines": ["old"]},
                {"motion": "natural01", "expression": "calm", "lines": ["old"]},
                {"motion": "smile01", "lines": ["old"]},
            ]
        }
        lines = [f"line {index}" for index in range(12)]

        entries = build_daily_chat_entries(greetings, lines)

        self.assertEqual(len(entries), 12)
        self.assertEqual(
            {entry.get("motion") for entry in entries},
            {"natural01", "smile01"},
        )
        self.assertNotIn("angry01", {entry.get("motion") for entry in entries})
        self.assertEqual(entries[0]["expression"], "calm")

    def test_build_entries_uses_no_action_when_no_neutral_action_exists(self):
        greetings = {
            "click_responses": [
                {"motion": "angry01", "lines": ["old"]},
                {"motion": 123, "expression": ["bad"], "lines": ["old"]},
            ]
        }

        entries = build_daily_chat_entries(
            greetings,
            [f"line {index}" for index in range(12)],
        )

        self.assertTrue(all(set(entry) == {"text"} for entry in entries))

    def test_parser_rejects_action_tags(self):
        fixture = ["\u3010Alice\u3011", "[smile] tagged line"]
        fixture.extend(f"line {index}" for index in range(11))

        with tempfile.TemporaryDirectory() as temp_dir:
            path = pathlib.Path(temp_dir) / "daily.txt"
            path.write_text("\n".join(fixture), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "action tag"):
                parse_daily_chat_source(path, name_to_key={"Alice": "alice"})

    def test_sync_validates_all_targets_before_writing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            first_path = root / "characters" / "first" / "greetings.json"
            first_path.parent.mkdir(parents=True)
            original = {"click_responses": [{"motion": "smile01", "lines": ["old"]}]}
            first_path.write_text(json.dumps(original), encoding="utf-8")
            parsed = {
                "first": [f"first {index}" for index in range(12)],
                "missing": [f"missing {index}" for index in range(12)],
            }

            with self.assertRaises(FileNotFoundError):
                sync_daily_chat(root, parsed)

            self.assertEqual(
                json.loads(first_path.read_text(encoding="utf-8")),
                original,
            )


if __name__ == "__main__":
    unittest.main()
