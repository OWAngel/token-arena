# ϟ Spark Arena

**自愿连接自己的 sparkDash，分享昨天的模型与 Token 用量。**

🌐 **[打开互动榜单](https://OWAngel.github.io/token-arena/)** · [报名与上报记录](https://github.com/OWAngel/token-arena/issues) · [公开数据说明](PRIVACY.md)

日榜 / 7 天 / 30 天、微信昵称搜索、模型筛选、输入 / 输出排名、模型明细、趋势和 CSV 导出。真实榜单默认空白；页面可切换明确标注的虚构演示。

只对接 **[MiaAI-Lab/sparkDash](https://github.com/MiaAI-Lab/sparkDash)**。每个人连接自己的实例，微信显示昵称代表该实例的所有者；多人共用实例时，这不是个人用量统计。平台不需要访问你的内网，也不保存 sparkDash 地址和访问令牌。

## 怎么参加

在**能够访问自己 sparkDash** 的电脑 / 服务器上，安装 Python 3.11+ 和 [GitHub CLI](https://cli.github.com/)，然后：

```bash
git clone https://github.com/OWAngel/token-arena.git
cd token-arena
gh auth login
```

若 sparkDash 启用了访问令牌，先保存到本机私有文件（终端隐藏输入；不会上传）：

```bash
python3 -m arena.client token
```

阅读 [PRIVACY.md](PRIVACY.md)，确认愿意公开昵称、GitHub 身份、每日模型及 Token 汇总后，报名：

```bash
python3 -m arena.client connect \
  --name '你的微信显示昵称' \
  --url 'http://你的sparkDash地址:5555' \
  --consent-public
python3 -m arena.client run --preview  # 看看昨天的汇总，不发布
python3 -m arena.client run            # 首次上报
python3 -m arena.client install-schedule
```

也可以在网站右上角点「连接我的 sparkDash」，填写昵称和地址即可生成加入命令，无需额外勾选。执行命令才会报名，仅打开页面或填写不会加入。GitHub 登录是报名身份，不需要给其他参加者仓库写权限。

`connect` 会先测试私有连接和小时历史接口，再创建公开报名 Issue。不会自动把这台电脑的其他 AI 工具或其他设备加入。它只读取 sparkDash 的 GET 接口；不会清空计数、修改配置或控制模型。

### 自动上传

- macOS：安装用户 LaunchAgent；Linux：安装用户 systemd timer。每小时检查一次，在北京时间 00:15 后上报前一天，已有同一日记录则更新，内容不变则跳过。配置安装在运行该命令的账户下。
- 电脑需要保持开机、具备内网访问和 GitHub 登录。休眠时不会上传，恢复后重试**当前的前一天**；不会声称离线期间的所有日期都已补齐。
- sparkDash 的小时历史保留 **72 小时**。允许用 `run --date YYYY-MM-DD` 手动补报仍在小时保留期内的完整自然日；过期则拒绝，不用 UTC 日累计冒充北京时间历史。
- Linux 用户 timer 默认依赖用户管理器在线；若打算登出后继续，管理员可按本机政策配置 `loginctl enable-linger`。本项目不自动改系统账户政策。
- Windows：用任务计划程序每小时运行 `python -m arena.client run`，起始目录设为仓库路径。使用执行任务的同一账户运行 `gh auth login` 和报名命令。Windows 没有自动安装计划任务。
- `SPARKDASH_TOKEN` 环境变量和 `connect --token-file /path/to/private-token` 可替代默认本地令牌文件。也可用 `--token-env-file /path/to/existing.env` 直接复用现有部署文件中的 `SPARKDASH_TOKEN` / `DASHBOARD_TOKEN`；只解析字面值，不执行脚本、不展开变量、不复制密钥。计划任务不继承交互 shell 的临时环境变量；推荐私有文件。POSIX 下凭据文件必须为 `0600`。
- 平台收到上报后触发 Actions，通常几分钟内更新；额外每小时重建一次。GitHub 排队、配额、服务异常可能造成延迟。页面显示最后成功构建时间。

### 暂停和退出

```bash
python3 -m arena.client leave
```

先在本地停止上报，再关闭自己所有报名 Issue。下一次成功构建会把你的历史记录从榜单移除。也可以直接在 GitHub 关闭自己的 `[participant]` Issue；上报器看到报名已关闭后会拒绝上传，不会偷偷重新报名。

想撤回某一天，关闭对应的 `[usage]` Issue；程序不会自动重新打开它。重新参加必须重新运行带 `--consent-public` 的 `connect`。公开 Issue、已下载文件、旧 Pages artifact 或第三方缓存不能保证彻底删除，见公开说明。

卸载定时器：

```bash
# macOS（上报器没有自动删除本地文件）
launchctl bootout "gui/$(id -u)" "$HOME/Library/LaunchAgents/cc.sparkarena.reporter.plist"
# Linux
systemctl --user disable --now spark-arena.timer
```

## 统计口径

接口：`GET /api/llm-token-totals/history`，`Authorization: Bearer …`（如果启用了认证）。支持反向代理路径前缀，也接受以 `/tokens` 结束的 UI 链接。请求直接连接、不经过系统代理，并拒绝重定向，避免把令牌带往其他地址。私有地址只由参加者本机访问；请在可信内网 / VPN 使用 HTTP，公网使用 HTTPS。

我们研究并对齐了 [sparkDash 源码 be35be9](https://github.com/MiaAI-Lab/sparkDash/blob/be35be9f594c65a3324f1d97ace58668d3a22068/server/llmtokens/LlmTokenLedger.js) 的实际响应结构：

| 上游字段 | 榜单字段 | 含义 |
|---|---|---|
| `hour[].t` | `date` | UTC 小时桶转换为北京时间自然日 |
| `modelId` | `model` | 按模型合并实例内所有 Spark / 端口 |
| `promptTokens` | `input_tokens` | 输入总量，包含缓存 |
| `completionTokens` | `output_tokens` | 已生成的输出 |
| `cachedTokens` | `cached_input_tokens` | 输入的子集，不再次加进总数 |
| — | `total_tokens` | 服务端重新计算为输入 + 输出 |

例如北京时间 10 月 19 日对应 UTC 10 月 18 日 16:00（含）至 10 月 19 日 16:00（不含）。**滚动 24 小时、UTC 日累计与昨日自然日不可互换。**

上游只存有流量的桶，缺桶按 0 汇总；但缺流量与监控中断无法完全区分。`coverage=partial` 表示保留的最早流量晚于该日开始（包括无历史）；`recorded-window` 只表示保留记录跨越该窗口，**并不保证 24 小时持续监控**。监控离线、首次安装、计数重置、引擎重启均可能少计。用量自报，未经独立审计，不能当作账单、个人贡献证明或模型能力分数。

## 平台如何工作

```text
参加者本机（私网）                         GitHub（公开）
自己的 sparkDash ──GET──> 本地上报器 ───> 报名 Issue + 每日汇总 Issue
  地址/令牌不外传                           │
                                       Actions 校验、去重
                                           │
                                      GitHub Pages 互动榜单
```

Issue 的实际作者数字 ID 决定身份，正文不能指定别人。相同作者、相同日期只取最新记录；不同人微信重名仍分开。报名和上报都要求 `consent_public=true`。参加者 / 日报关闭后不展示。构建只输出白名单字段，不执行 Issue 中的代码。公共报告不包括源地址、设备标识、凭据、完整上游响应或提示词。

### 本地开发 / 自建

零 Python 第三方运行时依赖，前端也是原生 JavaScript / CSS，无外部 CDN。

```bash
python3 -m unittest discover -s tests -v
node --test tests/*.test.js
python3 -m arena.build --repo OWAngel/token-arena
python3 -m http.server 8769 --directory dist --bind 127.0.0.1
```

自建时替换 `OWAngel/token-arena` 默认值和页面链接；在 GitHub Settings → Pages 选择 GitHub Actions，并启用 Issues、Actions。仓库只有标准 `GITHUB_TOKEN` 的最小构建权限，不需要存任何人的 sparkDash token。**不要把内网源地址 / bearer token 设为仓库公开变量。**

维护者可关闭不合规日报 / 报名、使用 GitHub block / report 控制滥用。开放报名不验证微信真实性，也不防止同一实例被多人重复认领；请遵守 [参与规则](CONTRIBUTING.md)。生产规模增大时应把认证、持久化、速率限制迁到专门后端。

## 来源与许可

受 [kky42/localmaxxing-arena](https://github.com/kky42/localmaxxing-arena) 的公开结果提交、自动重建榜单理念启发。该项目是模型基准测试榜，本项目是自愿的实例 Token 用量榜；未复制其源代码或评分模型。

sparkDash 由 [MiaAI-Lab](https://github.com/MiaAI-Lab/sparkDash) 开发。本项目独立实现 API 客户端，不修改或分发其源码，不代表 Mia 官方服务。我们只研究了其公开接口结构。

原创代码采用 [MIT](LICENSE) 许可。公开昵称和用量资料不因仓库代码许可而自动获得额外使用授权。
