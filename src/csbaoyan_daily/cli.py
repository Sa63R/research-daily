from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import asdict
from pathlib import Path

from .app.broadcast import broadcast_report
from .app.generate import GenerateOptions, NoMessagesForDate, run_generate_report
from .app.pipeline import PipelineOptions, run_pipeline
from .app.publish import PublishOptions, run_migrate, run_public_verify, run_publish
from .app.verify import format_release_issues, run_release_check
from .config import (
    CHAT_SOURCE,
    EXPORT_DIR,
    OPENAI_API_KEY,
    OPENAI_BASE_URL,
    OPENAI_FINAL_MODEL,
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
from .domain.file_utils import validate_report_date


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        stream=sys.stdout,
    )


def add_generate_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--source",
        choices=("export", "json", "qqnt"),
        default=CHAT_SOURCE,
        help="export invokes qqnt-export-macos; json consumes an existing ChatLab file. qqnt is a compatibility alias for export.",
    )
    parser.add_argument("--export-dir", type=Path, default=EXPORT_DIR, help="Private ChatLab JSON input/output directory.")
    parser.add_argument("--report-dir", type=Path, default=REPORT_DIR, help="Private local report output directory.")
    parser.add_argument("--date", "--report-date", dest="date", type=validate_report_date, help="Target report date in YYYY-MM-DD format.")
    parser.add_argument("--timezone", default=REPORT_TIMEZONE, help="IANA timezone used for daily message boundaries.")
    parser.add_argument("--qq-command", type=Path, default=QQNT_EXPORT_COMMAND)
    parser.add_argument("--qq-key", type=Path, default=QQNT_KEY_PATH)
    parser.add_argument("--qq-cache", type=Path, default=QQNT_CACHE_DIR)
    parser.add_argument("--qq-data-root", type=Path, default=QQNT_DATA_ROOT)
    parser.add_argument("--qq-account", default=QQNT_ACCOUNT)
    parser.add_argument("--qq-conversation", default=QQNT_CONVERSATION_ID)
    parser.add_argument("--model", default=OPENAI_MODEL, help="OpenAI-compatible model name.")
    parser.add_argument(
        "--final-model",
        default=OPENAI_FINAL_MODEL,
        help="Optional stronger model for final consolidation; defaults to --model.",
    )
    parser.add_argument("--chunk-max-chars", type=int, default=30000)
    parser.add_argument("--chunk-max-messages", type=int, default=600)
    parser.add_argument("--chunk-overlap-messages", type=int, default=30)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--final-timeout", type=float, default=300.0)
    parser.add_argument("--chunk-max-output-tokens", type=int, default=6000)
    parser.add_argument("--final-max-output-tokens", type=int, default=12000)
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--max-workers", type=int, default=4)
    parser.add_argument("--base-url", default=OPENAI_BASE_URL)
    parser.add_argument("--api-key", default=OPENAI_API_KEY)


