from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from ..config import (
    CHAT_SOURCE,
    EXPORT_DIR,
    OPENAI_API_KEY,
    OPENAI_BASE_URL,
    OPENAI_MODEL,
    QQNT_ACCOUNT,
    QQNT_CACHE_DIR,
    QQNT_CONVERSATION_ID,
    QQNT_DATA_ROOT,
    QQNT_EXPORT_COMMAND,
    QQNT_KEY_PATH,
    REPORT_DIR,
    REPORT_TIMEZONE,
    resolve_path,
)
from ..domain.file_utils import validate_report_date
from .broadcast import broadcast_report
from .generate import GenerateOptions, NoMessagesForDate, default_report_date, run_generate_report
from .publish import PublishOptions, run_publish
from .verify import format_release_issues, run_report_check


@dataclass(frozen=True)
class PipelineOptions:
    repo_root: Path
    source: str = CHAT_SOURCE
    export_dir: Path = EXPORT_DIR
    report_dir: Path = REPORT_DIR
    date: str | None = None
    timezone: str = REPORT_TIMEZONE
    qq_command: Path = QQNT_EXPORT_COMMAND
    qq_key_path: Path | None = QQNT_KEY_PATH
    qq_cache_dir: Path = QQNT_CACHE_DIR
    qq_data_root: Path | None = QQNT_DATA_ROOT
    qq_account: str | None = QQNT_ACCOUNT
    qq_conversation_id: str = QQNT_CONVERSATION_ID
    model: str | None = OPENAI_MODEL
    chunk_max_chars: int = 30000
    chunk_max_messages: int = 600
    chunk_overlap_messages: int = 30
    retries: int = 3
    timeout: float = 120.0
    final_timeout: float = 300.0
    temperature: float = 0.2
    max_workers: int = 4
    base_url: str | None = OPENAI_BASE_URL
    api_key: str | None = OPENAI_API_KEY
    skip_generate: bool = False
    skip_release_check: bool = False
    skip_upload: bool = False
    skip_telegram: bool = False
    verify_public: bool = False


def _resolved_report_date(report_date: str | None, timezone: str) -> str:
    return validate_report_date(report_date) if report_date else default_report_date(timezone)


def run_pipeline(options: PipelineOptions) -> str:
    repo_root = options.repo_root.resolve()
    report_date = _resolved_report_date(options.date, options.timezone)
    report_path = resolve_path(options.report_dir, repo_root) / f"{report_date}.md"

    if not options.skip_generate:
        logging.info("Running generate phase from %s source", options.source)
        try:
            artifacts = run_generate_report(
                GenerateOptions(
                    source=options.source,
                    export_dir=options.export_dir,
                    report_dir=options.report_dir,
                    date=options.date,
                    timezone=options.timezone,
                    qq_command=options.qq_command,
                    qq_key_path=options.qq_key_path,
                    qq_cache_dir=options.qq_cache_dir,
                    qq_data_root=options.qq_data_root,
                    qq_account=options.qq_account,
                    qq_conversation_id=options.qq_conversation_id,
                    model=options.model,
                    chunk_max_chars=options.chunk_max_chars,
                    chunk_max_messages=options.chunk_max_messages,
                    chunk_overlap_messages=options.chunk_overlap_messages,
                    retries=options.retries,
                    timeout=options.timeout,
                    final_timeout=options.final_timeout,
                    temperature=options.temperature,
                    max_workers=options.max_workers,
                    base_url=options.base_url,
                    api_key=options.api_key,
                )
            )
        except NoMessagesForDate:
            logging.info("No usable messages for %s; skipping publish and broadcast.", report_date)
            return report_date
        report_date = artifacts.report_date
        report_path = artifacts.report_path

    if not options.skip_release_check:
        logging.info("Running release check for %s", report_path)
        issues = run_report_check(report_path, repo_root)
        if issues:
            raise RuntimeError(format_release_issues(issues))
        logging.info("Release check passed.")

    if options.skip_upload:
        logging.info("Skipping R2 upload as requested.")
        logging.info("Skipping Telegram broadcast because the report was not published.")
        return report_date

    logging.info("Publishing report to Cloudflare R2")
    publish_result = run_publish(
        PublishOptions(
            report_path=report_path,
            report_date=report_date,
            verify_public=options.verify_public,
        )
    )
    logging.info(
        "R2 publish complete: %s reports indexed",
        publish_result.report_count,
    )

    if options.skip_telegram:
        logging.info("Skipping Telegram broadcast as requested.")
        return report_date

    try:
        logging.info("Sending Telegram broadcast")
        broadcast_report(report_date=report_date, report_path=report_path)
    except Exception as exc:
        logging.warning("Telegram broadcast failed but the daily pipeline will continue: %s", exc)

    logging.info("Daily pipeline completed.")
    return report_date
