import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from csbaoyan_daily.domain.chat_processing import (
    AnonymizedMessage,
    ChatChunk,
    anonymize_messages,
)


class ChatProcessingTests(unittest.TestCase):
    def test_same_day_chunk_repeats_date_only_in_chunk_context(self) -> None:
        chunk = ChatChunk(
            index=1,
            messages=[
                AnonymizedMessage("M00001", "2026-09-08 08:01:02", "User_1", "消息一"),
                AnonymizedMessage("M00002", "2026-09-08 08:03:04", "User_2", "消息二"),
            ],
        )

        self.assertEqual(chunk.common_date, "2026-09-08")
        self.assertIn("[M00001] [08:01:02]", chunk.prompt_text)
        self.assertNotIn("2026-09-08", chunk.prompt_text)
        self.assertIn("2026-09-08", chunk.text)

    def test_cross_day_chunk_keeps_full_timestamps(self) -> None:
        chunk = ChatChunk(
            index=1,
            messages=[
                AnonymizedMessage("M00001", "2026-09-08 23:59:59", "User_1", "消息一"),
                AnonymizedMessage("M00002", "2026-09-09 00:00:01", "User_2", "消息二"),
            ],
        )

        self.assertIsNone(chunk.common_date)
        self.assertEqual(chunk.prompt_text, chunk.text)

    def test_noise_is_filtered_and_message_refs_remain_stable(self) -> None:
        messages = [
            {
                "id": "normal",
                "time": "2026-09-07 08:00:00",
                "message_type": 0,
                "sender": {"uid": "12", "uin": "12", "name": "12"},
                "content": {"text": "12点开始讨论", "mentions": [], "elements": []},
            },
            {
                "id": "system",
                "time": "2026-09-07 08:01:00",
                "message_type": "81",
                "sender": {"uid": "99", "uin": "99", "name": "系统"},
                "content": {"text": "某人加入了群聊", "mentions": [], "elements": []},
            },
            {
                "id": "image",
                "time": "2026-09-07 08:02:00",
                "message_type": 1,
                "sender": {"uid": "3", "uin": "3", "name": "图片发送者"},
                "content": {"text": "[图片：截图]", "mentions": [], "elements": []},
            },
            {
                "id": "mixed",
                "time": "2026-09-07 08:03:00",
                "message_type": 0,
                "sender": {"uid": "4", "uin": "4", "name": "群友"},
                "content": {
                    "text": "请看[消息类型 1]这个通知",
                    "mentions": [],
                    "elements": [],
                },
            },
        ]

        anonymized = anonymize_messages(messages)

        self.assertEqual([message.ref for message in anonymized], ["M00001", "M00002"])
        self.assertEqual(anonymized[0].text, "12点开始讨论")
        self.assertEqual(anonymized[1].text, "请看这个通知")
        self.assertTrue(anonymized[0].to_line().startswith("[M00001] [2026-09-07 08:00:00]"))

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
