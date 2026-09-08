from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..config import (
    R2_ACCESS_KEY_ID,
    R2_ACCOUNT_ID,
    R2_BUCKET,
    R2_PUBLIC_BASE_URL,
    R2_SECRET_ACCESS_KEY,
)
from ..infra.r2 import R2Config, R2Publisher, R2PublishResult


@dataclass(frozen=True)
class PublishOptions:
    report_path: Path
    report_date: str | None = None
    verify_public: bool = False


def r2_config_from_environment() -> R2Config:
    return R2Config(
        account_id=str(R2_ACCOUNT_ID or "").strip(),
        access_key_id=str(R2_ACCESS_KEY_ID or "").strip(),
        secret_access_key=str(R2_SECRET_ACCESS_KEY or "").strip(),
        bucket=str(R2_BUCKET or "").strip(),
        public_base_url=str(R2_PUBLIC_BASE_URL or "").strip(),
    )


def run_publish(options: PublishOptions) -> R2PublishResult:
    publisher = R2Publisher(r2_config_from_environment())
    result = publisher.publish(options.report_path, options.report_date)
    if options.verify_public:
        publisher.verify_public_report(options.report_path, options.report_date)
    return result


def run_migrate(reports_dir: Path) -> R2PublishResult:
    return R2Publisher(r2_config_from_environment()).migrate(reports_dir)


def run_public_verify(report_path: Path, report_date: str | None = None) -> None:
    R2Publisher(r2_config_from_environment()).verify_public_report(
        report_path,
        report_date,
    )
