from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


DATE_PATTERN = re.compile(r"(\d{4}-\d{2}-\d{2})(?=T|$)")
REPORT_FILE_PATTERN = re.compile(r"^(\d{4}-\d{2}-\d{2})\.md$")
PRIVATE_DIRECTORY_MODE = 0o700
PRIVATE_FILE_MODE = 0o600


def validate_report_date(value: str) -> str:
    try:
        return dt.datetime.strptime(value, "%Y-%m-%d").strftime("%Y-%m-%d")
    except ValueError as exc:
        raise ValueError(f"日期格式无效：{value}，请使用 YYYY-MM-DD。") from exc


def previous_report_date(
    timezone: str,
    *,
    now: dt.datetime | None = None,
) -> str:
    try:
        zone = ZoneInfo(timezone)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"未知时区：{timezone}") from exc

    if now is not None and now.tzinfo is None:
        raise ValueError("now 必须包含时区信息。")
    current = now.astimezone(zone) if now is not None else dt.datetime.now(zone)
    return (current.date() - dt.timedelta(days=1)).isoformat()


def _list_json_files(export_dir: Path) -> list[Path]:
    if not export_dir.exists():
        raise FileNotFoundError(f"导出目录不存在：{export_dir}")

    json_files = [path for path in export_dir.glob("*.json") if path.is_file()]
    if not json_files:
        raise FileNotFoundError(f"导出目录中没有 JSON 文件：{export_dir}")
    return json_files


def _extract_date_from_filename(export_file: Path) -> str | None:
    match = DATE_PATTERN.search(export_file.stem)
    return match.group(1) if match else None


