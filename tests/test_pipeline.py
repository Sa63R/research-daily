import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from csbaoyan_daily.app.generate import NoMessagesForDate
from csbaoyan_daily.app.pipeline import PipelineOptions, run_pipeline
from csbaoyan_daily.infra.r2 import R2PublishResult


class PipelineTests(unittest.TestCase):
    def test_skip_upload_avoids_publish_and_broadcast(self) -> None:
        options = PipelineOptions(
            repo_root=Path.cwd(),
            date="2026-05-18",
            skip_generate=True,
            skip_release_check=True,
            skip_upload=True,
        )

        with patch("csbaoyan_daily.app.pipeline.run_publish") as mocked_publish, patch(
            "csbaoyan_daily.app.pipeline.broadcast_report"
        ) as mocked_broadcast:
            resolved_date = run_pipeline(options)

        self.assertEqual(resolved_date, "2026-05-18")
        mocked_publish.assert_not_called()
        mocked_broadcast.assert_not_called()

    def test_no_messages_skips_check_publish_and_broadcast(self) -> None:
        options = PipelineOptions(repo_root=Path.cwd(), date="2026-05-18")
        with patch(
            "csbaoyan_daily.app.pipeline.run_generate_report",
            side_effect=NoMessagesForDate("2026-05-18"),
        ), patch("csbaoyan_daily.app.pipeline.run_report_check") as mocked_check, patch(
            "csbaoyan_daily.app.pipeline.run_publish"
        ) as mocked_publish, patch(
            "csbaoyan_daily.app.pipeline.broadcast_report"
        ) as mocked_broadcast:
            resolved_date = run_pipeline(options)

        self.assertEqual(resolved_date, "2026-05-18")
        mocked_check.assert_not_called()
        mocked_publish.assert_not_called()
        mocked_broadcast.assert_not_called()

    def test_successful_publish_triggers_broadcast(self) -> None:
        options = PipelineOptions(
            repo_root=Path.cwd(),
            date="2026-05-18",
            skip_generate=True,
            skip_release_check=True,
        )
        result = R2PublishResult(
            report_date="2026-05-18",
            report_count=68,
            uploaded_reports=1,
        )

        with patch(
            "csbaoyan_daily.app.pipeline.run_publish", return_value=result
        ) as mocked_publish, patch(
            "csbaoyan_daily.app.pipeline.broadcast_report", return_value=True
        ) as mocked_broadcast:
            resolved_date = run_pipeline(options)

        self.assertEqual(resolved_date, "2026-05-18")
        mocked_publish.assert_called_once()
        mocked_broadcast.assert_called_once()


if __name__ == "__main__":
    unittest.main()
