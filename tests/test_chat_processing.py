import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from csbaoyan_daily.domain.chat_processing import anonymize_messages


class ChatProcessingTests(unittest.TestCase):
    def test_structured_mention_replacement_handles_adjacent_chinese_text(self) -> None:
        messages = [
            {
                "id": "target",
                "time": "2026-09-07 08:00:00",
                "sender": {"uid": "1", "uin": "1", "name": "周丽峰"},
                "content": {"text": "我说了一句话", "mentions": [], "elements": []},
            },
            {
                "id": "reply",
                "time": "2026-09-07 08:01:00",
                "sender": {"uid": "2", "uin": "2", "name": "回复者"},
                "content": {
                    "text": "[回复]@周丽峰全是九",
                    "mentions": [
                        {"uid": "1", "uin": "1", "name": "周丽峰"}
                    ],
                    "elements": [
                        {
                            "type": "at",
                            "data": {"uid": "1", "uin": "1", "name": "周丽峰"},
                        }
                    ],
                },
            },
        ]

        anonymized = anonymize_messages(messages)

        self.assertEqual(anonymized[1].text, "[回复]@User_1全是九")

    def test_structured_mention_replaces_the_complete_hyphenated_name(self) -> None:
        messages = [
            {
                "id": "target",
                "time": "2026-09-07 08:00:00",
                "sender": {
                    "uid": "10001",
                    "uin": "10001",
                    "name": "317-sdu-羊宫妃那",
                },
                "content": {"text": "我说了一句话", "mentions": [], "elements": []},
            },
            {
                "id": "reply",
                "time": "2026-09-07 08:01:00",
                "sender": {"uid": "10002", "uin": "10002", "name": "回复者"},
                "content": {
                    "text": "[回复]@317-sdu-羊宫妃那前面偷懒",
                    "mentions": [
                        {
                            "uid": "10001",
                            "uin": "10001",
                            "name": "317-sdu-羊宫妃那",
                        }
                    ],
                    "elements": [],
                },
            },
        ]

        anonymized = anonymize_messages(messages)

        self.assertEqual(anonymized[1].text, "[回复]@User_1前面偷懒")

    def test_structured_mention_without_rendered_name_replaces_at_marker(self) -> None:
        messages = [
            {
                "id": "target",
                "time": "2026-09-07 08:00:00",
                "sender": {"uid": "1", "uin": "1", "name": "目标用户"},
                "content": {"text": "原消息", "mentions": [], "elements": []},
            },
            {
                "id": "reply",
                "time": "2026-09-07 08:01:00",
                "sender": {"uid": "2", "uin": "2", "name": "回复者"},
                "content": {
                    "text": "[回复]@后续内容",
                    "mentions": [{"uid": "1", "uin": "1", "name": ""}],
                    "elements": [],
                },
            }
        ]

        anonymized = anonymize_messages(messages)

        self.assertEqual(anonymized[1].text, "[回复]@User_1后续内容")


if __name__ == "__main__":
    unittest.main()