def _generate_options(args: argparse.Namespace) -> GenerateOptions:
    return GenerateOptions(
        source=args.source,
        export_dir=args.export_dir,
        report_dir=args.report_dir,
        date=args.date,
        timezone=args.timezone,
        qq_command=args.qq_command,
        qq_key_path=args.qq_key,
        qq_cache_dir=args.qq_cache,
        qq_data_root=args.qq_data_root,
        qq_account=args.qq_account,
        qq_conversation_id=args.qq_conversation,
        model=args.model,
        final_model=args.final_model,
        chunk_max_chars=args.chunk_max_chars,
        chunk_max_messages=args.chunk_max_messages,
        chunk_overlap_messages=args.chunk_overlap_messages,
        retries=args.retries,
        timeout=args.timeout,
        final_timeout=args.final_timeout,
        chunk_max_output_tokens=args.chunk_max_output_tokens,
        final_max_output_tokens=args.final_max_output_tokens,
        temperature=args.temperature,
        max_workers=args.max_workers,
        base_url=args.base_url,
        api_key=args.api_key,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="CS Baoyan chat daily report tools.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate_parser = subparsers.add_parser("generate", help="Generate a daily report.")
    add_generate_arguments(generate_parser)

    verify_parser = subparsers.add_parser("verify", help="Check one or more local reports.")
    verify_parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    verify_parser.add_argument("--report-dir", type=Path, default=REPORT_DIR)
    verify_parser.add_argument("--date", type=validate_report_date)

    broadcast_parser = subparsers.add_parser("broadcast", help="Send a report overview to Telegram.")
    broadcast_parser.add_argument("--date", type=validate_report_date)
    broadcast_parser.add_argument("--report-dir", type=Path, default=REPORT_DIR)

    publish_parser = subparsers.add_parser("publish", help="Publish one local report to R2.")
    publish_parser.add_argument("--date", type=validate_report_date, required=True)
    publish_parser.add_argument("--report-dir", type=Path, default=REPORT_DIR)
    publish_parser.add_argument("--verify-public", action="store_true")

    migrate_parser = subparsers.add_parser("migrate-r2", help="Upload a directory of reports to R2.")
    migrate_parser.add_argument("--reports-dir", type=Path, required=True)
    migrate_parser.add_argument("--repo-root", type=Path, default=Path.cwd())

    public_parser = subparsers.add_parser("verify-r2", help="Verify a report through the public R2 domain.")
    public_parser.add_argument("--date", type=validate_report_date, required=True)
    public_parser.add_argument("--report-dir", type=Path, default=REPORT_DIR)

    pipeline_parser = subparsers.add_parser("pipeline", help="Generate, verify, publish and broadcast.")
    pipeline_parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    add_generate_arguments(pipeline_parser)
    pipeline_parser.add_argument("--skip-generate", action="store_true")
    pipeline_parser.add_argument("--skip-release-check", action="store_true")
    pipeline_parser.add_argument("--skip-upload", action="store_true")
    pipeline_parser.add_argument("--skip-telegram", action="store_true")
    pipeline_parser.add_argument("--verify-public", action="store_true")

    return parser


def main(argv: list[str] | None = None) -> int:
    configure_logging()
    args = build_parser().parse_args(argv)

    try:
        if args.command == "generate":
            run_generate_report(_generate_options(args))
            return 0

        if args.command == "verify":
            issues = run_release_check(
                repo_root=args.repo_root,
                reports_dir=args.report_dir,
                report_date=args.date,
            )
            if issues:
                print(format_release_issues(issues))
                return 1
            print("Release check passed.")
            return 0

        if args.command == "broadcast":
            broadcast_report(report_date=args.date, report_dir=args.report_dir)
            return 0

        if args.command == "publish":
            report_path = resolve_path(args.report_dir) / f"{args.date}.md"
            result = run_publish(
                PublishOptions(
                    report_path=report_path,
                    report_date=args.date,
                    verify_public=args.verify_public,
                )
            )
            print(f"R2 publish complete: {result.report_count} reports indexed.")
            return 0

        if args.command == "migrate-r2":
            issues = run_release_check(args.repo_root, args.reports_dir)
            if issues:
                print(format_release_issues(issues))
                return 1
            result = run_migrate(resolve_path(args.reports_dir, args.repo_root.resolve()))
            print(
                f"R2 migration complete: {result.uploaded_reports} uploaded, "
                f"{result.report_count} reports indexed."
            )
            return 0

        if args.command == "verify-r2":
            report_path = resolve_path(args.report_dir) / f"{args.date}.md"
            run_public_verify(report_path, args.date)
            print(f"R2 public verification passed for {args.date}.")
            return 0

        if args.command == "pipeline":
            generated = _generate_options(args)
            run_pipeline(
                PipelineOptions(
                    repo_root=args.repo_root,
                    **asdict(generated),
                    skip_generate=args.skip_generate,
                    skip_release_check=args.skip_release_check,
                    skip_upload=args.skip_upload,
                    skip_telegram=args.skip_telegram,
                    verify_public=args.verify_public,
                )
            )
            return 0
    except NoMessagesForDate as exc:
        logging.info("%s 跳过生成与发布。", exc)
        return 0
    except Exception as exc:
        logging.exception("%s failed: %s", args.command, exc)
        return 1

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
