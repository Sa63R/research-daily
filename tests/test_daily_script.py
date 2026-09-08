from __future__ import annotations

import plistlib
import subprocess
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class DailyPipelineScriptTests(unittest.TestCase):
    def test_launch_agent_runs_at_0630_with_shanghai_process_timezone(self) -> None:
        with (REPO_ROOT / "scripts/com.jielosc.csbaoyan-daily.plist.template").open("rb") as handle:
            plist = plistlib.load(handle)

        self.assertEqual(plist["StartCalendarInterval"], {"Hour": 6, "Minute": 30})
        self.assertEqual(plist["EnvironmentVariables"]["TZ"], "Asia/Shanghai")

    def test_macos_bash_accepts_no_forwarded_pipeline_arguments(self) -> None:
        script = (REPO_ROOT / "scripts/daily_pipeline.sh").read_text(encoding="utf-8")
        self.assertIn("umask 077", script)
        self.assertIn("if [[ ${pipeline_args+x} ]]", script)

        result = subprocess.run(
            [
                "/bin/bash",
                "-uc",
                "declare -a pipeline_args=(); "
                "if [[ ${pipeline_args+x} ]]; then exit 9; else exit 0; fi",
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
