# 绿群日报部署指南

## 1. 本机环境

日常 QQ 数据源只支持 macOS，并要求 `qqnt-export-macos` 的只读热镜像已经可用：

```bash
/absolute/path/to/qqnt-export-macos/.venv/bin/qqnt-export-macos bridge-status \
  --key '/absolute/path/to/database.key'
```

安装日报依赖：

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
chmod 600 .env
```

`.env` 中的 QQ command、key、缓存目录和群 ID 必须使用绝对路径或精确标识。文件已经被 `.gitignore` 排除，不得提交。

## 2. Cloudflare R2

先登录 Wrangler：

```bash
wrangler login
wrangler whoami
```

取得 `icelon.top` 的 Zone ID 后，一次性创建 APAC 桶、配置 CORS、绑定生产域名并关闭 `r2.dev`：

```bash
scripts/provision_r2.sh --zone-id YOUR_ZONE_ID
```

随后在 Cloudflare R2 中创建仅限 `csbaoyan-chat-daily` 桶的 Object Read & Write S3 API 凭据，并把 Account ID、Access Key ID、Secret Access Key 写入 `.env`。不要将密钥传给前端；浏览器只访问公开的 `https://data.csbaoyan.icelon.top`。

R2 对象结构：

```text
reports.json
reports/YYYY-MM-DD.md
```

发布器先上传并校验日报，再列举 `reports/` 重建索引，最后更新 `reports.json`。失败时不会提前发布不完整索引。

## 3. 旧日报迁移

清理 Git 历史之前运行：

```bash
PYTHONPATH=src .venv/bin/python -m csbaoyan_daily.cli migrate-r2 \
  --reports-dir /path/to/private-report-backup

PYTHONPATH=src .venv/bin/python -m csbaoyan_daily.cli verify-r2 \
  --report-dir /path/to/private-report-backup \
  --date 2026-05-18
```

迁移命令会先检查目录内的所有日报；任意报告命中隐私风险规则时不会开始上传。迁移后还应从网站检查首页、历史日期、正文和搜索。

## 4. 日常运行

```bash
# 完整流水线，默认处理昨天
scripts/daily_pipeline.sh

# 指定日期但不上传
scripts/daily_pipeline.sh --date 2026-09-06 --skip-upload

# 上传后同时从公网域名校验
scripts/daily_pipeline.sh --date 2026-09-06 --verify-public
```

日志写入 `logs/`，锁文件阻止同一时刻重复运行。Telegram 配置不完整时自动跳过。

### macOS LaunchAgent

确认 `.env` 和 `.venv` 已配置，然后安装每天 06:30 的任务：

```bash
scripts/install_launch_agent.sh
```

`StartCalendarInterval` 使用 macOS 系统时区。要让触发时刻严格等于北京时间 06:30，系统时区需要保持为 `Asia/Shanghai`，或使用与其全年同为 UTC+8 的 `Asia/Singapore`。即使系统时区变化，Python 仍会按 `.env` 中的 `CSBAOYAN_TIMEZONE=Asia/Shanghai` 计算目标日期并读取该日期的 `00:00:00`（含）至次日 `00:00:00`（不含）；变化的只是实际触发时刻。

检查或立即触发：

```bash
launchctl print gui/$(id -u)/com.jielosc.csbaoyan-daily
launchctl kickstart -k gui/$(id -u)/com.jielosc.csbaoyan-daily
```

卸载：

```bash
scripts/uninstall_launch_agent.sh
```

如果 LaunchAgent 无法读取 QQ 容器，请在 macOS“隐私与安全性”中为实际执行的 Python 或相关终端授予所需文件访问权限，然后重新触发测试。

### Windows / JSON 回填

QQ 热镜像只支持 macOS。Windows PowerShell 脚本保留用于旧 ChatLab JSON，并默认附加 `--source json`。

## 5. GitHub Pages

`pages/` 只包含静态前端。`pages/config.js` 定义公开 R2 基址，所有日报请求直接发送到 R2 自定义域名。GitHub Actions 仍在前端发生变化时部署 Pages，但日更不会再产生 Git commit 或 Pages 部署。

本地预览：

```bash
cd pages
python3 -m http.server 8080
```

## 6. 故障行为

- 没有有效消息：正常跳过，不更新 R2，不发 Telegram。
- QQ、LLM 或隐私检查失败：非零退出，不上传。
- 日报上传成功但索引上传失败：日报暂时不可见；重跑即可修复。
- 公网 CORS 校验失败：检查 R2 CORS 设置，并清理自定义域名已有缓存后重试。
