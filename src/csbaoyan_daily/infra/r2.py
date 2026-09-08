from __future__ import annotations

import hashlib
import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..domain.file_utils import iter_report_paths, validate_report_date


REPORT_KEY_PATTERN = re.compile(r"^reports/(\d{4}-\d{2}-\d{2})\.md$")
REPORT_CACHE_CONTROL = "public, max-age=300"
MANIFEST_CACHE_CONTROL = "no-cache"
PUBLIC_VERIFY_USER_AGENT = "csbaoyan-chat-daily-publisher/1.0"
PUBLIC_VERIFY_ATTEMPTS = 3


@dataclass(frozen=True)
class R2Config:
    account_id: str
    access_key_id: str
    secret_access_key: str
    bucket: str
    public_base_url: str

    @property
    def endpoint_url(self) -> str:
        return f"https://{self.account_id}.r2.cloudflarestorage.com"

    def validate(self) -> None:
        missing = [
            name
            for name, value in (
                ("R2_ACCOUNT_ID", self.account_id),
                ("R2_ACCESS_KEY_ID", self.access_key_id),
                ("R2_SECRET_ACCESS_KEY", self.secret_access_key),
                ("R2_BUCKET", self.bucket),
                ("R2_PUBLIC_BASE_URL", self.public_base_url),
            )
            if not str(value or "").strip()
        ]
        if missing:
            raise ValueError(f"缺少 R2 配置：{', '.join(missing)}")


@dataclass(frozen=True)
class R2PublishResult:
    report_date: str | None
    report_count: int
    uploaded_reports: int


def create_r2_client(config: R2Config):
    config.validate()
    try:
        import boto3
    except ImportError as exc:
        raise RuntimeError("缺少 boto3；请重新安装 requirements.txt。") from exc
    return boto3.client(
        service_name="s3",
        endpoint_url=config.endpoint_url,
        aws_access_key_id=config.access_key_id,
        aws_secret_access_key=config.secret_access_key,
        region_name="auto",
    )


