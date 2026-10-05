# iPhone Duo 库存监控 + 辅助抢购（日本 Apple Store）

基于 **Java 17+** 的 Apple 日本官网（`apple.com/jp`）库存监控工具。它持续监控 iPhone Duo（也可切换 iPhone 18 Pro 等其它型号）各颜色/容量的**线上配送**与**门店取货**库存，一旦有货：

1. 立刻通过控制台、桌面通知、提示音、邮件，以及企业微信/钉钉/飞书/Slack/Discord/Telegram 提醒你；
2. **自动用默认浏览器打开购买页**。你提前在浏览器登录好 Apple ID、保存好地址和支付方式后，到货时只需「加入购物袋 → 结账 → 确认」几次点击。

> ⚠️ **关于「自动购买」**
> 本工具**不会**替你自动提交订单或支付，最后一步由你本人在浏览器中完成，原因如下：
> - Apple 结账流程需要 Apple ID 登录、双重认证和支付验证（3D Secure 等），程序代填这些步骤需要保存你的密码和信用卡信息，风险极高；
> - Apple 日本官网的销售条款禁止自动化程序下单，并会对异常订单进行取消、限购或封号；
> - 结账页频繁改版，全自动脚本经常在真正到货时失效，反而错过机会。
>
> 实际体验上，「秒级提醒 + 自动打开购买页 + 浏览器已登录」与全自动下单的速度差距很小，而且更稳定、更安全。

---

## 一、功能特性

| 模块 | 说明 |
| --- | --- |
| 日本区监控 | `apple.com/jp`，部件号 `xxxxJ/A`，支持邮编查询配送日期、门店号查询取货 |
| 三种检查模式 | `fulfillment`（配送 + 门店，推荐）/ `buyability`（仅线上可购，最轻量）/ `product-page`（HTML 兜底） |
| 型号预设 | 内置 `iphone-duo`、`iphone-18-pro` 预设，启动时选择或 `--model=` 指定 |
| 辅助抢购 | 有货时自动打开购买页，可限制标签页数量、命中后停止该 SKU |
| 随机抖动间隔 | 默认 5±3 秒，下限 3 秒 |
| 失败重试 | 指数退避 + 抖动；连续多轮失败自动冷却 |
| 会话 | 先访问产品页获取 Cookie，固定 UA、日语请求头，支持 HTTP/SOCKS5 代理池 |
| 多渠道提醒 | 控制台、桌面通知、提示音、邮件、企业微信/钉钉/飞书/Slack/Discord/Telegram |
| 去重 | 默认只在「无货→有货」时提醒；可设置持续有货时的重复提醒间隔 |
| 有货历史 | 写入 `data/availability-history.csv` |
| 配置热更新 | SKU、间隔、检查模式等修改后约 5 秒生效 |
| 自检命令 | `--once` 单轮检查、`--test-notify` 测试提醒、`--test-open` 测试打开浏览器 |

## 二、快速开始

### 1. 准备配置

```bash
cp application-example.yml application.yml
```

编辑 `application.yml`：
- **把 `models.iphone-duo.skus` 里的部件号换成真实值**（见第四节），示例中的 `MXXA1J/A` 等是占位符；
- 填写你的邮编 `postal-code` 和想取货的门店号 `stores`；
- 按需开启邮件/Webhook。

### 2. 构建

```bash
mvn clean package
# 产物：target/iphone-stock-monitor.jar
```

IntelliJ IDEA：打开项目 → 右键 `pom.xml` → Maven → Reload，运行 `StockMonitorApplication`。

### 3. 先自检，再正式运行

```bash
# 只检查一轮，确认部件号和网络正常（应看到「有货 / 无货」而不是「无法判断 / 失败」）
java -jar target/iphone-stock-monitor.jar --once

# 测试所有提醒渠道
java -jar target/iphone-stock-monitor.jar --test-notify

# 测试自动打开购买页
java -jar target/iphone-stock-monitor.jar --test-open

# 正式监控（Ctrl+C 退出并打印统计）
java -jar target/iphone-stock-monitor.jar
java -jar target/iphone-stock-monitor.jar /path/to/application.yml --model=iphone-duo
```

> Windows 控制台日文/中文乱码时，先执行 `chcp 65001`，再以 `java -Dstdout.encoding=UTF-8 -jar ...` 运行。

### 4. 抢购前准备（很重要）

