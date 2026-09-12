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

项目每天自动检查上游数据。当前来源和规则数量记录在
[`dist/metadata.json`](dist/metadata.json)，客户端转换差异记录在
[`dist/report.json`](dist/report.json)。

## 文档

- [使用指南](docs/usage.md)：多订阅、更新方式和常见问题
- [维护指南](docs/maintenance.md)：规则来源、生成流程、客户端约束与测试方法
- [第三方声明](NOTICE.md)：数据、图标来源及许可边界
- [`config/`](config/)：策略、规则顺序、地区筛选和图标的声明式配置

## 许可

Lane 自有代码采用 [MIT License](LICENSE)。第三方规则数据和图标遵循各自许可；详细来源
及适用范围见 [NOTICE.md](NOTICE.md) 和 [`licenses/`](licenses/)。
