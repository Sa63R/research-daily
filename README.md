# 绿群日报（CS Baoyan Chat Daily） 📰

CS（Computer Science）保研群（[绿群](https://github.com/CS-BAOYAN)）每日 AI 信息总结（非官方）。

- 网站：https://csbaoyan.icelon.top
- 日报数据：Cloudflare R2
- 默认消息源：[qqnt-export-macos](https://github.com/jielosc/qqnt-export-macos) 本地只读热镜像

## 工作流

每天 06:30（北京时间）处理前一天 `00:00–24:00` 的群消息：

1. 调用本机 `qqnt-export-macos recent`，按游标读完绿群消息；
2. 严格过滤目标日期，对发送者、联系方式和链接进行匿名化；
3. 用 OpenAI 兼容 API 分块提取并生成 Markdown 日报；
4. 对最终报告执行隐私风险检查；
5. 上传 `reports/YYYY-MM-DD.md` 到 R2，再刷新 `reports.json`；
6. 可选发送 Telegram 概览。

原始 QQ 正文只在进程内存中使用。脱敏记录、中间结果和最终报告保存在被 Git 忽略的 `internal/`；GitHub Pages 仓库只保存前端代码，不再提交日报数据。

## 快速开始

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
chmod 600 .env
```

编辑 `.env`，至少配置：

- `QQNT_EXPORT_COMMAND`、`QQNT_KEY_PATH`、`QQNT_CONVERSATION_ID`
- `OPENAI_BASE_URL`、`OPENAI_API_KEY`、`OPENAI_MODEL`
- `R2_ACCOUNT_ID`、`R2_ACCESS_KEY_ID`、`R2_SECRET_ACCESS_KEY`

QQ 桥接的安装和 key 获取请参考 [qqnt-export-macos 文档](https://github.com/jielosc/qqnt-export-macos)。R2 部署、历史迁移和定时任务见[部署指南](./docs/deploy-guide.md)。

## CLI

```bash
# 从 QQ 热镜像生成某日的本地日报
PYTHONPATH=src .venv/bin/python -m csbaoyan_daily.cli generate --date 2026-09-06

# 完整日更：生成、检查、上传 R2、可选 Telegram
scripts/daily_pipeline.sh

# 只生成和检查，不上传
scripts/daily_pipeline.sh --skip-upload

# 用旧 ChatLab JSON 回填
scripts/daily_pipeline.sh --source json --export-dir /path/to/chatlab-json --date 2026-05-18

# 将现有 Markdown 批量迁移到 R2
PYTHONPATH=src .venv/bin/python -m csbaoyan_daily.cli migrate-r2 \
  --reports-dir pages/data/reports
```

目标日期没有有效消息时，流水线正常结束且不会改动 R2 索引。QQ、LLM、隐私检查或 R2 失败时会非零退出，并保留当前公开索引。

## 免责声明

日报由 AI 从群聊中整理，可能存在遗漏或错误。涉及夏令营、预推免、招生制度和导师信息时，请以官方通知及公开资料为准。

项目会尽量匿名化聊天内容，但无法保证所有上下文都绝对不可识别。如果你发现身份暴露、内容错误或其他风险，请通过 [GitHub Issues](https://github.com/jielosc/csbaoyan-chat-daily/issues/new) 反馈。

## License

[MIT](./LICENSE)
