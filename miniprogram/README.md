# Spark Arena 独立微信小程序（开发分支）

本目录是原创原生微信小程序，不使用 Miratap 的 AppID、源码、发布账号、业务数据或后端。

**当前状态：代码与合成测试可用；已配置独立 AppID `wx48f0bffa783c8e1d`，服务端凭据已通过微信官方校验，已部署只读 HTTPS 测试入口；真实微信登录尚未联调、未提审。** 账号名称和主体以微信后台实际核验为准；不要把开发包视为已上线小程序。

## 已实现

- 原生榜单：日 / 7 / 30 天、模型筛选、展开每位参加者的模型明细、跨日刷新和分享公开榜单。
- 使用 `wx.login` 的一次性 code，在服务端向微信固定官方接口换取身份。小程序和公开榜单没有 AppSecret、OpenID、UnionID。
- 微信登录不自动报名；本人填写昵称并同意公开后，才进入微信榜单。账号身份与展示昵称分开，昵称不代表实名或不可冒充。
- 生成 10 分钟、一次性的高熵设备绑定码。上报器用隐藏输入消费，获得仅可上传自己日报的设备凭据。
- 微信设备端的独立定时任务，复用 sparkDash 昨日自然日采集；不依赖参加者有 GitHub 账号。
- 撤销设备、退出登录、退出榜单；退出和每日撤回保留撤回标记，设备不会自动重发已撤回日报。
- GitHub 网页榜单是独立渠道；当前 Peter 的 GitHub 配置、Issue、上报任务和 Pages 没有迁移或替换。

## 需要 Peter 完成的外部步骤