1. 在常用浏览器登录 [apple.com/jp](https://www.apple.com/jp/) 的 Apple ID；
2. 在账户中保存好**配送地址**和**支付方式**（信用卡 / Apple Pay）；
3. 保持电脑开着、浏览器登录状态有效、不进入睡眠；
4. 到货后浏览器会自动打开购买页：选择型号 → 「バッグに追加」 → 「注文手続きへ」 → 确认下单。

## 三、配置说明（application.yml）

### monitor

| 字段 | 默认 | 说明 |
| --- | --- | --- |
| `base-url` | `https://www.apple.com/jp` | 日本官网 |
| `check-mode` | `fulfillment` | 见上表 |
| `postal-code` | `100-0005` | 日本邮编，用于配送日期与附近门店 |
| `stores` | `[R079]` | 门店号，第一个作为中心查询附近门店 |
| `interval.*` | 5 / 3 / 3 | 基础间隔、抖动、下限（秒） |
| `retry.*` | — | 指数退避重试参数 |
| `cooldown.*` | 5 轮 / 120 秒 | 连续全部失败多少轮后冷却多久 |
| `concurrency` | `2` | 并发检查数（需重启） |
| `renotify-seconds` | `300` | 0=只在到货瞬间提醒一次；>0=持续有货时重复提醒的间隔 |
| `active-model` | `iphone-duo` | 型号预设 key；留空则启动时询问 |
| `models.<key>.skus[]` | — | `part-number`、`name`、`enabled`，可选 `buy-url` |

### purchase（辅助抢购）

| 字段 | 默认 | 说明 |
| --- | --- | --- |
| `auto-open-browser` | `true` | 有货时自动打开购买页 |
| `open-once-per-restock` | `true` | 每次到货只打开一次 |
| `max-tabs-per-round` | `3` | 多个 SKU 同时到货时最多打开的标签页数 |
| `stop-sku-after-hit` | `false` | 命中后停止监控该 SKU |

### notify / http / proxy

- 邮件：Gmail 需开启两步验证并使用「应用专用密码」；密码通过环境变量 `SMTP_PASSWORD` 注入。
- Telegram：`TELEGRAM_BOT_TOKEN` 与 `TELEGRAM_CHAT_ID` 环境变量。
- 代理：在日本以外地区运行时，Apple 日本站一般也能访问；若频繁 403，可配置日本节点代理。

## 四、如何获取真实部件号（part number）

1. 打开 `https://www.apple.com/jp/shop/buy-iphone/iphone-duo`；
2. 按 F12 打开开发者工具 → Network，筛选 `fulfillment` 或 `buyability`；
3. 在页面上选择颜色和容量，观察请求 URL 中的 `parts.0=` 参数，例如 `parts.0=MXXXXJ/A`（日本区以 **`J/A`** 结尾，`%2F` 即 `/`）；
4. 把每个「颜色 + 容量」组合的部件号填入 `models.iphone-duo.skus`。

也可以在 Elements 中搜索 `J/A`，或在选择型号后查看地址栏/页面源码中的部件号。

## 五、如何获取门店号

在产品页点「受け取り可能な店舗を確認」，选择门店后在 Network 中查看 `fulfillment-messages` 请求的 `store=Rxxx` 参数。`R079` 为 Apple 銀座。

## 六、频率与风控建议

- 保持默认 3~8 秒随机间隔，不要调到 2 秒以下；`concurrency` 建议 1~3。
- 监控 SKU 越多，每轮请求越多；只启用你真正想买的组合。
- 若日志持续出现 403 / 429 / 541，说明触发了风控：调大间隔、减少 SKU，或稍后再试，不要加大并发。

## 七、热更新范围

保存 `application.yml` 后约 5 秒内生效：`monitor.models.*.skus`、`interval`、`retry`、`cooldown`、`renotify-seconds`、`check-mode`、`base-url`、`postal-code`、`stores`、`purchase.*`。

需要重启：`concurrency`、`proxy.*`、`notify.*`、`http.*`、所选型号。

## 八、输出

- 控制台：状态变化日志 + 每 30 秒状态面板；
- 日志：`logs/monitor.log`（按天滚动，保留 7 天）；
- 有货历史：`data/availability-history.csv`。

## 九、常见问题

**Q：`--once` 显示「无法判断」？**
部件号不正确或接口结构变化。先核对部件号；再尝试 `check-mode: buyability`。

**Q：显示「失败: HTTP 404」？**
产品页路径或部件号不存在，检查 `product-page-path` 与 `part-number`。

**Q：预购期间 buyability 一直显示有货？**
预购开始后即使配送要等几周，`isBuyable` 也为 true。想只在「近期可送达 / 门店可取」时提醒，请使用 `fulfillment` 模式并查看配送日期。

**Q：桌面通知没弹出？**
无图形环境（服务器、SSH）下自动禁用；Windows 需开启系统通知。

**Q：浏览器没自动打开？**
运行 `--test-open` 排查；Linux 需安装 `xdg-open`。日志中会打印购买链接，可手动点击。
