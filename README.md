# 绿群日报（CS Baoyan Chat Daily） 📰

CS（Computer Science）保研群（[绿群](https://github.com/CS-BAOYAN)）每日 AI 信息总结（非官方）。

- 网站：https://csbaoyan.icelon.top
- 日报数据：Cloudflare R2
- 默认消息源：[qqnt-export-macos](https://github.com/jielosc/qqnt-export-macos) 本地只读热镜像

## 工作流

每天 06:30（北京时间）处理前一天 `00:00–24:00` 的群消息：

1. 调用本机 `qqnt-export-macos export-chatlab`，导出目标自然日的 ChatLab JSON；
2. 读取 ChatLab JSON，对发送者、联系方式和链接进行匿名化；
3. 用 OpenAI 兼容 API 将分块聊天提取为带证据编号的结构化候选信息；
4. 合并候选信息并确定性渲染四板块 Markdown 日报，再执行结构与隐私风险检查；
5. 上传 `reports/YYYY-MM-DD.md` 到 R2，再刷新 `reports.json`；
6. 可选发送 Telegram 概览。

原始 QQ 正文只保存在本机权限为 `0600`、被 Git 忽略的 `chat_exports/` 中，并在生成日报时读入进程内存。脱敏记录、中间结果和最终报告保存在同样被 Git 忽略的 `internal/`；GitHub Pages 仓库只保存前端代码，不提交聊天数据或日报数据。

项目边界如下：

- `qqnt-export-macos` 负责 QQ 数据库、热镜像、protobuf、回复关系和 ChatLab 文件输出；
- 本项目只编排导出命令并消费 ChatLab JSON，不读取 QQ 数据库，也不解析 QQ 私有消息格式；
- `chat_exports/chatlab-YYYY-MM-DD.json` 是两个项目之间唯一的数据接口。

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
- `OPENROUTER_PROVIDER_ORDER`（当前建议为 `z-ai,deepinfra`）
- `R2_ACCOUNT_ID`、`R2_ACCESS_KEY_ID`、`R2_SECRET_ACCESS_KEY`

可选设置 `OPENAI_FINAL_MODEL`，让跨 Chunk 合并使用质量更高的模型；未设置时与 `OPENAI_MODEL` 相同。
默认按最多 2 万字符或 400 条消息切分（重叠 20 条），每个分块最多输出 3500 tokens、每个终稿板块最多输出 12000 tokens；`--timeout`（默认 240 秒）与 `--final-timeout`（默认 300 秒）是覆盖重试和退避等待的单次结构化编辑总耗时上限。程序会在多次尝试之间预留预算，避免单个卡住的请求耗尽全部重试时间。分块默认最多 2 路并发，以兼顾吞吐量和模型上游稳定性；终稿也按最多两个板块并行独立编辑，通过校验的板块会保存为私有缓存，再由程序合并并整体验证。
对强制推理且默认推理强度过高的已知模型，分块提取和终稿编辑都会使用较低推理强度，把输出预算优先留给最终 JSON；所有结构约束仍由本地校验器执行。OpenRouter Provider 顺序由 `OPENROUTER_PROVIDER_ORDER` 配置；例如 `z-ai,deepinfra` 会优先使用 Z.AI，失败时只回退到 DeepInfra，不会落到 Wafer 等名单外端点。留空则使用 OpenRouter 自动路由。

## 日报结构

新生成的日报固定包含四个板块：

1. **今日值得关注**：按“院校与项目”“申请与考核”“经验与选择”最多三个类别整理高价值内容，不要求读者立即行动；
2. **今日讨论脉络**：按时间顺序详细概括有内容的话题，包括讨论焦点、关键观点、分歧或阶段性结论；
3. **传闻与待核实**：单一信源、相互矛盾、仅有提问或缺少原始证据的消息；
4. **轻松一刻**：少量脱离上下文仍能理解、且不会伤害具体个人的有趣片段。

分块提取结果保存为私有 JSON。最终 Markdown 由程序渲染，模型输出中的证据编号仅用于内部校验，不会公开。

QQ 桥接的安装和 key 获取请参考 [qqnt-export-macos 文档](https://github.com/jielosc/qqnt-export-macos)。R2 部署、历史迁移和定时任务见[部署指南](./docs/deploy-guide.md)。

macOS 定时任务通过独立的 `GreenDailyRunner.app` 启动，不需要给 Homebrew 的通用 Python 完全磁盘访问权限。Runner 使用固定 bundle identifier，只执行本项目内固定的日报脚本；安装与授权步骤见部署指南。

## CLI

```bash
# 先由 qqnt-export-macos 生成当日 ChatLab JSON，再生成本地日报
PYTHONPATH=src .venv/bin/python -m csbaoyan_daily.cli generate --date 2026-09-06

# 完整日更：生成、检查、上传 R2、可选 Telegram
scripts/daily_pipeline.sh

# 只生成和检查，不上传
scripts/daily_pipeline.sh --skip-upload

# 使用已有 ChatLab JSON 回填（不会访问 QQ）
scripts/daily_pipeline.sh --source json --export-dir /path/to/chatlab-json --date 2026-05-18

# 将现有 Markdown 批量迁移到 R2
PYTHONPATH=src .venv/bin/python -m csbaoyan_daily.cli migrate-r2 \
  --reports-dir /path/to/reports
```

目标日期没有有效消息时，流水线正常结束且不会改动 R2 索引。QQ、LLM、隐私检查或 R2 失败时会非零退出，并保留当前公开索引。

## 免责声明

日报由 AI 从群聊中整理，可能存在遗漏或错误。涉及夏令营、预推免、招生制度和导师信息时，请以官方通知及公开资料为准。

项目会尽量匿名化聊天内容，但无法保证所有上下文都绝对不可识别。如果你发现身份暴露、内容错误或其他风险，请通过 [GitHub Issues](https://github.com/jielosc/csbaoyan-chat-daily/issues/new) 反馈。

## License

[MIT](./LICENSE)
