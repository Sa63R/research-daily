from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from csbaoyan_daily.app.generate import GenerateOptions, run_generate_report
from csbaoyan_daily.domain.file_utils import infer_report_date


class JsonSourceTests(unittest.TestCase):
    def test_target_date_controls_output_when_payload_date_disagrees(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            export_dir = root / "exports"
            export_dir.mkdir()
            export_file = export_dir / "chat-2026-09-06T120000.json"
            export_file.write_text(
                json.dumps(
                    {
                        "statistics": {"timeRange": {"end": "2026-09-05T23:59:59"}},
                        "messages": [
                            {
                                "id": "1",
                                "time": "2026-09-06 12:00:00",
                                "sender": {"uid": "u1", "name": "群友甲"},
                                "content": {"text": "一条测试消息"},
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


if __name__ == "__main__":
    unittest.main()
