from __future__ import annotations

import json
import re
from copy import deepcopy
from collections.abc import Callable, Iterable, Mapping
from typing import Any


SCHEMA_VERSION = 2
HIGHLIGHT_CATEGORIES = ("院校与项目", "申请与考核", "经验与选择")
HIGHLIGHT_KINDS = ("动态", "经验", "分析")
CONFIDENCE_LEVELS = ("high", "medium")
TIMELINE_MAX_DURATION_MINUTES = 240
CHUNK_ITEM_LIMITS = {
    "high_value": 4,
    "timeline_topics": 2,
    "uncertain": 3,
    "light_moments": 1,
}
FINAL_ITEM_LIMITS = {
    "high_value": 12,
    "timeline_topics": 14,
    "uncertain": 8,
    "light_moments": 3,
}
EVIDENCE_REF_PATTERN = re.compile(r"^M\d{5}$")
TIME_PATTERN = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")
TIMELINE_BUCKETS = ((0, 9), (9, 12), (12, 18), (18, 24))
QUESTION_PREFIX_PATTERN = re.compile(
    r"^(?:请问|想问|求问|问一下|有人知道|有无懂|有懂|谁知道|xdm.{0,8}(?:知道|了解))",
    re.IGNORECASE,
)
QUESTION_BODY_PATTERN = re.compile(
    r"(?:是否|能否|可不可以|能不能|有没有|什么时候|怎么|如何|哪(?:个|些|里)|出了吗|开了吗|结束了吗)",
    re.IGNORECASE,
)
QUESTION_END_PATTERN = re.compile(r"(?:吗|么|嘛|呢|吧)[啊呀呐嘛]*[？?。！!…~～\s]*$")


def _object_schema(properties: dict[str, Any], required: Iterable[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": list(required),
        "additionalProperties": False,
    }


EVIDENCE_SCHEMA = {
    "type": "array",
    "items": {"type": "string", "pattern": r"^M\d{5}$"},
    "minItems": 1,
}

HIGH_VALUE_ITEM_SCHEMA = _object_schema(
    {
        "category": {"type": "string", "enum": list(HIGHLIGHT_CATEGORIES)},
        "title": {"type": "string"},
        "summary": {"type": "string"},
        "kind": {"type": "string", "enum": list(HIGHLIGHT_KINDS)},
        "confidence": {"type": "string", "enum": list(CONFIDENCE_LEVELS)},
        "evidence": EVIDENCE_SCHEMA,
    },
    ("category", "title", "summary", "kind", "confidence", "evidence"),
)

TIMELINE_ITEM_SCHEMA = _object_schema(
    {
        "start_time": {"type": "string", "pattern": TIME_PATTERN.pattern},
        "end_time": {"type": "string", "pattern": TIME_PATTERN.pattern},
        "topic": {"type": "string"},
        "summary": {"type": "string"},
        "key_points": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 2,
            "maxItems": 4,
        },
        "status": {"type": "string"},
        "evidence": EVIDENCE_SCHEMA,
    },
    ("start_time", "end_time", "topic", "summary", "key_points", "status", "evidence"),
)

UNCERTAIN_ITEM_SCHEMA = _object_schema(
    {
        "title": {"type": "string"},
        "claim": {"type": "string"},
        "why_uncertain": {"type": "string"},
        "verification": {"type": "string"},
        "evidence": EVIDENCE_SCHEMA,
    },
    ("title", "claim", "why_uncertain", "verification", "evidence"),
)

LIGHT_MOMENT_SCHEMA = _object_schema(
    {
        "title": {"type": "string"},
        "summary": {"type": "string"},
        "evidence": EVIDENCE_SCHEMA,
    },
    ("title", "summary", "evidence"),
)

REPORT_PAYLOAD_SCHEMA = _object_schema(
    {
        "high_value": {"type": "array", "items": HIGH_VALUE_ITEM_SCHEMA},
        "timeline_topics": {"type": "array", "items": TIMELINE_ITEM_SCHEMA},
        "uncertain": {"type": "array", "items": UNCERTAIN_ITEM_SCHEMA},
        "light_moments": {"type": "array", "items": LIGHT_MOMENT_SCHEMA},
    },
    ("high_value", "timeline_topics", "uncertain", "light_moments"),
)