class R2Publisher:
    def __init__(self, config: R2Config, client: Any | None = None) -> None:
        config.validate()
        self.config = config
        self.client = client if client is not None else create_r2_client(config)

    @staticmethod
    def report_key(report_date: str) -> str:
        return f"reports/{validate_report_date(report_date)}.md"

    def _put_verified(
        self,
        *,
        key: str,
        body: bytes,
        content_type: str,
        cache_control: str,
    ) -> None:
        digest = hashlib.sha256(body).hexdigest()
        self.client.put_object(
            Bucket=self.config.bucket,
            Key=key,
            Body=body,
            ContentType=content_type,
            CacheControl=cache_control,
            Metadata={"sha256": digest},
        )
        metadata = self.client.head_object(Bucket=self.config.bucket, Key=key)
        remote_digest = str((metadata.get("Metadata") or {}).get("sha256") or "")
        if int(metadata.get("ContentLength") or -1) != len(body) or remote_digest != digest:
            raise RuntimeError(f"R2 上传校验失败：{key}")

    def upload_report(self, report_path: Path, report_date: str | None = None) -> str:
        path = report_path.resolve()
        if not path.is_file():
            raise FileNotFoundError(f"日报文件不存在：{path}")
        date = validate_report_date(report_date or path.stem)
        body = path.read_bytes()
        if not body.strip():
            raise ValueError(f"日报文件为空：{path}")
        key = self.report_key(date)
        self._put_verified(
            key=key,
            body=body,
            content_type="text/markdown; charset=utf-8",
            cache_control=REPORT_CACHE_CONTROL,
        )
        return key

    def build_manifest(self) -> list[dict[str, str]]:
        keys: list[str] = []
        continuation_token: str | None = None
        while True:
            kwargs: dict[str, Any] = {
                "Bucket": self.config.bucket,
                "Prefix": "reports/",
            }
            if continuation_token:
                kwargs["ContinuationToken"] = continuation_token
            response = self.client.list_objects_v2(**kwargs)
            for item in response.get("Contents") or []:
                key = str(item.get("Key") or "")
                if REPORT_KEY_PATTERN.fullmatch(key):
                    keys.append(key)
            if not response.get("IsTruncated"):
                break
            continuation_token = str(response.get("NextContinuationToken") or "")
            if not continuation_token:
                raise RuntimeError("R2 对象列表分页缺少 continuation token。")

        manifest = []
        for key in sorted(set(keys), reverse=True):
            match = REPORT_KEY_PATTERN.fullmatch(key)
            assert match is not None
            manifest.append({"date": match.group(1), "md_path": key})
        return manifest

    def upload_manifest(self, manifest: list[dict[str, str]]) -> None:
        body = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        self._put_verified(
            key="reports.json",
            body=body,
            content_type="application/json; charset=utf-8",
            cache_control=MANIFEST_CACHE_CONTROL,
        )

    def publish(self, report_path: Path, report_date: str | None = None) -> R2PublishResult:
        key = self.upload_report(report_path, report_date)
        manifest = self.build_manifest()
        if not any(item["md_path"] == key for item in manifest):
            raise RuntimeError(f"R2 索引未发现刚上传的日报：{key}")
        self.upload_manifest(manifest)
        return R2PublishResult(
            report_date=key.removeprefix("reports/").removesuffix(".md"),
            report_count=len(manifest),
            uploaded_reports=1,
        )

    def migrate(self, reports_dir: Path) -> R2PublishResult:
        paths = iter_report_paths(reports_dir.resolve())
        if not paths:
            raise FileNotFoundError(f"没有可迁移的日报：{reports_dir.resolve()}")
        uploaded = 0
        for report_date, path in paths:
            self.upload_report(path, report_date)
            uploaded += 1
        manifest = self.build_manifest()
        self.upload_manifest(manifest)
        return R2PublishResult(
            report_date=None,
            report_count=len(manifest),
            uploaded_reports=uploaded,
        )

    def verify_public_report(
        self,
        report_path: Path,
        report_date: str | None = None,
        *,
        origin: str = "https://csbaoyan.icelon.top",
    ) -> None:
        path = report_path.resolve()
        date = validate_report_date(report_date or path.stem)
        expected = path.read_bytes()
        base_url = self.config.public_base_url.rstrip("/")
        for key, expected_body in (
            (self.report_key(date), expected),
            ("reports.json", None),
        ):
            request = urllib.request.Request(
                f"{base_url}/{key}",
                headers={
                    "Origin": origin,
                    "Cache-Control": "no-cache",
                    "User-Agent": PUBLIC_VERIFY_USER_AGENT,
                },
            )
            for attempt in range(1, PUBLIC_VERIFY_ATTEMPTS + 1):
                try:
                    with urllib.request.urlopen(request, timeout=30) as response:
                        body = response.read()
                        allowed_origin = response.headers.get("Access-Control-Allow-Origin")
                    break
                except urllib.error.HTTPError as exc:
                    if exc.code < 500 or attempt == PUBLIC_VERIFY_ATTEMPTS:
                        raise RuntimeError(f"R2 公网校验失败：{key}: {exc}") from exc
                except urllib.error.URLError as exc:
                    if attempt == PUBLIC_VERIFY_ATTEMPTS:
                        raise RuntimeError(f"R2 公网校验失败：{key}: {exc}") from exc
                time.sleep(0.5 * attempt)
            if expected_body is not None and body != expected_body:
                raise RuntimeError(f"R2 公网内容不一致：{key}")
            if allowed_origin not in {origin, "*"}:
                raise RuntimeError(f"R2 CORS 未允许 {origin}：{key}")
        manifest = json.loads(body.decode("utf-8"))
        if not any(item.get("date") == date for item in manifest):
            raise RuntimeError(f"R2 公网索引缺少日报：{date}")
