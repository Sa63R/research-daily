from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from csbaoyan_daily.app.verify import run_release_check


class VerifyTests(unittest.TestCase):
    def test_external_migration_directory_can_be_scanned(self) -> None:
        with (
            tempfile.TemporaryDirectory() as repo_directory,
            tempfile.TemporaryDirectory() as reports_directory,
        ):
            report = Path(reports_directory) / "2026-09-06.md"
            report.write_text("# CS保研信息日报\n", encoding="utf-8")

            issues = run_release_check(Path(repo_directory), Path(reports_directory))

        self.assertEqual(issues, [])


if __name__ == "__main__":
    unittest.main()
