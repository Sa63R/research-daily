from __future__ import annotations

import logging
from dataclasses import dataclass, field, replace
from pathlib import Path

from ..config import resolve_path
from ..domain.file_utils import previous_report_date, validate_report_date
from .broadcast import broadcast_report
from .generate import GenerateOptions, NoMessagesForDate, run_generate_report
from .publish import PublishOptions, run_publish
from .verify import format_release_issues, run_report_check


@dataclass(frozen=True)
class PipelineOptions(GenerateOptions):
    repo_root: Path = field(default_factory=Path.cwd)
    skip_generate: bool = False
    skip_release_check: bool = False
    skip_upload: bool = False
    skip_telegram: bool = False
    verify_public: bool = False


def run_pipeline(options: PipelineOptions) -> str:
    repo_root = options.repo_root.resolve()
    report_date = (
        validate_report_date(options.date)
        if options.date
        else previous_report_date(options.timezone)
    )
    report_path = resolve_path(options.report_dir, repo_root) / f"{report_date}.md"

    if not options.skip_generate:
        logging.info("Running generate phase from %s source", options.source)
        try:
            artifacts = run_generate_report(replace(options, date=report_date))
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
