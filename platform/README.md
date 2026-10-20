# Spark Arena 无需账号的网页版

入口：**https://arena.miratap.cc/**。只对接 Mia 的 sparkDash，无需 GitHub、微信、手机号或邮箱登录。

## 参加

1. 点击「连接我的 sparkDash」，填写公开昵称和自己的 sparkDash 地址。地址不发送到平台。
2. 点击「加入并生成绑定码」，保存管理密钥。无需额外勾选；仅浏览、填写不会报名。
3. 在能够访问 sparkDash 的电脑上运行页面生成的命令。需 Python 3.11+；平台提供上报器 ZIP，不需 Git 或 GitHub CLI。命令不会包含管理密钥或绑定码。
4. 在隐藏输入中粘贴绑定码，完成本地采集验证和绑定。若源需要令牌，可在 bind 命令加 `--token-file` 或 `--token-env-file` 指向本人私有文件，POSIX 权限需0600。
5. macOS / Linux 自动安装独立小时检查任务；北京时间00:15后上报前一天。Windows 解压后运行相同 bind/run 命令，并自行配置任务计划程序。

地址与源令牌留在设备端，服务只收昵称、日期、模型及 Token 汇总。多人共用一个 sparkDash 时统计整个实例。设备离线会漏报，更早历史不保证补齐。

## 管理与退出

管理密钥仅存于本浏览器，可下载备份，在其他浏览器粘贴恢复。服务端只存哈希。它相当于密码，不能分享；丢失不能仅凭昵称找回。一年到期后同时撤销设备并隐藏该身份记录，继续参加需重新加入。

管理面板支持改昵称、生成10分钟单次绑定码、撤销所有设备及退出榜单。移除浏览器密钥不等于退出，不会停止设备上报。退出隐藏历史并撤销设备；重新参加不会自动恢复撤回日报。隐私联系见 [公开说明](https://arena.miratap.cc/privacy.html)。

设备配置独立保存在 `~/.config/token-arena/platform.json`，macOS 任务为 `cc.sparkarena.platform-reporter`，Linux timer为 `spark-arena-platform.timer`。不替换旧 GitHub 或微信配置。暂停设备：`python3 -m arena.platform_client pause`。

## 部署

- `arena.platform_server:create_app()`：WSGI factory；不需要 AppID、AppSecret 或 GitHub token。
- 环境：`ARENA_PLATFORM_DATA` 私有持久目录；`ARENA_TRUSTED_PROXIES` 显式代理地址。
- `deploy/platform/requirements.txt` 固定已部署的 Gunicorn 版本；systemd 示例使用2 worker、每 worker 2线程、loopback监听，256MB内存上限。
- `deploy/platform/nginx-locations.conf.example` 放在专属HTTPS虚拟主机中。API在 `/api/`，原生微信的 `/v1/` 可独立保留；exact join覆写代理头并额外限制1次/分钟（突发2次）。应用另有每IP120次/分钟限流与总报名名额上限。
- `python3 tools/package_platform.py /tmp/platform-release.tar.gz` 只打包列明的源码与静态资源，并生成不含配置的上报器ZIP；部署时把 `public` 作为静态根目录。
- 使用私有数据目录0700、SQLite0600及独立系统账户。变更后检查实际 `nginx -t`、服务、TLS、公开资源及未授权管理401。

当前独立平台已部署试运行，公开榜单为空，未替用户或其他人自动报名/迁移；微信版仍是单独的登录联调状态。长期运行的备份恢复、并发容量和监控告警仍需进一步验收。

## 验证

`python3 -m unittest discover -s tests -v`、`node --test tests/*.test.js`。

包含合成HTTP采集→无账号加入→绑定→日报去重→退出、管理到期同步撤销、身份同名区分、来源地址不上传、密钥恢复失败仍可移除及独立调度。仅用临时数据库/合成数据做写入测试；公网只做只读健康、资源、空榜单与拒绝未授权的验证。
