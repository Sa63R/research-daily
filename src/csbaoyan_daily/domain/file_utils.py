from __future__ import annotations

import datetime as dt
import json
import re
import time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


DATE_PATTERN = re.compile(r"(\d{4}-\d{2}-\d{2})T")
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


def _describe_available_dates(json_files: list[Path]) -> str:
    dates = sorted({date for path in json_files if (date := _extract_date_from_filename(path))}, reverse=True)
    if not dates:
        return "目录中的文件名未包含可识别日期。"
    preview = ", ".join(dates[:10])
    if len(dates) > 10:
        preview = f"{preview} 等 {len(dates)} 个日期"
    return f"可用日期：{preview}"


def get_latest_json_file(export_dir: Path) -> Path:
    json_files = _list_json_files(export_dir)
    return max(json_files, key=lambda path: path.stat().st_mtime)


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


def extract_messages(payload: dict[str, Any]) -> list[dict[str, Any]]:
    messages = payload.get("messages")
    if not isinstance(messages, list):
        raise ValueError("JSON 中缺少 messages 列表。")
    return messages


def infer_report_date(payload: dict[str, Any], export_file: Path) -> str:
    statistics = payload.get("statistics") or {}
    time_range = statistics.get("timeRange") or {}
    end_value = str(time_range.get("end") or "").strip()
    if end_value:
        return end_value[:10]

    file_date = _extract_date_from_filename(export_file)
    if file_date:
        return file_date
    return time.strftime("%Y-%m-%d")


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
    extracted_path = extracted_dir / f"{report_date}.md"
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
