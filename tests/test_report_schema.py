from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from csbaoyan_daily.domain.report_schema import (
    build_payload_validator,
    collect_timeline_buckets,
    normalize_report_payload,
    render_report_markdown,
    structured_response_format,
)


def empty_payload() -> dict[str, list[dict[str, object]]]:
    return {
        "high_value": [],
        "timeline_topics": [],
        "uncertain": [],
        "light_moments": [],
    }


class ReportSchemaTests(unittest.TestCase):
    def test_final_schema_constrains_evidence_to_each_section(self) -> None:
        response_format = structured_response_format(
            "daily",
            {"high_value": 12, "timeline_topics": 14, "uncertain": 8, "light_moments": 3},
            {
                "high_value": {"M00001"},
                "timeline_topics": {"M00002"},
                "uncertain": set(),
                "light_moments": {"M00003"},
            },
        )
        properties = response_format["json_schema"]["schema"]["properties"]

        high_evidence = properties["high_value"]["items"]["properties"]["evidence"]
        self.assertEqual(high_evidence["items"]["enum"], ["M00001"])
        self.assertEqual(properties["uncertain"]["maxItems"], 0)

    def test_question_only_high_value_candidate_is_demoted_to_uncertain(self) -> None:
        payload = empty_payload()
        payload["high_value"] = [
            {
                "category": "院校与项目",
                "title": "华师软件学院第二批通知",
                "summary": "华师软件学院将在下午发送第二批通知。",
                "kind": "动态",
                "confidence": "medium",
                "evidence": ["M00001"],
            }
        ]

        normalized = normalize_report_payload(
            payload,
            allowed_refs={"M00001"},
            evidence_text={"M00001": "那华师软下午就发第二批通知？"},
        )

        self.assertEqual(normalized["high_value"], [])
        self.assertEqual(len(normalized["uncertain"]), 1)
        self.assertIn("只有提问", normalized["uncertain"][0]["why_uncertain"])

    def test_final_editor_cannot_promote_evidence_from_another_section(self) -> None:
        payload = empty_payload()
        payload["high_value"] = [
            {
                "category": "院校与项目",
                "title": "未经确认的项目消息",
                "summary": "这是一条只有转述来源、尚未得到确认的项目消息。",
                "kind": "动态",
                "confidence": "medium",
                "evidence": ["M00002"],
            }
        ]

        with self.assertRaisesRegex(ValueError, "不能用于当前板块"):
            normalize_report_payload(
                payload,
                allowed_refs={"M00001", "M00002"},
                role_refs={
                    "high_value": {"M00001"},
                    "timeline_topics": set(),
                    "uncertain": {"M00002"},
                    "light_moments": set(),
                },
                final=True,
            )

    def test_timeline_coverage_uses_non_overlapping_time_buckets(self) -> None:
        chunks = [
            {
                "data": {
                    "timeline_topics": [
                        {"start_time": "09:00", "end_time": "09:30"}
                    ]
                }
            }
        ]

        self.assertEqual(collect_timeline_buckets(chunks), {1})

    def test_final_timeline_must_cover_active_source_periods(self) -> None:
        payload = empty_payload()
        payload["timeline_topics"] = [
            {
                "start_time": "13:00",
                "end_time": "13:30",
                "topic": "中午的项目讨论",
                "summary": "群友围绕项目方向和申请材料展开了较完整的讨论。",
                "key_points": ["有人介绍项目方向。", "大家比较了申请材料。"],
                "status": "形成了部分共识。",
                "evidence": ["M00001"],
            }
        ]
        validator = build_payload_validator(
            allowed_refs={"M00001"},
            final=True,
            required_timeline_buckets={0, 2},
        )

        with self.assertRaisesRegex(ValueError, "00:00–09:00"):
            validator(json.dumps(payload, ensure_ascii=False))

    def test_timeline_requires_multiple_points_and_a_bounded_time_range(self) -> None:
        one_point = empty_payload()
        one_point["timeline_topics"] = [
            {
                "start_time": "08:00",
                "end_time": "08:30",
                "topic": "申请材料讨论",
                "summary": "群友围绕申请材料准备展开了一段完整讨论。",
                "key_points": ["大家比较了材料清单。"],
                "status": "形成了部分共识。",
                "evidence": ["M00001"],
            }
        ]
        with self.assertRaisesRegex(ValueError, "至少包含 2 项"):
            normalize_report_payload(one_point, allowed_refs={"M00001"})

        all_day = empty_payload()
        all_day["timeline_topics"] = [
            {
                "start_time": "08:00",
                "end_time": "20:00",
                "topic": "过于宽泛的全天话题",
                "summary": "这个条目试图用一个宽泛概括覆盖当天的大部分讨论。",
                "key_points": ["上午有一段讨论。", "晚上还有另一段讨论。"],
                "status": "需要拆分成更具体的话题。",
                "evidence": ["M00001"],
            }
        ]
        with self.assertRaisesRegex(ValueError, "跨度超过 4 小时"):
            normalize_report_payload(all_day, allowed_refs={"M00001"})

    def test_renderer_outputs_four_sections_and_detailed_timeline(self) -> None:
        report = {
            "high_value": [
                {
                    "category": "经验与选择",
                    "title": "联系导师的经验",
                    "summary": "群友分享了先阅读课题组材料再写邮件的经验。",
                    "kind": "经验",
                    "confidence": "high",
                    "evidence": ["M00001"],
                }
            ],
            "timeline_topics": [
                {
                    "start_time": "08:10",
                    "end_time": "08:45",
                    "topic": "导师联系策略",
                    "summary": "讨论从邮件内容延伸到是否应该在短期内再次跟进。",
                    "key_points": ["先了解研究方向再联系。", "跟进频率没有统一答案。"],
                    "status": "形成部分共识，但跟进时点仍有分歧。",
                    "evidence": ["M00001"],
                }
            ],
            "uncertain": [
                {
                    "title": "项目通知时间",
                    "claim": "有人转述项目可能会在下午发出通知。",
                    "why_uncertain": "只有单一转述，没有官方来源。",
                    "verification": "以学院官网或正式通知为准。",
                    "evidence": ["M00002"],
                }
            ],
            "light_moments": [
                {
                    "title": "群友的自嘲",
                    "summary": "大家用轻松的方式调侃等待通知时反复刷新页面。",
                    "evidence": ["M00003"],
                }
            ],
        }

        markdown = render_report_markdown(report)

        sections = [
            "## 今日值得关注",
            "## 今日讨论脉络",
            "## 传闻与待核实",
            "## 轻松一刻",
        ]
        self.assertEqual(
            [markdown.index(section) for section in sections],
            sorted(markdown.index(section) for section in sections),
        )
        self.assertIn("<!-- report-schema: 2 -->", markdown)
        self.assertIn("### 08:10–08:45｜导师联系策略", markdown)
        self.assertIn("**讨论状态：** 形成部分共识", markdown)


if __name__ == "__main__":
    unittest.main()
