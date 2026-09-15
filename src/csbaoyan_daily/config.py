from __future__ import annotations

import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

REPO_ROOT = Path(__file__).resolve().parents[2]

if load_dotenv is not None:
    load_dotenv(REPO_ROOT / ".env")


def parse_provider_order(value: str | None) -> tuple[str, ...]:
    """Parse an ordered, de-duplicated provider allowlist."""

    providers: list[str] = []
    for candidate in (value or "").split(","):
        provider = candidate.strip()
        if provider and provider not in providers:
            providers.append(provider)
    return tuple(providers)

# Local paths
EXPORT_DIR = Path(os.getenv("CSBAOYAN_EXPORT_DIR", "chat_exports"))
REPORT_DIR = Path(os.getenv("CSBAOYAN_REPORT_DIR", "internal/reports"))

# Message source config
CHAT_SOURCE = os.getenv("CSBAOYAN_SOURCE", "json").strip().lower()
REPORT_TIMEZONE = os.getenv("CSBAOYAN_TIMEZONE", "Asia/Shanghai").strip()
QQNT_EXPORT_COMMAND = Path(os.getenv("QQNT_EXPORT_COMMAND", "qqnt-export-macos"))
_qqnt_key_path = os.getenv("QQNT_KEY_PATH", "").strip()
QQNT_KEY_PATH = Path(_qqnt_key_path) if _qqnt_key_path else None
QQNT_CACHE_DIR = Path(
    os.getenv(
        "QQNT_CACHE_DIR",
        str(Path.home() / "Library/Caches/qqnt-export-macos/bridge"),
    )
)
_qqnt_data_root = os.getenv("QQNT_DATA_ROOT", "").strip()
QQNT_DATA_ROOT = Path(_qqnt_data_root) if _qqnt_data_root else None
QQNT_ACCOUNT = os.getenv("QQNT_ACCOUNT")
QQNT_CONVERSATION_ID = os.getenv("QQNT_CONVERSATION_ID", "").strip()

# Model provider config
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL")
OPENAI_FINAL_MODEL = os.getenv("OPENAI_FINAL_MODEL")
OPENROUTER_PROVIDER_ORDER = parse_provider_order(
    os.getenv("OPENROUTER_PROVIDER_ORDER")
)

# Telegram broadcast config
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID")
SITE_BASE_URL = os.getenv("SITE_BASE_URL")

# Cloudflare R2 config
R2_ACCOUNT_ID = os.getenv("R2_ACCOUNT_ID")
R2_ACCESS_KEY_ID = os.getenv("R2_ACCESS_KEY_ID")
R2_SECRET_ACCESS_KEY = os.getenv("R2_SECRET_ACCESS_KEY")
R2_BUCKET = os.getenv("R2_BUCKET")
R2_PUBLIC_BASE_URL = os.getenv("R2_PUBLIC_BASE_URL")


def resolve_path(path: Path, base: Path | None = None) -> Path:
    if path.is_absolute():
        return path
    return (base or REPO_ROOT) / path
