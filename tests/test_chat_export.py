from __future__ import annotations

import datetime as dt
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from csbaoyan_daily.infra.chat_export import ChatExportOptions, export_chatlab_day


class ChatExportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.options = ChatExportOptions(
            command=Path("qqnt-export-macos"),
            key_path=Path("/tmp/database.key"),
            cache_dir=Path("/tmp/cache"),
            conversation_id="group:943826679",
        )

    def test_exports_one_completed_day_to_chatlab_json(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            export_dir = Path(directory) / "exports"
            destination = export_dir / "chatlab-2026-09-06.json"
            destination.parent.mkdir()
            destination.write_text('{"messages": []}\n', encoding="utf-8")
            now = dt.datetime(
                2026, 9, 7, 6, 30, tzinfo=dt.timezone(dt.timedelta(hours=8))
            )
            with patch(
                "csbaoyan_daily.infra.chat_export.subprocess.run",
                return_value=subprocess.CompletedProcess([], 0, "", ""),
            ) as run:
                result = export_chatlab_day(
                    self.options,
                    "2026-09-06",
                    export_dir,
                    now=now,
                )

        self.assertEqual(result.name, "chatlab-2026-09-06.json")
        command = run.call_args.args[0]
        self.assertIn("export-chatlab", command)
        self.assertEqual(command[command.index("--date") + 1], "2026-09-06")
        self.assertEqual(command[command.index("--conversation") + 1], "group:943826679")
        self.assertIn("--overwrite", command)

    def test_rejects_a_day_that_has_not_finished(self) -> None:
        with self.assertRaisesRegex(ValueError, "尚未结束"):
            export_chatlab_day(
                self.options,
                "2026-09-06",
                Path("/tmp/exports"),
                now=dt.datetime(
                    2026, 9, 6, 23, 59, tzinfo=dt.timezone(dt.timedelta(hours=8))
                ),
            )

    def test_surfaces_exporter_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch(
            "csbaoyan_daily.infra.chat_export.subprocess.run",
            return_value=subprocess.CompletedProcess([], 2, "", "broken exporter"),
        ):
            with self.assertRaisesRegex(RuntimeError, "broken exporter"):
                export_chatlab_day(
                    self.options,
                    "2026-09-06",
                    Path(directory) / "exports",
                    now=dt.datetime(
                        2026, 9, 7, 1, tzinfo=dt.timezone(dt.timedelta(hours=8))
                    ),
                )


if __name__ == "__main__":
    unittest.main()
