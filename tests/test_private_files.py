from __future__ import annotations

import stat
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from csbaoyan_daily.domain.file_utils import prepare_output_paths, write_private_text


class PrivateFileTests(unittest.TestCase):
    def test_internal_directories_and_files_are_private(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            internal_dir = Path(temporary_dir) / "internal"
            extracted, report, transcript = prepare_output_paths(
                internal_dir / "reports",
                "2026-09-07",
            )
            for directory in (
                internal_dir,
                extracted.parent,
                report.parent,
                transcript.parent,
            ):
                self.assertEqual(stat.S_IMODE(directory.stat().st_mode), 0o700)

            for path in (extracted, report, transcript):
                write_private_text(path, "private\n")
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)


if __name__ == "__main__":
    unittest.main()
