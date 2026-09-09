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
        self.assertEqual(plist["ProgramArguments"], ["__RUNNER_EXECUTABLE__"])
        self.assertNotIn("python", " ".join(plist["ProgramArguments"]).lower())
        self.assertNotIn("/bin/bash", plist["ProgramArguments"])

    def test_runner_has_fixed_identity_and_fixed_entrypoint(self) -> None:
        runner_dir = REPO_ROOT / "scripts/green_daily_runner"
        with (runner_dir / "Info.plist").open("rb") as handle:
            info = plistlib.load(handle)
        source = (runner_dir / "main.swift").read_text(encoding="utf-8")

        self.assertEqual(
            info["CFBundleIdentifier"],
            "com.jielosc.greendaily.runner",
        )
        self.assertEqual(info["CFBundleExecutable"], "GreenDailyRunner")
        self.assertIn('appendingPathComponent("scripts/daily_pipeline.sh")', source)
        self.assertIn('appendingPathComponent(".venv/bin/python")', source)
        self.assertNotIn(
            'appendingPathComponent(".venv/bin/python")\n    .resolvingSymlinksInPath()',
            source,
        )
        self.assertIn("unsupported arguments; only --check is accepted", source)
        self.assertIn('"BASH_ENV", "ENV", "PYTHONHOME", "PYTHONPATH", "PYTHONSTARTUP"', source)

    def test_runner_scripts_have_valid_bash_syntax(self) -> None:
        for name in (
            "build_green_daily_runner.sh",
            "install_launch_agent.sh",
            "uninstall_launch_agent.sh",
        ):
            result = subprocess.run(
                ["/bin/bash", "-n", str(REPO_ROOT / "scripts" / name)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_macos_bash_accepts_no_forwarded_pipeline_arguments(self) -> None:
        script = (REPO_ROOT / "scripts/daily_pipeline.sh").read_text(encoding="utf-8")
        self.assertIn("umask 077", script)
        self.assertIn("if [[ ${pipeline_args+x} ]]", script)
        self.assertIn('if [[ -n "${GREEN_DAILY_RUNNER:-}" ]]', script)
        self.assertIn('runner_python="${resolved_repo_root}/.venv/bin/python"', script)

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
