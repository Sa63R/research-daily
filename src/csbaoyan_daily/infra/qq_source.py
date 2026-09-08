from __future__ import annotations

import datetime as dt
import json
import math
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ..domain.file_utils import validate_report_date


QQ_PAGE_LIMIT = 1000
IGNORED_CONTENT = {"", "[无正文]", "[正文解析失败]"}


@dataclass(frozen=True)
class QQSourceOptions:
    command: Path
    key_path: Path
    cache_dir: Path
    conversation_id: str
    timezone: str = "Asia/Shanghai"
    data_root: Path | None = None
    account: str | None = None
    timeout: float = 120.0


def _date_window(
    report_date: str,
    timezone: str,
    now: dt.datetime | None = None,
) -> tuple[dt.datetime, dt.datetime, dt.datetime]:
    try:
        zone = ZoneInfo(timezone)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"未知时区：{timezone}") from exc

    day = dt.date.fromisoformat(validate_report_date(report_date))
    start = dt.datetime.combine(day, dt.time.min, tzinfo=zone)
    end = start + dt.timedelta(days=1)
    if now is not None and now.tzinfo is None:
        raise ValueError("now 必须包含时区信息。")
    current = now.astimezone(zone) if now is not None else dt.datetime.now(zone)
    if current < end:
        raise ValueError(f"目标日期 {report_date} 尚未结束，无法生成完整日报。")
    return start, end, current


def _run_page(options: QQSourceOptions, minutes: int, cursor: str | None) -> dict[str, Any]:
    command = [
        str(options.command),
        "recent",
        "--key",
        str(options.key_path),
        "--cache",
        str(options.cache_dir),
        "--minutes",
        str(minutes),
        "--limit",
        str(QQ_PAGE_LIMIT),
        "--conversation",
        options.conversation_id,
    ]
    if options.data_root is not None:
        command.extend(["--source", str(options.data_root)])
    if options.account:
        command.extend(["--account", options.account])
    if cursor:
        command.extend(["--cursor", cursor])

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=options.timeout,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(f"找不到 QQ 导出命令：{options.command}") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("读取 QQ 热镜像超时。") from exc

    if result.returncode != 0:
        detail = result.stderr.strip().splitlines()
        suffix = f"：{detail[-1]}" if detail else ""
        raise RuntimeError(f"QQ 热镜像读取失败（退出码 {result.returncode}）{suffix}")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("QQ 导出命令返回了无效 JSON。") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("messages"), list):
        raise RuntimeError("QQ 导出命令返回的数据结构无效。")
    return payload


def _normalize_message(message: dict[str, Any], zone: ZoneInfo) -> dict[str, Any] | None:
    try:
        timestamp = int(message.get("timestamp") or 0)
    except (TypeError, ValueError):
        return None
    raw_content = message.get("content")
    if isinstance(raw_content, dict):
        content = str(raw_content.get("text") or "").strip()
        raw_metadata = raw_content
    else:
        content = str(raw_content or "").strip()
        raw_metadata = message.get("content_metadata")
    metadata = raw_metadata if isinstance(raw_metadata, dict) else {}
    mentions = [
        item for item in (metadata.get("mentions") or []) if isinstance(item, dict)
    ]
    elements = [
        item for item in (metadata.get("elements") or []) if isinstance(item, dict)
    ]
    message_id = str(message.get("message_id") or "").strip()
    sender_name = str(message.get("sender") or "").strip()
    sender_number = str(message.get("sender_number") or "").strip()
    if not timestamp or not message_id or not sender_name or content in IGNORED_CONTENT:
        return None

    sender_id = sender_number or sender_name
    moment = dt.datetime.fromtimestamp(timestamp, tz=zone)
    return {
        "id": message_id,
        "time": moment.strftime("%Y-%m-%d %H:%M:%S"),
        "sender": {
            "uid": sender_id,
            "uin": sender_number or None,
            "name": sender_name,
        },
        "content": {
            "text": content,
            "mentions": mentions,
            "elements": elements,
        },
    }


def read_qq_messages(
    options: QQSourceOptions,
    report_date: str,
    *,
    now: dt.datetime | None = None,
) -> list[dict[str, Any]]:
    if not options.conversation_id.startswith("group:"):
        raise ValueError("QQNT_CONVERSATION_ID 必须是 group: 开头的群聊标识。")

    start, end, current = _date_window(report_date, options.timezone, now)
    zone = start.tzinfo
    assert isinstance(zone, ZoneInfo)
    minutes = max(1, math.ceil((current - start).total_seconds() / 60) + 1)

    selected: dict[tuple[str, str], dict[str, Any]] = {}
    cursor: str | None = None
    seen_cursors: set[str] = set()
    while True:
        payload = _run_page(options, minutes, cursor)
        for raw in payload["messages"]:
            if not isinstance(raw, dict):
                continue
            try:
                timestamp = int(raw.get("timestamp") or 0)
            except (TypeError, ValueError):
                continue
            if not (start.timestamp() <= timestamp < end.timestamp()):
                continue
            normalized = _normalize_message(raw, zone)
            if normalized is None:
                continue
            key = (
                str(raw.get("conversation_id") or options.conversation_id),
                normalized["id"],
            )
            selected[key] = normalized

        if not payload.get("has_more"):
            break
        next_cursor = str(payload.get("next_cursor") or "")
        if not next_cursor or next_cursor in seen_cursors:
            raise RuntimeError("QQ 消息分页游标无效或发生循环。")
        seen_cursors.add(next_cursor)
        cursor = next_cursor

    return sorted(selected.values(), key=lambda item: (item["time"], item["id"]))