def _normalize_optional_date(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return validate_report_date(value)
    except ValueError:
        return None


def _describe_available_dates(json_files: list[Path]) -> str:
    dates = sorted({date for path in json_files if (date := _extract_date_from_filename(path))}, reverse=True)
    if not dates:
        return "目录中的文件名未包含可识别日期。"
    preview = ", ".join(dates[:10])
    if len(dates) > 10:
        preview = f"{preview} 等 {len(dates)} 个日期"
    return f"可用日期：{preview}"


def get_json_file_by_date(export_dir: Path, report_date: str) -> Path:
    normalized_date = validate_report_date(report_date)
    json_files = _list_json_files(export_dir)
    matched_files = [path for path in json_files if _extract_date_from_filename(path) == normalized_date]
    if matched_files:
        return max(matched_files, key=lambda path: path.stat().st_mtime)

    payload_matched_files: list[Path] = []
    for path in json_files:
        try:
            payload = load_chat_export(path)
        except ValueError:
            continue
        if infer_report_date(payload, path) == normalized_date:
            payload_matched_files.append(path)
    if payload_matched_files:
        return max(payload_matched_files, key=lambda path: path.stat().st_mtime)

    raise FileNotFoundError(f"未找到日期为 {normalized_date} 的导出文件。{_describe_available_dates(json_files)}")


def load_chat_export(file_path: Path) -> dict[str, Any]:
    try:
        return json.loads(file_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON 解析失败：{file_path}") from exc


def validate_chatlab_payload(payload: dict[str, Any]) -> None:
    chatlab = payload.get("chatlab")
    if not isinstance(chatlab, dict) or not str(chatlab.get("version") or "").strip():
        raise ValueError("输入文件不是有效的 ChatLab JSON：缺少 chatlab.version。")
    if not isinstance(payload.get("meta"), dict):
        raise ValueError("输入文件不是有效的 ChatLab JSON：缺少 meta 对象。")
    if not isinstance(payload.get("members"), list):
        raise ValueError("输入文件不是有效的 ChatLab JSON：缺少 members 列表。")
    messages = payload.get("messages")
    if not isinstance(messages, list):
        raise ValueError("输入文件不是有效的 ChatLab JSON：缺少 messages 列表。")
    required = {"platformMessageId", "sender", "timestamp", "type", "content"}
    for index, message in enumerate(messages):
        if not isinstance(message, dict) or not required.issubset(message):
            raise ValueError(f"ChatLab messages[{index}] 缺少必需字段。")


def extract_messages(payload: dict[str, Any]) -> list[dict[str, Any]]:
    messages = payload.get("messages")
    if not isinstance(messages, list):
        raise ValueError("JSON 中缺少 messages 列表。")
    if not messages:
        return []

    # Internal normalized fixtures remain supported, but the public boundary
    # between the exporter and this project is ChatLab JSON.
    if all(
        isinstance(message, dict)
        and isinstance(message.get("sender"), dict)
        and isinstance(message.get("content"), dict)
        for message in messages
    ):
        return messages

    members = payload.get("members") or []
    member_names = {
        str(member.get("platformId") or ""): (
            str(member.get("groupNickname") or "").strip()
            or str(member.get("accountName") or "").strip()
        )
        for member in members
        if isinstance(member, dict) and str(member.get("platformId") or "").strip()
    }
    chatlab_by_id = {
        str(message.get("platformMessageId") or "").strip(): message
        for message in messages
        if isinstance(message, dict)
        and str(message.get("platformMessageId") or "").strip()
    }
    range_start = str(
        ((payload.get("statistics") or {}).get("timeRange") or {}).get("start")
        or ""
    ).strip()
    try:
        export_timezone = dt.datetime.fromisoformat(range_start).tzinfo
    except ValueError:
        export_timezone = None

    normalized: list[dict[str, Any]] = []
    for message in messages:
        if not isinstance(message, dict):
            continue
        message_id = str(message.get("platformMessageId") or "").strip()
        sender_id = str(message.get("sender") or "").strip()
        if not message_id or not sender_id:
            continue
        account_name = str(message.get("accountName") or "").strip()
        group_nickname = str(message.get("groupNickname") or "").strip()
        sender_name = group_nickname or account_name or member_names.get(sender_id) or sender_id
        content_text = str(message.get("content") or "").strip()
        source_metadata = message.get("contentMetadata") or {}
        if not isinstance(source_metadata, dict):
            source_metadata = {}
        mentions = [
            item for item in (source_metadata.get("mentions") or [])
            if isinstance(item, dict)
        ]
        elements: list[dict[str, Any]] = [
            item for item in (source_metadata.get("elements") or [])
            if isinstance(item, dict) and item.get("type") != "reply"
        ]

        reply_id = str(message.get("replyToMessageId") or "").strip()
        if reply_id:
            target = chatlab_by_id.get(reply_id) or {}
            reply_context = message.get("replyContext") or {}
            if not isinstance(reply_context, dict):
                reply_context = {}
            target_sender_id = str(
                reply_context.get("sender") or target.get("sender") or ""
            ).strip()
            target_name = (
                str(reply_context.get("accountName") or "").strip()
                or str(target.get("groupNickname") or "").strip()
                or str(target.get("accountName") or "").strip()
                or member_names.get(target_sender_id, "")
                or target_sender_id
            )
            target_content = str(
                reply_context.get("content") or target.get("content") or ""
            ).strip()
            if target_content and not target_name:
                target_name = "未知用户"
            reply_data = {
                "referencedMessageId": reply_id,
                "senderName": target_name,
                "content": target_content,
            }
            elements.append({"type": "reply", "data": reply_data})
            if target_name and target_content:
                content_text = f"[回复 {target_name}: {target_content}]\n{content_text}"

        try:
            timestamp = int(message.get("timestamp") or 0)
        except (TypeError, ValueError):
            timestamp = 0
        moment = (
            dt.datetime.fromtimestamp(timestamp, tz=export_timezone).strftime("%Y-%m-%d %H:%M:%S")
            if timestamp and export_timezone is not None
            else dt.datetime.fromtimestamp(timestamp).astimezone().strftime("%Y-%m-%d %H:%M:%S")
            if timestamp
            else "UNKNOWN_TIME"
        )
        normalized.append(
            {
                "id": message_id,
                "time": moment,
                "sender": {
                    "uid": sender_id,
                    "uin": None,
                    "name": sender_name,
                },
                "content": {
                    "text": content_text,
                    "mentions": mentions,
                    "elements": elements,
                },
                "message_type": message.get("type"),
            }
        )
    return normalized


def infer_report_date(payload: dict[str, Any], export_file: Path) -> str | None:
    statistics = payload.get("statistics") or {}
    time_range = statistics.get("timeRange") or {}
    start_value = str(time_range.get("start") or "").strip()
    end_value = str(time_range.get("end") or "").strip()
    return _normalize_optional_date(start_value[:10]) or _normalize_optional_date(
        end_value[:10]
    ) or _normalize_optional_date(
        _extract_date_from_filename(export_file)
    )


def ensure_private_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    path.chmod(PRIVATE_DIRECTORY_MODE)


def write_private_text(path: Path, content: str) -> None:
    ensure_private_directory(path.parent)
    path.write_text(content, encoding="utf-8")
    path.chmod(PRIVATE_FILE_MODE)


def prepare_output_paths(report_dir: Path, report_date: str) -> tuple[Path, Path, Path]:
    internal_dir = report_dir.parent
    extracted_dir = internal_dir / "extracted"
    reports_dir = report_dir
    transcripts_dir = internal_dir / "transcripts"
    ensure_private_directory(internal_dir)
    ensure_private_directory(extracted_dir)
    ensure_private_directory(reports_dir)
    ensure_private_directory(transcripts_dir)
    extracted_path = extracted_dir / f"{report_date}.json"
    report_path = reports_dir / f"{report_date}.md"
    transcript_path = transcripts_dir / f"{report_date}.txt"
    return extracted_path, report_path, transcript_path


def iter_report_paths(reports_dir: Path) -> list[tuple[str, Path]]:
    if not reports_dir.exists():
        return []

    report_paths: list[tuple[str, Path]] = []
    for path in reports_dir.iterdir():
        if not path.is_file():
            continue

        match = REPORT_FILE_PATTERN.fullmatch(path.name)
        if match:
            report_paths.append((match.group(1), path))

    return sorted(report_paths, key=lambda item: item[0], reverse=True)