1. 已收到独立 AppID（公开标识）。在 [微信公众平台](https://mp.weixin.qq.com/) 核对 **Spark Arena** 账号及开发者权限；扫码、账号密码、主体资料、协议确认及任何收费由本人处理。
2. AppSecret 已保存到受保护的后端配置并通过官方接口校验，未进入仓库。该凭据校验不等于真实 `wx.login` / `code2session` 已联调；后续密钥仅通过受保护的配置文件更新。
3. 已建立独立 HTTPS 测试入口。下一步在该小程序后台将 `https://arena.miratap.cc` 加入 request 合法域名，按后台提示完成管理员验证；域名可用性/主体适用性以后台结果为准。

注册费用、主体可选项、名称可用性、类目、备案和审核要求以实际官方后台提示为准。本项目没有代替官方审核给出结论。

## 在开发者工具导入

- 导入本目录。`project.config.json` 已使用独立 AppID `wx48f0bffa783c8e1d`；需使用具有该小程序开发者权限的微信登录开发工具。
- `config.js` 的 `API_BASE` 暂留空：通过 `PUBLIC_BOARD_URL` 只读独立测试榜单，微信报名按钮禁用。账号身份标签取自记录；旧GitHub渠道的记录不会标成微信登录账号。
- 后端配置好后，将 `API_BASE` 设为专属 HTTPS 基址，并在微信后台配置对应的 request 合法域名。
- `urlCheck` 默认开启。本地模拟使用微信开发者工具认可的调试方式；不要把跳过域名检查的设置作为生产配置。
- 先前 CLI 因服务端口关闭未能导入；本轮已通过原生工具界面导入并编译运行，未开启该端口。已检查榜单布局、错误态及报名禁用；真机预览、真实登录与隐私授权仍未验收。
- 此前GitHub公开快照域名不在微信合法域名列表中，现已将只读来源切换为独立HTTPS入口；需在后台将 `https://arena.miratap.cc` 加入 request 合法域名。不要关闭域名检查。

## 独立后端

后端入口：`python3 -m arena.wechat_server`，只监听 loopback。模板见 [deploy/wechat](../deploy/wechat)。Python 3.11+，无额外 Python 运行依赖。

### 当前只读测试入口

- `https://arena.miratap.cc/health`：服务健康检查；`https://arena.miratap.cc/v1/board`：微信渠道空榜单。已从服务器及本机读取，均 HTTP 200。
- 反代暂时仅允许上述只读路径；登录/报名/配对/上传路径未开放，写方法被拒绝。小程序 `API_BASE` 仍留空，报名保持禁用；这是准备真实联调的测试入口。
- 使用独立 DNS、证书、系统账户、服务和数据库；没有挂接旧业务接口。服务已启用开机启动，设置256MB内存及50% CPU上限。
- 只读模板为 `nginx-readonly.conf.example`；`nginx.conf.example` 为后续完整API模式参考，不能在隐私资料和真实联调完成前直接替换上线。证书续期hook示例仅作用于本项目证书。
- 当前证书和公网传输验证不代替微信合法域名、备案适用性、账号权限或真机验收。

必需的私有配置：

| 名称 | 用途 |
|---|---|
| `WECHAT_APPID` | 新小程序 AppID，不能使用 Miratap ID |
| `WECHAT_APPSECRET` | 只在服务端调用微信 code2session |
| `ARENA_IDENTITY_KEY` | 32 字符以上随机密钥；稳定保存，用于生成本平台专用公开身份 ID |
| `ARENA_WECHAT_DATA` | 私有持久化目录，SQLite / WAL 不进入 Git 或 Pages |
| `ARENA_TRUSTED_PROXIES` | 生产反代的明确地址列表；配套模板为 `127.0.0.1` |

生产必须在 HTTPS 反代后运行，反代覆盖 `X-Real-IP`。应用只信任显式配置的代理，不接受任意来源伪造的转发头。反代另设限流、请求体与超时限制。单节点 SQLite 部署需持久盘、私有权限和备份；没有横向扩容或高可用承诺。

### 身份和数据边界

| 操作 | 授权 |
|---|---|
| 读取微信榜单 | 公开，只输出昵称、伪名化 ID、日期、模型和 Token 汇总 |
| 微信登录 | code 由微信服务器验证，客户端不能指定 OpenID 或账号 ID |
| 修改昵称 / 报名 / 绑定码 / 撤回 / 退出 | 微信登录会话，24 小时有效 |
| 消费一次性绑定码 | 10 分钟、单次、32 字符随机绑定码；只发放设备上传凭据 |
| 上传日报 | 设备凭据，只能写所属用户，不能改昵称、生成绑定码或控制其他用户 |

会话、设备凭据及绑定码在数据库只存 SHA-256；公开身份由 AppID + 微信身份 + 服务端 HMAC 密钥生成。每次授权和数据变更在 SQLite 事务内完成，退出与上传跨 worker 串行化。退出会撤销设备、隐藏并标记历史，不会在重新报名时自动恢复旧日报。仅退出登录不等于退出榜单。

### API

`POST /v1/wechat/login` · `GET /v1/me` · `PUT/DELETE /v1/profile` · `DELETE /v1/session` · `POST /v1/pair` · `POST /v1/pair/consume` · `DELETE /v1/devices` · `PUT /v1/reports` · `DELETE /v1/reports/YYYY-MM-DD` · `GET /v1/board`。

JSON 请求体上限 64 KiB，不接受 URL 参数携带凭据。默认不开放 CORS。应用与客户端不记录密钥或完整请求体；正式部署的反代也不得记录 Authorization、绑定码或登录 code。

## 本地上报器（微信账号）

在能够访问自己 sparkDash 的设备上，克隆包含本分支的代码。微信小程序中完成登录、自愿报名，生成一次性绑定码，然后：

```bash
python3 -m arena.wechat_client bind \
  --api-base 'https://你的独立API域名' \
  --url 'http://自己的sparkDash地址:5555' \
  --consent-public
# 绑定码在隐藏提示中粘贴，不放进命令行、URL或日志。
python3 -m arena.wechat_client run --preview
python3 -m arena.wechat_client run
python3 -m arena.wechat_client install-schedule
```

需要 sparkDash 令牌时，可追加 `--token-file /path/to/private-token` 或 `--token-env-file /path/to/existing.env`，均要求 POSIX 0600。地址和源令牌留在设备端；微信服务只收到最小日报。

配置独立存入 `~/.config/token-arena/wechat.json`（或 XDG 对应位置），其中包含仅用于日报上传的设备凭据，权限 0600。macOS 任务标签 `cc.sparkarena.wechat-reporter`；Linux timer `spark-arena-wechat.timer`。不会覆盖现有 GitHub 定时任务。

任务在本机开机联网时每小时检查，北京时间 00:15 后上传前一天。重复日期在服务端更新同一条；小时保留期与监控缺口规则沿用原 sparkDash 采集。暂停本机上报：`python3 -m arena.wechat_client pause`；隐藏榜单历史须在小程序选择退出。

## 验证

```bash
python3 -m unittest discover -s tests -v
node --test tests/*.test.js
```

测试只用合成身份、临时数据库与 loopback HTTP，包含 code 身份映射、同名区分、scope、绑定码并发单次消费/过期、日报撤回、重启持久化、退出再参加、受信代理、跨日刷新，以及真实本地 HTTP 的采集→绑定→上报→撤销闭环。

## 正式上线前仍需完成

- AppID 对应账号/开发者权限、微信后台合法域名及域名适用性核验；生产API开放与运行方式、并发/超时、监控及备份验收。当前仅只读测试模式。
- 真机登录与隐私授权、合法域名、会话过期、绑定码与网络故障联调；原生工具编译与未配置后端的禁用状态已核验。
- 正式运营主体、联系方式、完整隐私保护指引、数据保留与删除流程；当前隐私页明确标注开发状态，上线前必须替换。
- 根据正式微信后台要求接入昵称内容安全审核、类目与其他审核材料。当前昵称只有长度/控制字符校验，不宣称满足正式内容审核要求。
- 取得实际提审与发布回执。完成这些之前不把代码 PR、合成测试或游客模式称为微信小程序上线。

技术参考：[微信登录](https://developers.weixin.qq.com/miniprogram/dev/framework/open-ability/login.html)、[头像昵称填写](https://developers.weixin.qq.com/miniprogram/dev/framework/open-ability/userProfile.html)、[腾讯云微信身份说明](https://docs.cloudbase.net/lowcode/app/mp)。