def structured_response_format(
    name: str,
    item_limits: Mapping[str, int] | None = None,
    role_refs: Mapping[str, set[str]] | None = None,
) -> dict[str, Any]:
    schema = deepcopy(REPORT_PAYLOAD_SCHEMA)
    if item_limits:
        for field, maximum in item_limits.items():
            schema["properties"][field]["maxItems"] = maximum
    if role_refs:
        for field, refs in role_refs.items():
            field_schema = schema["properties"][field]
            if refs:
                field_schema["items"]["properties"]["evidence"] = {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": sorted(refs),
                    },
                    "minItems": 1,
                }
            else:
                field_schema["maxItems"] = 0
    return {
        "type": "json_schema",
        "json_schema": {
            "name": name,
            "strict": True,
            "schema": schema,
        },
    }


def parse_json_object(raw_text: str) -> dict[str, Any]:
    text = raw_text.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*([\s\S]*?)\s*```", text, flags=re.IGNORECASE)
    if fenced:
        text = fenced.group(1).strip()

    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("模型输出不是 JSON 对象。") from None
        try:
            value = json.loads(text[start : end + 1])
        except json.JSONDecodeError as exc:
            raise ValueError(f"模型输出 JSON 解析失败：{exc.msg}") from exc

    if not isinstance(value, dict):
        raise ValueError("模型输出的顶层必须是 JSON 对象。")
    return value


def _require_list(value: Mapping[str, Any], field: str) -> list[Any]:
    items = value.get(field)
    if not isinstance(items, list):
        raise ValueError(f"字段 {field} 必须是数组。")
    return items


def _require_mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} 必须是对象。")
    return value


def _plain_text(value: Any, field: str, *, minimum: int = 1) -> str:
    if not isinstance(value, str):
        raise ValueError(f"字段 {field} 必须是字符串。")
    text = re.sub(r"\s+", " ", value).strip()
    if len(text) < minimum:
        raise ValueError(f"字段 {field} 内容过短。")
    return text


def _enum(value: Any, field: str, allowed: tuple[str, ...]) -> str:
    text = _plain_text(value, field)
    if text not in allowed:
        raise ValueError(f"字段 {field} 的值 {text!r} 不在允许范围内。")
    return text


def _highlight_category(value: Any, field: str) -> str:
    text = _plain_text(value, field)
    aliases = {
        "招生动态": "院校与项目",
        "院校动态": "院校与项目",
        "项目动态": "院校与项目",
        "申请经验": "申请与考核",
        "考核经验": "申请与考核",
        "申请流程": "申请与考核",
        "选择分析": "经验与选择",
        "经验分享": "经验与选择",
        "培养体验": "经验与选择",
    }
    return _enum(aliases.get(text, text), field, HIGHLIGHT_CATEGORIES)


def _highlight_kind(value: Any, field: str) -> str:
    text = _plain_text(value, field)
    aliases = {
        "信息": "动态",
        "通知": "动态",
        "经历": "经验",
        "体验": "经验",
        "观察": "分析",
        "观点": "分析",
        "建议": "分析",
    }
    return _enum(aliases.get(text, text), field, HIGHLIGHT_KINDS)


def _evidence_refs(
    value: Any,
    field: str,
    allowed_refs: set[str],
    *,
    allowed_role_refs: set[str] | None = None,
) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"字段 {field} 必须包含至少一个证据编号。")

    refs: list[str] = []
    for raw in value:
        ref = _plain_text(raw, field)
        if not EVIDENCE_REF_PATTERN.fullmatch(ref):
            raise ValueError(f"证据编号格式无效：{ref}")
        if ref not in allowed_refs:
            raise ValueError(f"证据编号不存在于输入：{ref}")
        if allowed_role_refs is not None and ref not in allowed_role_refs:
            raise ValueError(f"证据编号 {ref} 不能用于当前板块。")
        if ref not in refs:
            refs.append(ref)
    return refs


def _string_list(
    value: Any,
    field: str,
    *,
    minimum: int = 1,
    maximum: int = 4,
) -> list[str]:
    if not isinstance(value, list) or len(value) < minimum:
        raise ValueError(f"字段 {field} 至少包含 {minimum} 项。")
    if len(value) > maximum:
        raise ValueError(f"字段 {field} 最多包含 {maximum} 项。")
    return [_plain_text(item, field) for item in value]


def _time(value: Any, field: str) -> str:
    text = _plain_text(value, field)
    if TIME_PATTERN.fullmatch(text):
        return text
    match = re.search(r"(?<!\d)((?:[01]\d|2[0-3]):[0-5]\d)(?::[0-5]\d)?(?!\d)", text)
    if match:
        return match.group(1)[:5]
    raise ValueError(f"字段 {field} 必须使用 HH:MM 格式。")


def _looks_like_question(text: str) -> bool:
    body = text.rsplit("\n", 1)[-1].strip()
    body = re.sub(r"^(?:@User_\d+\s*)+", "", body)
    return bool(
        "?" in body
        or "？" in body
        or QUESTION_PREFIX_PATTERN.search(body)
        or QUESTION_BODY_PATTERN.search(body)
        or QUESTION_END_PATTERN.search(body)
    )


def normalize_report_payload(
    value: Mapping[str, Any],
    *,
    allowed_refs: set[str],
    evidence_text: Mapping[str, str] | None = None,
    role_refs: Mapping[str, set[str]] | None = None,
    final: bool = False,
) -> dict[str, list[dict[str, Any]]]:
    high_value: list[dict[str, Any]] = []
    timeline_topics: list[dict[str, Any]] = []
    uncertain: list[dict[str, Any]] = []
    light_moments: list[dict[str, Any]] = []

    high_refs = role_refs.get("high_value") if role_refs else None
    timeline_refs = role_refs.get("timeline_topics") if role_refs else None
    uncertain_refs = role_refs.get("uncertain") if role_refs else None
    light_refs = role_refs.get("light_moments") if role_refs else None

    for index, raw in enumerate(_require_list(value, "high_value")):
        item = _require_mapping(raw, f"high_value[{index}]")
        evidence = _evidence_refs(
            item.get("evidence"),
            f"high_value[{index}].evidence",
            allowed_refs,
            allowed_role_refs=high_refs,
        )
        normalized = {
            "category": _highlight_category(
                item.get("category"),
                f"high_value[{index}].category",
            ),
            "title": _plain_text(item.get("title"), f"high_value[{index}].title"),
            "summary": _plain_text(
                item.get("summary"),
                f"high_value[{index}].summary",
                minimum=8,
            ),
            "kind": _highlight_kind(
                item.get("kind"),
                f"high_value[{index}].kind",
            ),
            "confidence": _enum(
                item.get("confidence"),
                f"high_value[{index}].confidence",
                CONFIDENCE_LEVELS,
            ),
            "evidence": evidence,
        }

        question_only = bool(evidence_text) and all(
            _looks_like_question(evidence_text.get(ref, "")) for ref in evidence
        )
        if question_only and not final:
            uncertain.append(
                {
                    "title": normalized["title"],
                    "claim": normalized["summary"],
                    "why_uncertain": "现有证据只有提问，没有找到明确回答。",
                    "verification": "等待群内明确答复或查阅对应院校的官方通知。",
                    "evidence": evidence,
                }
            )
        else:
            high_value.append(normalized)

    for index, raw in enumerate(_require_list(value, "timeline_topics")):
        item = _require_mapping(raw, f"timeline_topics[{index}]")
        start_time = _time(item.get("start_time"), f"timeline_topics[{index}].start_time")
        end_time = _time(item.get("end_time"), f"timeline_topics[{index}].end_time")
        if end_time < start_time:
            raise ValueError(f"timeline_topics[{index}] 的结束时间早于开始时间。")
        duration = _minutes(end_time) - _minutes(start_time)
        if duration > TIMELINE_MAX_DURATION_MINUTES:
            raise ValueError(
                f"timeline_topics[{index}] 跨度超过 4 小时，请拆成更具体的话题。"
            )
        timeline_topics.append(
            {
                "start_time": start_time,
                "end_time": end_time,
                "topic": _plain_text(item.get("topic"), f"timeline_topics[{index}].topic"),
                "summary": _plain_text(
                    item.get("summary"),
                    f"timeline_topics[{index}].summary",
                    minimum=12,
                ),
                "key_points": _string_list(
                    item.get("key_points"),
                    f"timeline_topics[{index}].key_points",
                    minimum=2,
                ),
                "status": _plain_text(item.get("status"), f"timeline_topics[{index}].status"),
                "evidence": _evidence_refs(
                    item.get("evidence"),
                    f"timeline_topics[{index}].evidence",
                    allowed_refs,
                    allowed_role_refs=timeline_refs,
                ),
            }
        )

    for index, raw in enumerate(_require_list(value, "uncertain")):
        item = _require_mapping(raw, f"uncertain[{index}]")
        uncertain.append(
            {
                "title": _plain_text(item.get("title"), f"uncertain[{index}].title"),
                "claim": _plain_text(
                    item.get("claim"), f"uncertain[{index}].claim", minimum=8
                ),
                "why_uncertain": _plain_text(
                    item.get("why_uncertain"), f"uncertain[{index}].why_uncertain"
                ),
                "verification": _plain_text(
                    item.get("verification"), f"uncertain[{index}].verification"
                ),
                "evidence": _evidence_refs(
                    item.get("evidence"),
                    f"uncertain[{index}].evidence",
                    allowed_refs,
                    allowed_role_refs=uncertain_refs,
                ),
            }
        )

    for index, raw in enumerate(_require_list(value, "light_moments")):
        item = _require_mapping(raw, f"light_moments[{index}]")
        light_moments.append(
            {
                "title": _plain_text(item.get("title"), f"light_moments[{index}].title"),
                "summary": _plain_text(
                    item.get("summary"), f"light_moments[{index}].summary", minimum=8
                ),
                "evidence": _evidence_refs(
                    item.get("evidence"),
                    f"light_moments[{index}].evidence",
                    allowed_refs,
                    allowed_role_refs=light_refs,
                ),
            }
        )

    if final:
        fields = {
            "high_value": high_value,
            "timeline_topics": timeline_topics,
            "uncertain": uncertain,
            "light_moments": light_moments,
        }
        for field, items in fields.items():
            maximum = FINAL_ITEM_LIMITS[field]
            if len(items) > maximum:
                raise ValueError(f"最终日报字段 {field} 最多包含 {maximum} 项。")
    else:
        fields = {
            "high_value": high_value,
            "timeline_topics": timeline_topics,
            "uncertain": uncertain,
            "light_moments": light_moments,
        }
        for field, items in fields.items():
            maximum = CHUNK_ITEM_LIMITS[field]
            if len(items) > maximum:
                raise ValueError(f"每个 Chunk 的 {field} 最多包含 {maximum} 项。")

    timeline_topics.sort(key=lambda item: (item["start_time"], item["end_time"]))
    return {
        "high_value": high_value,
        "timeline_topics": timeline_topics,
        "uncertain": uncertain,
        "light_moments": light_moments,
    }


def collect_role_refs(chunks: Iterable[Mapping[str, Any]]) -> dict[str, set[str]]:
    role_refs = {
        "high_value": set(),
        "timeline_topics": set(),
        "uncertain": set(),
        "light_moments": set(),
    }
    for chunk in chunks:
        data = chunk.get("data")
        if not isinstance(data, Mapping):
            continue
        for role in role_refs:
            items = data.get(role)
            if not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, Mapping):
                    continue
                evidence = item.get("evidence")
                if isinstance(evidence, list):
                    role_refs[role].update(
                        ref for ref in evidence if isinstance(ref, str)
                    )
    return role_refs


def _minutes(value: str) -> int:
    hours, minutes = value.split(":", 1)
    return int(hours) * 60 + int(minutes)


def _timeline_buckets(items: Iterable[Mapping[str, Any]]) -> set[int]:
    covered: set[int] = set()
    for item in items:
        start = item.get("start_time")
        end = item.get("end_time")
        if not isinstance(start, str) or not isinstance(end, str):
            continue
        if not TIME_PATTERN.fullmatch(start) or not TIME_PATTERN.fullmatch(end):
            continue
        start_minutes = _minutes(start)
        end_minutes = max(start_minutes + 1, _minutes(end))
        for index, (bucket_start, bucket_end) in enumerate(TIMELINE_BUCKETS):
            if start_minutes < bucket_end * 60 and end_minutes > bucket_start * 60:
                covered.add(index)
    return covered


def collect_timeline_buckets(chunks: Iterable[Mapping[str, Any]]) -> set[int]:
    source_items: list[Mapping[str, Any]] = []
    for chunk in chunks:
        data = chunk.get("data")
        if not isinstance(data, Mapping):
            continue
        timeline = data.get("timeline_topics")
        if not isinstance(timeline, list):
            continue
        source_items.extend(item for item in timeline if isinstance(item, Mapping))
    return _timeline_buckets(source_items)


def _append_empty(lines: list[str], message: str) -> None:
    lines.extend((f"- {message}", ""))


def render_report_markdown(report: Mapping[str, list[dict[str, Any]]]) -> str:
    lines = [
        "# CS保研信息日报",
        "",
        f"<!-- report-schema: {SCHEMA_VERSION} -->",
        "",
        "> 免责声明：以下内容由 AI 总结绿群信息生成，仅供参考，请以官方通知和公开资料为准。",
        "",
        "## 今日值得关注",
        "",
    ]

    high_value = report["high_value"]
    if not high_value:
        _append_empty(lines, "今天没有筛选出可信度和信息价值都足够高的内容。")
    else:
        for category in HIGHLIGHT_CATEGORIES:
            items = [item for item in high_value if item["category"] == category]
            if not items:
                continue
            lines.extend((f"### {category}", ""))
            for item in items:
                lines.append(f"- **{item['title']}**：{item['summary']}")
            lines.append("")

    lines.extend(("## 今日讨论脉络", ""))
    timeline = report["timeline_topics"]
    if not timeline:
        _append_empty(lines, "今天没有形成适合单独整理的连续讨论。")
    else:
        for item in timeline:
            lines.extend(
                (
                    f"### {item['start_time']}–{item['end_time']}｜{item['topic']}",
                    "",
                    item["summary"],
                    "",
                )
            )
            for key_point in item["key_points"]:
                lines.append(f"- {key_point}")
            lines.extend(("", f"**讨论状态：** {item['status']}", ""))

    lines.extend(("## 传闻与待核实", ""))
    uncertain = report["uncertain"]
    if not uncertain:
        _append_empty(lines, "今天没有值得单独收录的低可信度消息。")
    else:
        for item in uncertain:
            lines.extend(
                (
                    f"- **{item['title']}**：{item['claim']}",
                    f"  - **不确定性：** {item['why_uncertain']}",
                    f"  - **建议核实：** {item['verification']}",
                )
            )
        lines.append("")

    lines.extend(("## 轻松一刻", ""))
    light_moments = report["light_moments"]
    if not light_moments:
        _append_empty(lines, "今天没有特别适合单独收录的轻松片段。")
    else:
        for item in light_moments:
            lines.append(f"- **{item['title']}**：{item['summary']}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def build_payload_validator(
    *,
    allowed_refs: set[str],
    evidence_text: Mapping[str, str] | None = None,
    role_refs: Mapping[str, set[str]] | None = None,
    final: bool = False,
    required_timeline_buckets: set[int] | None = None,
) -> Callable[[str], dict[str, list[dict[str, Any]]]]:
    def validate(raw_text: str) -> dict[str, list[dict[str, Any]]]:
        report = normalize_report_payload(
            parse_json_object(raw_text),
            allowed_refs=allowed_refs,
            evidence_text=evidence_text,
            role_refs=role_refs,
            final=final,
        )
        if required_timeline_buckets:
            covered = _timeline_buckets(report["timeline_topics"])
            missing = sorted(required_timeline_buckets - covered)
            if missing:
                labels = [
                    f"{TIMELINE_BUCKETS[index][0]:02d}:00–{TIMELINE_BUCKETS[index][1]:02d}:00"
                    for index in missing
                ]
                raise ValueError(f"最终时间线缺少活跃时段：{', '.join(labels)}")
        return report

    return validate
