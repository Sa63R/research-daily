from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from csbaoyan_daily.app.generate import GenerateOptions, run_generate_report
from csbaoyan_daily.domain.file_utils import (
    extract_messages,
    get_json_file_by_date,
    infer_report_date,
    validate_chatlab_payload,
)


class JsonSourceTests(unittest.TestCase):
    def test_finds_date_only_chatlab_filename(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            export_dir = Path(directory)
            export_file = export_dir / "chatlab-2026-09-06.json"
            export_file.write_text("{}", encoding="utf-8")

            self.assertEqual(
                get_json_file_by_date(export_dir, "2026-09-06"),
                export_file,
            )

    def test_target_date_controls_output_when_payload_date_disagrees(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            export_dir = root / "exports"
            export_dir.mkdir()
            export_file = export_dir / "chat-2026-09-06T120000.json"
            export_file.write_text(
                json.dumps(
                    {
                        "chatlab": {"version": "0.0.2"},
                        "meta": {"name": "测试群", "platform": "QQ", "type": "group"},
                        "members": [],
                        "statistics": {"timeRange": {"end": "2026-09-05T23:59:59"}},
                        "messages": [
                            {
                                "platformMessageId": "1",
                                "sender": "u1",
                                "accountName": "群友甲",
                                "timestamp": 1788667200,
                                "type": 0,
                                "content": "一条测试消息",
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            with (
                patch(
                    "csbaoyan_daily.app.generate.previous_report_date",
                    return_value="2026-09-06",
                ),
                patch("csbaoyan_daily.app.generate.create_openai_client"),
                patch("csbaoyan_daily.app.generate.extract_all_chunks"),
                patch("csbaoyan_daily.app.generate.generate_final_report"),
            ):
                artifacts = run_generate_report(
                    GenerateOptions(
                        source="json",
                        export_dir=export_dir,
                        report_dir=root / "internal/reports",
                        api_key="test",
                        model="test",
                    )
                )

        self.assertEqual(artifacts.report_date, "2026-09-06")
        self.assertEqual(artifacts.report_path.name, "2026-09-06.md")

    def test_missing_or_invalid_metadata_does_not_guess_host_date(self) -> None:
        path = Path("undated.json")
        self.assertIsNone(infer_report_date({}, path))
        self.assertIsNone(
            infer_report_date(
                {"statistics": {"timeRange": {"end": "not-a-date"}}},
                path,
            )
        )

    def test_chatlab_messages_are_normalized_with_reply_context(self) -> None:
        payload = {
            "statistics": {
                "timeRange": {
                    "start": "2026-09-06T00:00:00+08:00",
                    "end": "2026-09-07T00:00:00+08:00",
                }
            },
            "members": [
                {
                    "platformId": "u1",
                    "accountName": "甲",
                    "groupNickname": "甲同学",
                },
                {
                    "platformId": "u2",
                    "accountName": "乙",
                    "groupNickname": "乙同学",
                },
            ],
            "messages": [
                {
                    "platformMessageId": "1",
                    "sender": "u1",
                    "accountName": "甲",
                    "groupNickname": "甲同学",
                    "timestamp": 1788624000,
                    "type": 0,
                    "content": "原消息",
                },
                {
                    "platformMessageId": "2",
                    "sender": "u2",
                    "accountName": "乙",
                    "groupNickname": "乙同学",
                    "timestamp": 1788624060,
                    "type": 25,
                    "content": "回复正文",
                    "replyToMessageId": "1",
                    "replyContext": {
                        "sender": "u1",
                        "accountName": "甲同学",
                        "timestamp": 1788624000,
                        "content": "原消息",
                    },
                },
            ],
        }

        messages = extract_messages(payload)

        self.assertEqual(messages[1]["id"], "2")
        self.assertEqual(
            messages[1]["content"]["text"],
            "[回复 甲同学: 原消息]\n回复正文",
        )
        self.assertEqual(
            messages[1]["content"]["elements"],
            [
                {
                    "type": "reply",
                    "data": {
                        "referencedMessageId": "1",
                        "senderName": "甲同学",
                        "content": "原消息",
                    },
                }
            ],
        )
        self.assertEqual(messages[1]["time"], "2026-09-06 00:01:00")

    def test_chatlab_range_start_controls_inferred_date(self) -> None:
        payload = {
            "statistics": {
                "timeRange": {
                    "start": "2026-09-06T00:00:00+08:00",
                    "end": "2026-09-07T00:00:00+08:00",
                }
            }
        }

        self.assertEqual(infer_report_date(payload, Path("chat.json")), "2026-09-06")

    def test_reply_context_survives_without_sender_identity(self) -> None:
        payload = {
            "statistics": {
                "timeRange": {"start": "2026-09-06T00:00:00+08:00"}
            },
            "members": [],
            "messages": [
                {
                    "platformMessageId": "2",
                    "sender": "u2",
                    "accountName": "乙",
                    "timestamp": 1788624060,
                    "type": 25,
                    "content": "回复正文",
                    "replyToMessageId": "outside-range",
                    "replyContext": {"content": "范围外的原消息"},
                }
            ],
        }

        messages = extract_messages(payload)

        self.assertEqual(
            messages[0]["content"]["text"],
            "[回复 未知用户: 范围外的原消息]\n回复正文",
        )

    def test_rejects_non_chatlab_input_at_the_public_boundary(self) -> None:
        with self.assertRaisesRegex(ValueError, "chatlab.version"):
            validate_chatlab_payload({"messages": []})


if __name__ == "__main__":
    unittest.main()
