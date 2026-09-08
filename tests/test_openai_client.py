from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from csbaoyan_daily.infra.openai_client import create_openai_client


class OpenAIClientTests(unittest.TestCase):
    def test_disables_sdk_retries_so_application_retry_budget_is_bounded(self) -> None:
        captured: dict[str, object] = {}

        class FakeOpenAI:
            def __init__(self, **kwargs: object) -> None:
                captured.update(kwargs)

        fake_module = SimpleNamespace(OpenAI=FakeOpenAI)
        with patch.dict(sys.modules, {"openai": fake_module}):
            create_openai_client("secret", "https://example.invalid/v1", 42.0)

        self.assertEqual(captured["max_retries"], 0)
        self.assertEqual(captured["timeout"], 42.0)
        self.assertEqual(captured["base_url"], "https://example.invalid/v1")


if __name__ == "__main__":
    unittest.main()
