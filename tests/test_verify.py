from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from csbaoyan_daily.app.verify import run_release_check, scan_text


class VerifyTests(unittest.TestCase):
    def test_valid_v2_report_passes_structure_check(self) -> None:
        report = """# CS保研信息日报

<!-- report-schema: 2 -->

## 今日值得关注

- 一条可靠信息。

## 今日讨论脉络

### 08:10–08:45｜导师联系策略

讨论有足够的细节。

## 传闻与待核实

- 今天没有值得单独收录的低可信度消息。

## 轻松一刻

- 今天没有特别适合单独收录的轻松片段。
"""

        self.assertEqual(scan_text(Path("report.md"), report, Path.cwd()), [])

    def test_v2_report_requires_all_four_sections(self) -> None:
        report = """# CS保研信息日报

<!-- report-schema: 2 -->

## 今日值得关注

- 一条可靠信息。
"""

        issues = scan_text(Path("report.md"), report, Path.cwd())

        self.assertTrue(any("missing report section: ## 今日讨论脉络" in issue for issue in issues))
        self.assertTrue(any("missing report section: ## 轻松一刻" in issue for issue in issues))

    def test_non_empty_v2_timeline_requires_detailed_time_range(self) -> None:
        report = """# CS保研信息日报

<!-- report-schema: 2 -->

## 今日值得关注

- 一条可靠信息。

## 今日讨论脉络

- 大家讨论了若干话题。

## 传闻与待核实

- 暂无。

## 轻松一刻

- 暂无。
"""

        issues = scan_text(Path("report.md"), report, Path.cwd())

        self.assertTrue(any("timeline has no detailed time-range entry" in issue for issue in issues))

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
