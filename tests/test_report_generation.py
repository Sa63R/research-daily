from __future__ import annotations

import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from csbaoyan_daily.domain.report_generation import (
    call_structured_llm_with_retry,
    compact_extracted_payload,
    generate_final_report,
)


class FakeCompletions:
    def __init__(self, events: list[object]) -> None:
        self.events = list(events)
        self.requests: list[dict[str, object]] = []

    def create(self, **request: object) -> object:
        self.requests.append(request)
        event = self.events.pop(0)
        if isinstance(event, Exception):
            raise event
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=event))]
        )


def fake_client(events: list[object]) -> tuple[object, FakeCompletions]:
    completions = FakeCompletions(events)
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    return client, completions


class ReportGenerationTests(unittest.TestCase):
    def test_final_editor_input_is_bounded_per_chunk(self) -> None:
        item = {"title": "候选"}
        payload = {
            "schema_version": 2,
            "chunks": [
                {
                    "chunk_index": 1,
                    "start_time": "2026-09-07 08:00:00",
                    "end_time": "2026-09-07 09:00:00",
                    "data": {
                        "high_value": [item] * 8,
                        "timeline_topics": [item] * 5,
                        "uncertain": [item] * 7,
                        "light_moments": [item] * 4,
                    },
                }
            ],
        }

        compact = compact_extracted_payload(payload)
        data = compact["chunks"][0]["data"]

        self.assertEqual(len(data["high_value"]), 4)
        self.assertEqual(len(data["timeline_topics"]), 2)
        self.assertEqual(len(data["uncertain"]), 3)
        self.assertEqual(len(data["light_moments"]), 1)

    def test_final_generation_renders_structured_candidates_as_markdown(self) -> None:
        report_payload = {
            "high_value": [
                {
                    "category": "申请与考核",
                    "title": "材料准备经验",
                    "summary": "群友结合亲历说明了材料检查时容易遗漏的项目。",
                    "kind": "经验",
                    "confidence": "high",
                    "evidence": ["M00001"],
                }
            ],
            "timeline_topics": [
                {
                    "start_time": "08:10",
                    "end_time": "08:40",
                    "topic": "申请材料检查",
                    "summary": "讨论围绕材料清单、格式检查和提交前复核逐步展开。",
                    "key_points": ["先按官方清单逐项核对。", "提交前由他人协助复核。"],
                    "status": "形成了较明确的经验共识。",
                    "evidence": ["M00002"],
                }
            ],
            "uncertain": [],
            "light_moments": [],
        }
        extracted_payload = {
            "schema_version": 2,
            "chunks": [
                {
                    "chunk_index": 1,
                    "start_time": "2026-09-07 08:00:00",
                    "end_time": "2026-09-07 08:50:00",
                    "data": report_payload,
                }
            ],
        }
        high_only = dict(report_payload)
        high_only["timeline_topics"] = []
        timeline_only = dict(report_payload)
        timeline_only["high_value"] = []

        class SectionCompletions:
            def __init__(self) -> None:
                self.requests: list[dict[str, object]] = []

            def create(self, **request: object) -> object:
                self.requests.append(request)
                response_format = request["response_format"]
                assert isinstance(response_format, dict)
                schema_config = response_format["json_schema"]
                assert isinstance(schema_config, dict)
                payload = (
                    high_only
                    if schema_config["name"] == "csbaoyan_daily_high_value"
                    else timeline_only
                )
                return SimpleNamespace(
                    choices=[
                        SimpleNamespace(
                            message=SimpleNamespace(
                                content=json.dumps(payload, ensure_ascii=False)
                            )
                        )
                    ]
                )

        completions = SectionCompletions()
        client = SimpleNamespace(chat=SimpleNamespace(completions=completions))

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            extracted_path = root / "2026-09-07.json"
            report_path = root / "2026-09-07.md"
            extracted_path.write_text(
                json.dumps(extracted_payload, ensure_ascii=False),
                encoding="utf-8",
            )

            generate_final_report(
                extracted_path=extracted_path,
                final_report_path=report_path,
                client=client,
                model="test-model",
                retries=1,
                temperature=0.2,
                max_output_tokens=12000,
                deadline_seconds=300,
            )
            markdown = report_path.read_text(encoding="utf-8")

            cached_client, cached_completions = fake_client([])
            generate_final_report(
                extracted_path=extracted_path,
                final_report_path=report_path,
                client=cached_client,
                model="test-model",
                retries=1,
                temperature=0.2,
                max_output_tokens=12000,
                deadline_seconds=300,
            )

        self.assertEqual(len(completions.requests), 2)
        self.assertEqual(len(cached_completions.requests), 0)
        self.assertIn("## 今日值得关注", markdown)
        self.assertIn("### 08:10–08:40｜申请材料检查", markdown)
        self.assertIn("## 传闻与待核实", markdown)
        self.assertIn("## 轻松一刻", markdown)

    def test_structured_call_prefers_strict_json_schema(self) -> None:
        client, completions = fake_client([json.dumps({"ok": True})])

        result = call_structured_llm_with_retry(
            client=client,
            model="test-model",
            system_prompt="system",
            user_prompt="user",
            retries=1,
            temperature=0.2,
            response_format={"type": "json_schema", "json_schema": {"name": "test"}},
            validator=json.loads,
            max_output_tokens=12000,
        )

        self.assertEqual(result, {"ok": True})
        self.assertEqual(
            completions.requests[0]["response_format"],
            {"type": "json_schema", "json_schema": {"name": "test"}},
        )
        self.assertEqual(completions.requests[0]["max_tokens"], 12000)

    def test_structured_call_falls_back_to_json_object_when_unsupported(self) -> None:
        client, completions = fake_client(
            [
                RuntimeError("response_format json_schema is unsupported"),
                json.dumps({"ok": True}),
            ]
        )

        result = call_structured_llm_with_retry(
            client=client,
            model="test-model",
            system_prompt="system",
            user_prompt="user",
            retries=2,
            temperature=0.2,
            response_format={"type": "json_schema", "json_schema": {"name": "test"}},
            validator=json.loads,
            max_output_tokens=12000,
        )

        self.assertEqual(result, {"ok": True})
        self.assertEqual(completions.requests[1]["response_format"], {"type": "json_object"})

    def test_structured_call_can_start_with_json_object_mode(self) -> None:
        client, completions = fake_client([json.dumps({"ok": True})])

        result = call_structured_llm_with_retry(
            client=client,
            model="z-ai/glm-5.3-flash",
            system_prompt="system",
            user_prompt="user",
            retries=1,
            temperature=0.2,
            response_format={"type": "json_schema", "json_schema": {"name": "test"}},
            validator=json.loads,
            prefer_json_object=True,
        )

        self.assertEqual(result, {"ok": True})
        self.assertEqual(completions.requests[0]["response_format"], {"type": "json_object"})

    def test_structured_call_can_lower_reasoning_effort(self) -> None:
        client, completions = fake_client([json.dumps({"ok": True})])

        call_structured_llm_with_retry(
            client=client,
            model="z-ai/glm-5.3-flash",
            system_prompt="system",
            user_prompt="user",
            retries=1,
            temperature=0.2,
            response_format={"type": "json_object"},
            validator=json.loads,
            reasoning_effort="low",
        )

        self.assertEqual(
            completions.requests[0]["extra_body"],
            {"reasoning": {"effort": "low", "exclude": True}},
        )

    def test_structured_call_enforces_total_wall_clock_deadline(self) -> None:
        class SlowCompletions:
            def __init__(self) -> None:
                self.calls = 0

            def create(self, **request: object) -> object:
                self.calls += 1
                time.sleep(0.1)
                return SimpleNamespace(
                    choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok": true}'))]
                )

        completions = SlowCompletions()
        client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
        started = time.monotonic()

        with self.assertRaisesRegex(RuntimeError, "总耗时上限"):
            call_structured_llm_with_retry(
                client=client,
                model="test-model",
                system_prompt="system",
                user_prompt="user",
                retries=3,
                temperature=0.2,
                response_format={"type": "json_object"},
                validator=json.loads,
                deadline_seconds=0.02,
            )

        self.assertLess(time.monotonic() - started, 0.08)
        self.assertEqual(completions.calls, 1)


if __name__ == "__main__":
    unittest.main()
