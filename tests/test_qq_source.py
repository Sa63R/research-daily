import datetime as dt
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from csbaoyan_daily.infra.qq_source import QQSourceOptions, read_qq_messages


class QQSourceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.options = QQSourceOptions(
            command=Path("/tmp/qqnt-export-macos"),
            key_path=Path("/tmp/database.key"),
            cache_dir=Path("/tmp/cache"),
            conversation_id="group:943826679",
        )

    def test_paginates_filters_boundaries_and_deduplicates(self) -> None:
        pages = [
            {
                "messages": [
                    {
                        "conversation_id": "group:943826679",
                        "message_id": "2",
                        "timestamp": 1788710400,
                        "sender": "甲",
                        "sender_number": "10002",
                        "content": "次日零点，不应包含",
                    },
                    {
                        "conversation_id": "group:943826679",
                        "message_id": "1",
                        "timestamp": 1788624000,
                        "sender": "乙",
                        "sender_number": "10001",
                        "content": "当日零点，应包含",
                    },
                ],
                "has_more": True,
                "next_cursor": "cursor-1",
            },
            {
                "messages": [
                    {
                        "conversation_id": "group:943826679",
                        "message_id": "1",
                        "timestamp": 1788624000,
                        "sender": "乙",
                        "sender_number": "10001",
                        "content": "重复消息",
                    },
                    {
                        "conversation_id": "group:943826679",
                        "message_id": "0",
                        "timestamp": 1788623999,
                        "sender": "丙",
                        "sender_number": "10000",
                        "content": "前一天，不应包含",
                    },
                ],
                "has_more": False,
                "next_cursor": None,
            },
        ]
        now = dt.datetime(2026, 9, 7, 6, 30, tzinfo=dt.timezone(dt.timedelta(hours=8)))

        with patch("csbaoyan_daily.infra.qq_source._run_page", side_effect=pages) as run_page:
            messages = read_qq_messages(self.options, "2026-09-06", now=now)

        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]["id"], "1")
        self.assertEqual(messages[0]["sender"]["uin"], "10001")
        self.assertEqual(messages[0]["content"]["text"], "重复消息")
        self.assertEqual(run_page.call_args_list[0].args[1:], (1831, None))
        self.assertEqual(run_page.call_args_list[1].args[1:], (1831, "cursor-1"))

    def test_empty_or_unreadable_messages_return_empty(self) -> None:
        page = {
            "messages": [
                {
                    "conversation_id": "group:943826679",
                    "message_id": "1",
                    "timestamp": 1788624000,
                    "sender": "甲",
                    "sender_number": "1",
                    "content": "[无正文]",
                }
            ],
            "has_more": False,
        }
        with patch("csbaoyan_daily.infra.qq_source._run_page", return_value=page):
            result = read_qq_messages(
                self.options,
                "2026-09-06",
                now=dt.datetime(2026, 9, 7, tzinfo=dt.timezone(dt.timedelta(hours=8))),
            )
        self.assertEqual(result, [])

    def test_rejects_repeated_cursor(self) -> None:
        page = {"messages": [], "has_more": True, "next_cursor": "same"}
        with patch("csbaoyan_daily.infra.qq_source._run_page", return_value=page):
            with self.assertRaisesRegex(RuntimeError, "游标"):
                read_qq_messages(
                    self.options,
                    "2026-09-06",
                    now=dt.datetime(2026, 9, 7, tzinfo=dt.timezone(dt.timedelta(hours=8))),
                )


if __name__ == "__main__":
    unittest.main()
