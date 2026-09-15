# 可选集成与部署指南

本项目的核心用途是从 ChatLab JSON 生成本地 Markdown 日报。本页记录 QQ 自动导出、Cloudflare R2、Telegram 和定时任务等可选集成；它们不是使用生成器的前置条件。

维护者的公开 Pages 现为历史效果预览，不再执行每日生成和发布。下文中的域名、桶名、时间和目录都应替换为使用者自己的配置。

## 1. 本地生成环境

日常 QQ 数据源只支持 macOS，并要求 `qqnt-export-macos` 的只读热镜像已经可用：

```bash
/absolute/path/to/qqnt-export-macos/.venv/bin/qqnt-export-macos bridge-status \
  --key '/absolute/path/to/database.key'
```

安装生成器：

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
cp .env.example .env
chmod 600 .env
```

`.env` 中的 QQ command、key、缓存目录和群 ID 必须使用绝对路径或精确标识。文件已经被 `.gitignore` 排除，不得提交。

## 2. Cloudflare R2（可选）

先登录 Wrangler：

```bash
wrangler login
wrangler whoami
```

取得自己的 Cloudflare Zone ID 后，创建桶、配置 CORS、绑定域名并关闭 `r2.dev`：

```bash
scripts/provision_r2.sh \
  --zone-id YOUR_ZONE_ID \
  --bucket YOUR_BUCKET \
  --domain data.example.com \
  --site-origin https://reports.example.com
```

随后在 Cloudflare R2 中创建仅限目标桶的 Object Read & Write S3 API 凭据，并把 Account ID、Access Key ID、Secret Access Key、桶名和公开基址写入 `.env`。不要将密钥传给前端；浏览器只应访问公开数据域名。

R2 对象结构：

```text
reports.json
reports/YYYY-MM-DD.md
```

发布器先上传并校验日报，再列举 `reports/` 重建索引，最后更新 `reports.json`。失败时不会提前发布不完整索引。

## 3. 旧日报迁移

清理 Git 历史之前运行：

```bash
csbaoyan-daily migrate-r2 \
  --reports-dir /path/to/private-report-backup

csbaoyan-daily verify-r2 \
  --report-dir /path/to/private-report-backup \
  --date 2026-05-18
```

迁移命令会先检查目录内的所有日报；任意报告命中隐私风险规则时不会开始上传。迁移后还应从网站检查首页、历史日期、正文和搜索。

## 4. 完整流水线（可选）

```bash
# 完整流水线，默认处理昨天
scripts/daily_pipeline.sh

# 指定日期但不上传
scripts/daily_pipeline.sh --date 2026-09-06 --skip-upload

# 上传后同时从公网域名校验
scripts/daily_pipeline.sh --date 2026-09-06 --verify-public
```

日志写入 `logs/`，锁文件阻止同一时刻重复运行。Telegram 配置不完整时自动跳过。

### macOS LaunchAgent（可选）

只有确实需要无人值守运行时，才安装每天 06:30 的任务：

```bash
scripts/install_launch_agent.sh
```

安装器会在 `.runner/GreenDailyRunner.app` 创建一个本机编译、临时签名的辅助 app，并让 LaunchAgent 只启动它。Runner 的 bundle identifier 固定为 `com.jielosc.greendaily.runner`，不接受任意命令或脚本路径；它只会从自身位置定位当前仓库，依次启动固定的 `scripts/daily_pipeline.sh` 和 `.venv/bin/python`。构建产物被 Git 忽略。

首次安装时，安装器会在 Finder 中显示 Runner，并打开“系统设置 → 隐私与安全性 → 完全磁盘访问权限”。完成以下操作：

1. 点击 `+`，加入 `.runner/GreenDailyRunner.app` 并启用；
2. 不要为 Homebrew 的 `python3.14`、`/bin/bash` 或常用终端授予完全磁盘访问权限；
3. 授权 Runner 后立即触发一次任务，确认它确实能读取 QQ 数据并完成流水线；
4. 验证成功后，可从完全磁盘访问权限列表中关闭或移除之前为通用 Python 添加的权限。

macOS 没有受支持的 API 可以直接查询“是否已获得完全磁盘访问权限”，也不允许脚本自动授权。因此最终验证必须实际运行一次：

`StartCalendarInterval` 使用 macOS 系统时区。要让触发时刻严格等于北京时间 06:30，系统时区需要保持为 `Asia/Shanghai`，或使用与其全年同为 UTC+8 的 `Asia/Singapore`。即使系统时区变化，Python 仍会按 `.env` 中的 `CSBAOYAN_TIMEZONE=Asia/Shanghai` 计算目标日期并读取该日期的 `00:00:00`（含）至次日 `00:00:00`（不含）；变化的只是实际触发时刻。

检查或立即触发：

```bash
launchctl print gui/$(id -u)/com.jielosc.csbaoyan-daily
launchctl kickstart -k gui/$(id -u)/com.jielosc.csbaoyan-daily
tail -f logs/launchd.out.log logs/launchd.err.log
```

`launchctl print` 的 `program` 应指向：

```text
<仓库>/.runner/GreenDailyRunner.app/Contents/MacOS/GreenDailyRunner
```

它不应再指向 `/bin/bash` 或任何 Python 路径。可以单独检查 Runner 的固定路径解析与签名，但该检查不会证明完全磁盘访问权限已经生效：

```bash
.runner/GreenDailyRunner.app/Contents/MacOS/GreenDailyRunner --check
codesign --verify --deep --strict .runner/GreenDailyRunner.app
codesign -d --verbose=4 .runner/GreenDailyRunner.app 2>&1 | grep Identifier
```

日常更新仓库、虚拟环境或 Homebrew Python 不需要重建 Runner。只有修改 Runner 源码时才执行：

```bash
scripts/build_green_daily_runner.sh --force
```

替换 `.app` 会改变代码签名哈希，macOS 可能要求重新加入或重新启用完全磁盘访问权限。普通安装命令检测到 Runner 已存在时会保留它，避免无意中使授权失效。

卸载：

```bash
# 只卸载定时任务，保留 Runner 身份和授权，便于以后恢复
scripts/uninstall_launch_agent.sh

# 同时删除 Runner；之后可在系统设置中移除对应授权项
scripts/uninstall_launch_agent.sh --remove-runner
```

如果 LaunchAgent 无法读取 QQ 容器，请确认完全磁盘访问权限列表中启用的是 `GreenDailyRunner`，然后重新触发测试。不要通过给通用 Python、Bash 或终端授予权限来绕过问题。

Runner 缩小的是 TCC 授权身份和定时任务入口，而不是把 Python 放进文件系统沙箱。Runner 所启动的日报代码仍能继承该次运行所需的访问能力，因此应保护仓库、`.env`、Runner app 和 LaunchAgent plist，避免其他用户写入。

### Windows / JSON 回填

QQ 热镜像只支持 macOS。Windows PowerShell 脚本保留用于旧 ChatLab JSON，并默认附加 `--source json`。

## 5. GitHub Pages 历史预览

`pages/` 只包含静态前端，用于展示维护者过去生成的历史结果。`pages/config.js` 定义该预览实例的公开 R2 基址，所有日报请求直接发送到 R2 自定义域名。GitHub Actions 只在前端发生变化时部署 Pages，不会生成或发布新日报。

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
