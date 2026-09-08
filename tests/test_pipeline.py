import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from csbaoyan_daily.app.generate import NoMessagesForDate
from csbaoyan_daily.app.pipeline import PipelineOptions, run_pipeline
from csbaoyan_daily.infra.r2 import R2PublishResult


class PipelineTests(unittest.TestCase):
    def test_automatic_date_is_used_for_check_and_r2_key(self) -> None:
        repo_root = Path("/tmp/csbaoyan-date-test")
        publish_result = R2PublishResult(
            report_date="2026-09-07",
            report_count=69,
            uploaded_reports=1,
        )
        options = PipelineOptions(
            repo_root=repo_root,
            report_dir=Path("internal/reports"),
            skip_generate=True,
            skip_telegram=True,
        )

        with patch(
            "csbaoyan_daily.app.pipeline.default_report_date",
            return_value="2026-09-07",
        ), patch(
            "csbaoyan_daily.app.pipeline.run_report_check",
            return_value=[],
        ) as mocked_check, patch(
            "csbaoyan_daily.app.pipeline.run_publish",
            return_value=publish_result,
        ) as mocked_publish:
            resolved_date = run_pipeline(options)

        resolved_repo_root = repo_root.resolve()
        expected_path = resolved_repo_root / "internal/reports/2026-09-07.md"
        self.assertEqual(resolved_date, "2026-09-07")
        mocked_check.assert_called_once_with(expected_path, resolved_repo_root)
        publish_options = mocked_publish.call_args.args[0]
        self.assertEqual(publish_options.report_date, "2026-09-07")
        self.assertEqual(publish_options.report_path, expected_path)

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
