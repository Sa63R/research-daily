from __future__ import annotations

import datetime as dt
import sys
import unittest
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from csbaoyan_daily.domain.file_utils import previous_report_date


class ReportDateTests(unittest.TestCase):
    def test_shanghai_0630_generates_previous_calendar_day(self) -> None:
        now = dt.datetime(2026, 9, 8, 6, 30, tzinfo=ZoneInfo("Asia/Shanghai"))
        self.assertEqual(previous_report_date("Asia/Shanghai", now=now), "2026-09-07")

    def test_host_timezone_does_not_change_shanghai_report_date(self) -> None:
        now = dt.datetime(2026, 9, 7, 15, 30, tzinfo=ZoneInfo("America/Los_Angeles"))
        self.assertEqual(previous_report_date("Asia/Shanghai", now=now), "2026-09-07")

    def test_crosses_year_boundary(self) -> None:
        now = dt.datetime(2027, 1, 1, 6, 30, tzinfo=ZoneInfo("Asia/Shanghai"))
        self.assertEqual(previous_report_date("Asia/Shanghai", now=now), "2026-12-31")

    def test_rejects_naive_datetime(self) -> None:
        with self.assertRaisesRegex(ValueError, "时区"):
            previous_report_date("Asia/Shanghai", now=dt.datetime(2026, 9, 8, 6, 30))

    def test_rejects_unknown_timezone(self) -> None:
        with self.assertRaisesRegex(ValueError, "未知时区"):
            previous_report_date("Mars/Olympus_Mons")


if __name__ == "__main__":
    unittest.main()
