from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from csbaoyan_daily.config import parse_provider_order


class ConfigTests(unittest.TestCase):
    def test_provider_order_is_trimmed_and_deduplicated(self) -> None:
        self.assertEqual(
            parse_provider_order(" z-ai,deepinfra,z-ai, "),
            ("z-ai", "deepinfra"),
        )

    def test_empty_provider_order_disables_routing_override(self) -> None:
        self.assertEqual(parse_provider_order(""), ())
        self.assertEqual(parse_provider_order(None), ())


if __name__ == "__main__":
    unittest.main()
