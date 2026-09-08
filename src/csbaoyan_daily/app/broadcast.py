from __future__ import annotations

import logging
from pathlib import Path

from ..config import REPORT_DIR, REPORT_TIMEZONE, SITE_BASE_URL, TELEGRAM_BOT_TOKEN, TELEGRAM_CHANNEL_ID, resolve_path
from ..domain.file_utils import previous_report_date, validate_report_date
from ..infra.telegram import compose_message, extract_overview, read_report, resolve_report_path, send_telegram_message


def default_report_date() -> str:
    return previous_report_date(REPORT_TIMEZONE)


def resolve_broadcast_config(
    *,
    bot_token: str | None = None,
    channel_id: str | None = None,
    site_base_url: str | None = None,
) -> tuple[str, str, str] | None:
    required = {
        "TELEGRAM_BOT_TOKEN": bot_token if bot_token is not None else TELEGRAM_BOT_TOKEN,
        "TELEGRAM_CHANNEL_ID": channel_id if channel_id is not None else TELEGRAM_CHANNEL_ID,
        "SITE_BASE_URL": site_base_url if site_base_url is not None else SITE_BASE_URL,
    }
    missing = [name for name, value in required.items() if not str(value or "").strip()]
    if missing:
        logging.warning("Skipping Telegram broadcast: missing required config: %s", ", ".join(missing))
        return None

    return (
        str(required["TELEGRAM_BOT_TOKEN"]).strip(),
        str(required["TELEGRAM_CHANNEL_ID"]).strip(),
        str(required["SITE_BASE_URL"]).strip(),
    )


def broadcast_report(
    *,
    report_date: str | None = None,
    report_dir: Path = REPORT_DIR,
    report_path: Path | None = None,
    bot_token: str | None = None,
    channel_id: str | None = None,
    site_base_url: str | None = None,
) -> bool:
    config = resolve_broadcast_config(bot_token=bot_token, channel_id=channel_id, site_base_url=site_base_url)
    if config is None:
        return False

    resolved_report_date = validate_report_date(report_date) if report_date else default_report_date()
    resolved_bot_token, resolved_channel_id, resolved_site_base_url = config

    resolved_report_path = (
        resolve_path(report_path)
        if report_path is not None
        else resolve_report_path(resolve_path(report_dir), resolved_report_date)
    )
    report_markdown = read_report(resolved_report_path)
    overview = extract_overview(report_markdown)
    message = compose_message(resolved_report_date, overview, resolved_site_base_url)
    send_telegram_message(resolved_bot_token, resolved_channel_id, message)
    logging.info("Telegram broadcast sent for %s", resolved_report_date)
    return True
