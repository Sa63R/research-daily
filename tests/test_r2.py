import json
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from csbaoyan_daily.infra.r2 import PUBLIC_VERIFY_USER_AGENT, R2Config, R2Publisher


class FakeHTTPResponse:
    def __init__(self, body: bytes, origin: str) -> None:
        self._body = body
        self.headers = {"Access-Control-Allow-Origin": origin}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self) -> bytes:
        return self._body


class FakeR2Client:
    def __init__(self) -> None:
        self.objects = {}
        self.calls = []

    def put_object(self, **kwargs):
        self.calls.append(("put", kwargs["Key"]))
        self.objects[kwargs["Key"]] = kwargs

    def head_object(self, **kwargs):
        self.calls.append(("head", kwargs["Key"]))
        item = self.objects[kwargs["Key"]]
        return {
            "ContentLength": len(item["Body"]),
            "Metadata": item["Metadata"],
        }

    def list_objects_v2(self, **kwargs):
        self.calls.append(("list", kwargs.get("ContinuationToken")))
        keys = sorted(key for key in self.objects if key.startswith(kwargs["Prefix"]))
        offset = int(kwargs.get("ContinuationToken") or 0)
        selected = keys[offset : offset + 1]
        next_offset = offset + len(selected)
        return {
            "Contents": [{"Key": key} for key in selected],
            "IsTruncated": next_offset < len(keys),
            "NextContinuationToken": str(next_offset) if next_offset < len(keys) else None,
        }


class R2PublisherTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = FakeR2Client()
        self.publisher = R2Publisher(
            R2Config(
                account_id="account",
                access_key_id="access",
                secret_access_key="secret",
                bucket="csbaoyan-chat-daily",
                public_base_url="https://data.example.com",
            ),
            client=self.client,
        )

    def test_publish_uploads_report_before_manifest_with_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "2026-09-06.md"
            report.write_text("# 日报\n", encoding="utf-8")
            result = self.publisher.publish(report)

        self.assertEqual(result.report_count, 1)
        self.assertLess(
            self.client.calls.index(("put", "reports/2026-09-06.md")),
            self.client.calls.index(("put", "reports.json")),
        )
        stored = self.client.objects["reports/2026-09-06.md"]
        self.assertEqual(stored["ContentType"], "text/markdown; charset=utf-8")
        self.assertEqual(stored["CacheControl"], "public, max-age=300")
        manifest = json.loads(self.client.objects["reports.json"]["Body"])
        self.assertEqual(
            manifest,
            [{"date": "2026-09-06", "md_path": "reports/2026-09-06.md"}],
        )

    def test_migrate_lists_all_pages_and_sorts_descending(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "2026-09-05.md").write_text("old", encoding="utf-8")
            (root / "2026-09-06.md").write_text("new", encoding="utf-8")
            result = self.publisher.migrate(root)

        self.assertEqual(result.uploaded_reports, 2)
        manifest = json.loads(self.client.objects["reports.json"]["Body"])
        self.assertEqual([item["date"] for item in manifest], ["2026-09-06", "2026-09-05"])
        self.assertGreaterEqual(
            sum(call[0] == "list" for call in self.client.calls),
            2,
        )

    def test_public_verify_uses_named_user_agent(self) -> None:
        origin = "https://csbaoyan.icelon.top"
        requests = []

        def fake_urlopen(request, timeout):
            self.assertEqual(timeout, 30)
            requests.append(request)
            if request.full_url.endswith("reports.json"):
                body = json.dumps(
                    [{"date": "2026-09-06", "md_path": "reports/2026-09-06.md"}]
                ).encode("utf-8")
            else:
                body = b"# report\n"
            return FakeHTTPResponse(body, origin)

        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "2026-09-06.md"
            report.write_bytes(b"# report\n")
            with patch(
                "csbaoyan_daily.infra.r2.urllib.request.urlopen",
                side_effect=fake_urlopen,
            ):
                self.publisher.verify_public_report(report, origin=origin)

        self.assertEqual(len(requests), 2)
        self.assertTrue(
            all(
                request.get_header("User-agent") == PUBLIC_VERIFY_USER_AGENT
                for request in requests
            )
        )

    def test_public_verify_retries_transient_url_error(self) -> None:
        origin = "https://csbaoyan.icelon.top"
        calls = 0

        def fake_urlopen(request, timeout):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise urllib.error.URLError("temporary TLS failure")
            if request.full_url.endswith("reports.json"):
                body = json.dumps(
                    [{"date": "2026-09-06", "md_path": "reports/2026-09-06.md"}]
                ).encode("utf-8")
            else:
                body = b"# report\n"
            return FakeHTTPResponse(body, origin)

        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "2026-09-06.md"
            report.write_bytes(b"# report\n")
            with (
                patch(
                    "csbaoyan_daily.infra.r2.urllib.request.urlopen",
                    side_effect=fake_urlopen,
                ),
                patch("csbaoyan_daily.infra.r2.time.sleep") as sleep,
            ):
                self.publisher.verify_public_report(report, origin=origin)

        self.assertEqual(calls, 3)
        sleep.assert_called_once_with(0.5)

    def test_public_verify_rejects_malformed_manifest(self) -> None:
        origin = "https://csbaoyan.icelon.top"

        def fake_urlopen(request, timeout):
            body = (
                b'["not-an-object"]'
                if request.full_url.endswith("reports.json")
                else b"# report\n"
            )
            return FakeHTTPResponse(body, origin)

        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "2026-09-06.md"
            report.write_bytes(b"# report\n")
            with patch(
                "csbaoyan_daily.infra.r2.urllib.request.urlopen",
                side_effect=fake_urlopen,
            ):
                with self.assertRaisesRegex(RuntimeError, "索引格式"):
                    self.publisher.verify_public_report(report, origin=origin)


if __name__ == "__main__":
    unittest.main()
