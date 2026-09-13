# Lane

一套面向 Stash、Loon、Shadowrocket、Surge、Quantumult X 和 Egern 的分流配置。
Lane 使用同一份规则清单生成六端配置，提供地区自动选点、服务分类、中国大陆直连与
IPv4/IPv6 兜底。项目只负责分流，**不提供节点或订阅转换服务**。

## 下载配置

| 客户端 | 配置文件 |
| --- | --- |
| Stash | [Lane_stash.yaml](https://raw.githubusercontent.com/wenjinliuu/Lane/main/dist/stash/Lane_stash.yaml) |
| Loon | [Lane_loon.lcf（推荐）](https://raw.githubusercontent.com/wenjinliuu/Lane/main/dist/loon/Lane_loon.lcf) · [Lane_loon.conf（兼容）](https://raw.githubusercontent.com/wenjinliuu/Lane/main/dist/loon/Lane_loon.conf) |
| Shadowrocket | [Lane_shadowrocket.conf](https://raw.githubusercontent.com/wenjinliuu/Lane/main/dist/shadowrocket/Lane_shadowrocket.conf) |
| Surge | [Lane_surge.conf](https://raw.githubusercontent.com/wenjinliuu/Lane/main/dist/surge/Lane_surge.conf) |
| Quantumult X | [Lane_qx.conf](https://raw.githubusercontent.com/wenjinliuu/Lane/main/dist/qx/Lane_qx.conf) |
| Egern | [Lane_egern.yaml](https://raw.githubusercontent.com/wenjinliuu/Lane/main/dist/egern/Lane_egern.yaml) |

> 导入前请先保存为本地配置。不要把已经填入私人订阅地址的配置上传到公开仓库。
> Loon 现主推原生 `.lcf` 配置与 `.lsr` 规则；旧 `.conf` / `.list` 地址继续兼容。

## 首次使用

1. 打开上表中对应客户端的配置文件，下载或复制原始链接。
2. 按下表添加自己的节点订阅。`你的订阅地址` 只是占位文字，不是有效 URL。
3. 保存并启用本地配置，再开启节点订阅和远程规则的自动更新。

| 客户端 | 节点订阅位置 |
| --- | --- |
| Stash | `proxy-providers → Subscription1 → url` |
| Loon | `[Remote Proxy] → Subscription1` |
| Surge | `[Proxy Group] → Subscription1 → policy-path` |
| Quantumult X | 导入配置后，在 App 的 `设置 → 节点 → 节点资源` 中添加 |
| Egern | `我的节点 → urls` |
| Shadowrocket | 直接使用 App 内已有的节点订阅 |

不同客户端支持的订阅格式并不完全相同，同一条订阅链接不保证六端通用。多订阅设置、
配置升级和常见问题见 [使用指南](docs/usage.md)。

## 主要功能

- 地区策略：美国、日本、香港、台湾、新加坡，均提供 Auto 和 Manual。
- 服务策略：AI、Brokerage、Crypto、YouTube、TikTok、Emby、Streaming、Gaming、
  Telegram、Social、Developer、Google、Microsoft、Apple 和 Final。
- 中国分流：AppleCN 与中国域名优先直连，并使用中国 IPv4/IPv6 数据和客户端 GeoIP
  作为后续兜底。
- 专项规则：富途 / Moomoo、老虎、长桥和嘉信统一进入 Brokerage；Binance、OKX、
  Bybit、Bitget 进入 Crypto。
- 安全边界：不内置广告拦截、脚本、HTTPS 解密或 MitM 配置，也不收集私人订阅。

所有服务组默认跟随基础代理入口，也可手动选择 `DIRECT` 或某个地区策略。各客户端因
能力不同会保持少量界面差异：

| 客户端 | 基础代理入口 |
| --- | --- |
| Stash / Surge / Egern | `我的节点` 汇总真实节点，`Proxy` 先显示我的节点，再显示地区 Auto |
| Loon | `Proxy` 组合地区 Auto 与全部节点筛选 |
| Quantumult X | 使用 `代理选择`；QX 的 `proxy` 是内置保留名，因此不能建立同名 `Proxy` 组 |
| Shadowrocket | 使用 App 内置 `PROXY`，不额外生成基础代理组 |

## 更新说明

节点列表和远程规则可以独立更新，不需要频繁替换本地主配置。只有策略组、DNS、规则顺序
或客户端兼容性发生变化时，才需要重新下载完整配置，并重新填入订阅地址及个人修改。

### CN IP 稳定更新

项目每天自动检查上游，但不会直接照搬某一天的中国 IP 数据。Lane 从
[`gaoyifan/china-operator-ip`](https://github.com/gaoyifan/china-operator-ip) 读取最近 5 个
不同 UTC 日期的 IPv4/IPv6 快照，只发布在至少 3 份快照中出现的地址空间，以过滤单日或
短期的 BGP 数据波动。

新结果还会分别与上一版 IPv4、IPv6 覆盖范围比较；任一地址族变化超过 1%，自动更新立即
停止，必须人工核对并按候选 SHA-256 明确放行。项目另用
[`misakaio/chnroutes2`](https://github.com/misakaio/chnroutes2) 独立对照 IPv4，只做异常提示，
不会把它混入正式规则。也就是说，这是“每天检查、五日滚动、三次共识、异常熔断”，不是
每周才更新一次。

当前来源、快照日期和规则数量记录在
[`dist/metadata.json`](dist/metadata.json)，客户端转换差异记录在
[`dist/report.json`](dist/report.json)。

## 常见疑问

### 为什么配置中间会出现 `DIRECT`？

Lane 使用从上到下的首匹配规则。AppleCN、中国域名等已确认适合直连的流量会在对应位置
进入 `DIRECT`；境外域名、Telegram IP、CN IP 等仍按既定顺序继续判断。这些直连不是随机
插入，而是黄金分流顺序的一部分，尤其会确保 Brokerage IP 先于 China / CN IP 匹配。

### Domain 和 IP 为什么有时分开？

同一逻辑规则集里的 Domain/IP，在 Loon、Surge、Shadowrocket、Quantumult X 和 Egern
可以写在同一个文件；Stash 为使用低占用的 `domain`、`ipcidr`、`classical` provider，
会生成对应的专用载荷。

`Brokerage` 与 `Brokerage IP`、`Telegram` 与 `Telegram IP`、`China` 与 `CN IP` 则是为了
匹配阶段和顺序而有意分开：域名规则需要优先判断，IP 规则放在指定的后置位置。把它们简单
合并会改变 DNS 解析时机和首匹配结果，并可能破坏券商等已验证的分流。

### 为什么 Loon 的 `GEOIP,CN` 不写在本地？

Loon 的本地规则优先级高于插件和订阅规则，本地写入 `GEOIP,CN,DIRECT` 可能让后续插件规则
失去匹配机会。因此 Lane 将它放在最后一项远程规则 `cn-region.lsr` 中，本地 `[Rule]` 只
保留 `FINAL,Final`。逻辑顺序仍是 `CN IP → GEOIP,CN → Final`；其中 CN IP 是 Lane 每天维护
的稳定 CIDR，`GEOIP,CN` 只是客户端数据库的第二层兜底。

## 文档

- [使用指南](docs/usage.md)：多订阅、更新方式和常见问题
- [维护指南](docs/maintenance.md)：规则来源、生成流程、客户端约束与测试方法
- [第三方声明](NOTICE.md)：数据、图标来源及许可边界
- [`config/`](config/)：策略、规则顺序、地区筛选和图标的声明式配置

## 许可

Lane 自有代码采用 [MIT License](LICENSE)。第三方规则数据和图标遵循各自许可；详细来源
及适用范围见 [NOTICE.md](NOTICE.md) 和 [`licenses/`](licenses/)。
