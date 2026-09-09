from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from ..config import (
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
from ..domain.chat_processing import anonymize_messages, chunk_messages, write_anonymized_transcript
from ..domain.file_utils import (
    extract_messages,
    get_json_file_by_date,
    infer_report_date,
    load_chat_export,
    prepare_output_paths,
    previous_report_date,
    validate_chatlab_payload,
    validate_report_date,
)
from ..domain.report_generation import extract_all_chunks, generate_final_report
from ..infra.openai_client import create_openai_client
from ..infra.chat_export import ChatExportOptions, export_chatlab_day


class NoMessagesForDate(RuntimeError):
    def __init__(self, report_date: str) -> None:
        super().__init__(f"日期 {report_date} 没有可用于日报的 QQ 消息。")
        self.report_date = report_date


@dataclass(frozen=True)
class GenerateOptions:
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
    final_model: str | None = OPENAI_FINAL_MODEL
    chunk_max_chars: int = 30000
    chunk_max_messages: int = 600
    chunk_overlap_messages: int = 30
    retries: int = 3
    timeout: float = 120.0
    final_timeout: float = 300.0
    chunk_max_output_tokens: int = 6000
    final_max_output_tokens: int = 12000
    temperature: float = 0.2
    max_workers: int = 4
    base_url: str | None = OPENAI_BASE_URL
    api_key: str | None = OPENAI_API_KEY


@dataclass(frozen=True)
class GenerateArtifacts:
    report_date: str
    report_path: Path


def run_generate_report(options: GenerateOptions) -> GenerateArtifacts:
    target_date = (
        validate_report_date(options.date)
        if options.date
        else previous_report_date(options.timezone)
    )
    report_dir = resolve_path(options.report_dir)
    source = options.source.strip().lower()

    export_file: Path | None = None
    inferred_report_date: str | None = None
    if source in {"export", "qqnt"}:
        if options.qq_key_path is None:
            raise ValueError("QQNT_KEY_PATH 不能为空。")
        export_file = export_chatlab_day(
            ChatExportOptions(
                command=options.qq_command,
                key_path=resolve_path(options.qq_key_path),
                cache_dir=resolve_path(options.qq_cache_dir),
                conversation_id=options.qq_conversation_id,
                timezone=options.timezone,
                data_root=resolve_path(options.qq_data_root) if options.qq_data_root else None,
                account=options.qq_account,
                timeout=options.timeout,
            ),
            target_date,
            resolve_path(options.export_dir),
        )
    elif source == "json":
        export_dir = resolve_path(options.export_dir)
        export_file = get_json_file_by_date(export_dir, target_date)
    else:
        raise ValueError("CSBAOYAN_SOURCE 只支持 export 或 json（qqnt 为兼容别名）。")

    assert export_file is not None
    payload = load_chat_export(export_file)
    validate_chatlab_payload(payload)
    messages = extract_messages(payload)
    inferred_report_date = infer_report_date(payload, export_file)

    if not messages:
        raise NoMessagesForDate(target_date)
    anonymized_messages = anonymize_messages(messages)
    if not anonymized_messages:
        raise NoMessagesForDate(target_date)
    chunks = chunk_messages(
        anonymized_messages,
        max_chars=options.chunk_max_chars,
        max_messages=options.chunk_max_messages,
        overlap_messages=options.chunk_overlap_messages,
    )
    extraction_model = str(options.model or "").strip()
    final_model = str(options.final_model or options.model or "").strip()
    if not extraction_model:
        raise ValueError("缺少模型名称。请设置 OPENAI_MODEL 或通过 --model 传入。")
    if not final_model:
        raise ValueError("缺少最终汇总模型名称。请设置 OPENAI_FINAL_MODEL 或 OPENAI_MODEL。")

    extracted_path, report_path, transcript_path = prepare_output_paths(report_dir, target_date)
    write_anonymized_transcript(anonymized_messages, transcript_path)

    extraction_client = create_openai_client(options.api_key, options.base_url, options.timeout)
    final_client = create_openai_client(options.api_key, options.base_url, options.final_timeout)

    logging.info("使用日期 %s 的 ChatLab JSON：%s", target_date, export_file)
    if source == "json" and inferred_report_date and inferred_report_date != target_date:
        logging.warning(
            "目标日期为 %s，但导出内容推断日期为 %s，将按目标日期输出。",
            target_date,
            inferred_report_date,
        )
    logging.info(
        "原始消息数：%s，清洗脱敏后消息数：%s，Chunk 数：%s",
        len(messages),
        len(anonymized_messages),
        len(chunks),
    )
    logging.info("模型设置：分块提取 %s，最终汇总 %s", extraction_model, final_model)
    logging.info("LLM 超时设置：分块提取 %ss，最终汇总 %ss", options.timeout, options.final_timeout)
    logging.info(
        "LLM 输出上限：分块提取 %s tokens，最终汇总 %s tokens",
        options.chunk_max_output_tokens,
        options.final_max_output_tokens,
    )

    extract_all_chunks(
        chunks=chunks,
        extracted_path=extracted_path,
        client=extraction_client,
        model=extraction_model,
        retries=options.retries,
        temperature=options.temperature,
        max_workers=options.max_workers,
        max_output_tokens=options.chunk_max_output_tokens,
        deadline_seconds=options.timeout,
    )

    generate_final_report(
        extracted_path=extracted_path,
        final_report_path=report_path,
        client=final_client,
        model=final_model,
        retries=options.retries,
        temperature=options.temperature,
        max_output_tokens=options.final_max_output_tokens,
        deadline_seconds=options.final_timeout,
    )

    logging.info("中间提取结果：%s", extracted_path)
    logging.info("脱敏聊天记录：%s", transcript_path)
    logging.info("最终日报：%s", report_path)

    return GenerateArtifacts(
        report_date=target_date,
        report_path=report_path,
    )
