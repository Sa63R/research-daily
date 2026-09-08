from __future__ import annotations

import datetime as dt
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ..domain.file_utils import ensure_private_directory, validate_report_date


@dataclass(frozen=True)
class ChatExportOptions:
    command: Path
    key_path: Path
    cache_dir: Path
    conversation_id: str
    timezone: str = "Asia/Shanghai"
    data_root: Path | None = None
    account: str | None = None
    timeout: float = 120.0


def _resolve_command(command: Path) -> Path:
    expanded = command.expanduser()
    if expanded.is_absolute() or len(expanded.parts) > 1:
        return expanded.resolve()
    discovered = shutil.which(str(expanded))
    return Path(discovered) if discovered else expanded


def _ensure_completed_day(
    report_date: str,
    timezone: str,
    *,
    now: dt.datetime | None = None,
) -> None:
    try:
        zone = ZoneInfo(timezone)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"未知时区：{timezone}") from exc
    day = dt.date.fromisoformat(validate_report_date(report_date))
    end = dt.datetime.combine(day + dt.timedelta(days=1), dt.time.min, tzinfo=zone)
    if now is not None and now.tzinfo is None:
        raise ValueError("now 必须包含时区信息。")
    current = now.astimezone(zone) if now is not None else dt.datetime.now(zone)
    if current < end:
        raise ValueError(f"目标日期 {report_date} 尚未结束，无法生成完整日报。")


def export_chatlab_day(
    options: ChatExportOptions,
    report_date: str,
    export_dir: Path,
    *,
    now: dt.datetime | None = None,
) -> Path:
    """Ask qqnt-export-macos to create one exact-day ChatLab JSON file."""
    _ensure_completed_day(report_date, options.timezone, now=now)
    if not options.conversation_id.startswith(("group:", "c2c:", "dataline:")):
        raise ValueError("QQNT_CONVERSATION_ID 必须是完整的会话标识。")

    ensure_private_directory(export_dir)
    destination = export_dir / f"chatlab-{report_date}.json"
    command = [
        str(_resolve_command(options.command)),
        "export-chatlab",
        str(destination),
        "--key",
        str(options.key_path.expanduser().resolve()),
        "--cache",
        str(options.cache_dir.expanduser().resolve()),
        "--conversation",
        options.conversation_id,
        "--date",
        report_date,
        "--timezone",
        options.timezone,
        "--overwrite",
    ]
    if options.data_root is not None:
        command.extend(["--source", str(options.data_root.expanduser().resolve())])
    if options.account:
        command.extend(["--account", options.account])

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=options.timeout,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(f"找不到聊天导出命令：{options.command}") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("导出 ChatLab JSON 超时。") from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip().splitlines()
        suffix = f"：{detail[-1]}" if detail else ""
        raise RuntimeError(f"ChatLab JSON 导出失败（退出码 {result.returncode}）{suffix}")
    if not destination.is_file():
        raise RuntimeError("聊天导出工具成功退出，但没有生成 ChatLab JSON 文件。")
    destination.chmod(0o600)
    return destination
