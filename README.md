# 保研与科研日报

基于 [jielosc/csbaoyan-chat-daily](https://github.com/jielosc/csbaoyan-chat-daily) 的个人日报项目，保留原站的阅读样式、日期切换、全文搜索和深浅色模式。

网页由 GitHub Pages 托管。Windows 登录后从 QQ 回读前一天的群聊历史，使用已登录的 Codex 生成脱敏日报，自动更新网站。无需额外模型 API Key。

## 内容

- 保研：院校项目、申请时间、考核与经验。
- 科研：研究问题、论文阅读、实验、复现与写作方法。
- 学习：课程、书籍、项目和工具；说明适合谁、前置基础与开始方式。
- 过滤：重复焦虑、纯粹攀比、无信息量的情绪表达和无关闲聊；有参考价值的录取样本、选校比较、真实风险和失败经验仍保留，并说明适用条件。

原始消息、QQ 登录状态、访问密钥与本机配置都不进入 Git 仓库。公开目录 `pages/` 只放网页及最终脱敏日报。部署任务只上传该目录。

## 整理结构

沿用原项目的[提取与分板块编辑规则](https://github.com/jielosc/csbaoyan-chat-daily/blob/7eb3428d184fef84ee60381c5fa489b0d483be30/src/csbaoyan_daily/domain/report_generation.py)及[结构校验](https://github.com/jielosc/csbaoyan-chat-daily/blob/7eb3428d184fef84ee60381c5fa489b0d483be30/src/csbaoyan_daily/domain/report_schema.py)，加入科研学习主题，省略无关趣闻。

- **今日值得关注**：按院校与项目、申请与考核、经验与选择、科研与学习组织重点。先写具体事件或研究问题，不把每条信息都改成行动建议。
- **今日讨论脉络**：按时间呈现提问、补充、分歧与纠正，明确讨论是否得到答复。同一资源集中说明方法、学习价值、前置基础和已知限制。
- **传闻与待核实**：分开写消息说法、不确定原因和核实渠道；没有答复的问题不能被改写成事实。

提取沿用最多400条消息、约2万字、相邻20条重叠的窗口。每批分别提取重点、讨论和疑问；最终对三个板块独立编辑，再生成导读。程序校验每条引用、各类候选证据边界和已有讨论时段的覆盖，避免合并时把待核实条目升为确定结论。校验通过不代表群内说法已获官方证实。

通常保留6–9条重点（最多12条），讨论脉络最多24段、待核实最多8条，信息不足时留空。公开页面不展示内部证据编号，不重复添加“怎么开始”和依据小字。

## 运行边界

QQ 历史接口可能无法补齐离线期间的所有消息。程序必须记录读取范围、疑似序号缺口及分页是否推进，并在日报中说明覆盖情况。没有读取成功时，不生成虚假的“当天没有消息”。图片、语音及未解析的转发不作为已读内容。

本项目使用 NapCat 的非官方 QQ 接入；首次需要在本机登录，QQ 要求重新验证时仍需人工处理。Windows 只负责采集和生成，网页并不依赖本地服务器。

## 开发

原始 Python 生成器保留在 `src/csbaoyan_daily/`，原始部署说明保留在 `docs/`，可作为其他接入方式的参考。Windows/Codex 自动化位于 `automation/`。

## Windows 自动更新

准备 PowerShell 7、Windows QQ、Node.js 22 或更新版、已登录的 Codex CLI，以及已登录且有仓库写权限的 GitHub CLI。Codex 使用现有的 ChatGPT 登录；不需要另外配置模型 API Key。

1. 从 [NapCat 官方发布页](https://github.com/NapNeko/NapCatQQ/releases) 下载 Shell 包，解压至 `vendor/napcat/napcat/`，其中应包含 `NapCatWinBootMain.exe` 和 `napcat.mjs`。程序通过本机已有的完整 QQ 安装启动。
2. 在项目目录执行 `npm ci --ignore-scripts`，再运行 `node automation/setup.mjs --groups 你的群号 --repository 你的用户名/仓库名`。正常退出桌面 QQ，运行 `pwsh -NoProfile -File automation/login-qq.ps1 -Scan`，打开它提示的二维码图片，用手机 QQ 扫码并确认。登录状态和接口密钥只保存在本机。
3. 运行 `node automation/setup.mjs --enable`，再运行 `pwsh -NoProfile -File automation/start-daily.ps1 -NoPublish` 测试完整流程：快速登录、采集昨天的历史、关闭本次 QQ 会话、生成草稿。输入保存在 `.private/inputs/日期.json`，草稿位于 `.private/drafts/`。
4. 验证通过后，不带 `-NoPublish` 运行启动脚本即可发布。运行 `pwsh -NoProfile -File automation/install-startup.ps1` 注册 Windows 登录任务。

任务在 Windows 登录后整理前一天，已经发布的日期不会重复生成。关机期间不运行，也不自动补发多个更早日期。桌面 QQ 已运行时，程序会记录冲突并退出，不强行关闭它。QQ 登录过期需要重新扫码。

`automation/run.mjs` 默认会发布；`--collect-only` 只采集，`--no-publish` 只生成本地草稿，`--date YYYY-MM-DD` 指定历史日期，`--force` 允许重新生成已发布日期。任务状态见 `.private/status.json`。用 `automation/uninstall-startup.ps1` 移除登录任务。

测试：`npm test`。发布只更新 `pages/reports/日期.md` 和 `pages/reports.json`；GitHub Actions 随后更新 Pages 网站。

## 许可

MIT。保留原作者版权与 [LICENSE](LICENSE)。
