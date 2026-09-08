from __future__ import annotations

import subprocess
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class DailyPipelineScriptTests(unittest.TestCase):
    def test_macos_bash_accepts_no_forwarded_pipeline_arguments(self) -> None:
        script = (REPO_ROOT / "scripts/daily_pipeline.sh").read_text(encoding="utf-8")
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
