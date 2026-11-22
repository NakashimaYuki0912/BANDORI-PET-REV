import unittest

from llm_manager import _messages_to_responses_input


class ResponsesInputTest(unittest.TestCase):
    def test_multiturn_roles_and_image(self):
        instructions, items = _messages_to_responses_input([
            {"role": "system", "content": "Be helpful"},
            {"role": "developer", "content": "Be concise"},
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi"},
            {"role": "user", "content": [
                {"type": "text", "text": "What is this?"},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}},
            ]},
        ])
        self.assertEqual(instructions, "Be helpful")
        self.assertEqual(items, [
            {"role": "developer", "content": [{"type": "input_text", "text": "Be concise"}]},
            {"role": "user", "content": [{"type": "input_text", "text": "Hello"}]},
            {"role": "assistant", "content": [{"type": "output_text", "text": "Hi"}]},
            {"role": "user", "content": [
                {"type": "input_text", "text": "What is this?"},
                {"type": "input_image", "image_url": "data:image/png;base64,abc"},
            ]},
        ])

    def test_assistant_list_and_empty_content(self):
        _, items = _messages_to_responses_input([
            {"role": "assistant", "content": [{"type": "text", "text": "Hi"}]},
            {"role": "assistant", "content": []},
        ])
        self.assertEqual(items[0]["content"], [{"type": "output_text", "text": "Hi"}])
        self.assertEqual(items[1]["content"], [{"type": "output_text", "text": ""}])


if __name__ == "__main__":
    unittest.main()
