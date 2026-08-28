# Lane

一份规则清单，生成 Stash、Loon、Shadowrocket、Surge、Quantumult X 与 Egern 六种客户端配置。只有一个版本，不区分通用版与个人版；策略组、地区筛选和上游数据由同一套声明式配置管理。

**主配置本地保存，节点订阅与远程规则独立更新。** 不需要额外安装覆写、脚本或订阅转换服务。

## 当前设计

- 所有策略组名称均使用简洁英文。
- `AI`、`Google`、`Developer`、`Telegram`、`Social`、券商、交易所、视频、游戏平台等服务组均默认选择 `Manual`。
- `Manual` 包含用户导入的全部节点，不排除流量、到期、高倍率或维护信息项。
- 地区仅保留美国、日本、香港、台湾与新加坡；每个地区分别提供 `XX Auto` 自动优选和 `XX Manual` 手动选点。
- 策略组按 `Manual`、服务组、地区组排列，十个地区 Auto / Manual 组统一放在列表末尾。
- 地区筛选只使用国旗、简体中文地区名、英文全称与常见简称做正向匹配，不使用城市、机场代码或排除词。
- 服务组可切换到 `DIRECT`，或五个地区各自的 Auto / Manual 策略。
- `Brokerage` 合并 Futu、Moomoo、Tiger 与 Longbridge；`Schwab` 单独成组。除 v2fly 上游外，还合并经过实际使用的补充域名与 Futu IP 段。
- `Crypto` 只匹配 Binance、OKX、Bybit 与 Bitget。其他交易所不单独分类，按后续规则或 `Final` 处理。
- 中国大陆 AI 不设专门规则，自然落入 `cn` / `GEOIP,CN` 直连。
- 不设置游戏大文件下载特例，不内置广告拦截，也不生成默认 `REJECT` 规则。
- 未命中流量进入 `Final`，而 `Final` 默认跟随 `Manual`。

完整策略声明见 [`config/policies.yaml`](config/policies.yaml)，规则顺序见 [`config/rulesets.yaml`](config/rulesets.yaml)。

### Brokerage、Crypto 与 Schwab

这三个组都默认选择 `Manual`，也可独立切换为 `DIRECT` 或某个地区的 Auto / Manual。下面的直连建议不会改变配置的默认值；六端配置顶部也保留了简短说明。

| 策略组 | 覆盖范围 | 用途与选择建议 |
| --- | --- | --- |
| `Brokerage` | 富途 / Moomoo、老虎 Tiger、长桥 Longbridge | 统一处理相关域名与 IP 的网络分流，用于登录、行情及入金、交易相关连接；可按实际连通性选择代理或直连。 |
| `Crypto` | 币安 Binance、OKX、Bybit、Bitget，仅这四家 | 当前网络可以正常访问时，建议手动选择 `DIRECT`；无法正常访问时可按实际情况选择代理。其他交易所按后续规则或 `Final` 处理。 |
| `Schwab` | 嘉信 Charles Schwab | 与 `Brokerage` 分开控制网络路径；当前网络可以正常访问时，可手动选择 `DIRECT`，也保留代理选项。 |

`Brokerage` 在上游规则外，保留了实际使用中补充的域名与 Futu IP 段，包括老虎的 `skytigris.cn` 和长桥的 `geotest.lbkrs.com`。这些规则是域名/IP 匹配，不是对整个应用的识别；入金流程涉及的外部银行、支付页面仍按各自命中的规则处理。

Lane 只控制网络路径，不保证入金或交易成功，也不改变账户权限、银行处理或平台限制。三个组彼此独立，但选择 `Manual` 时都会跟随同一个手动节点。

## 使用配置

| 客户端 | 配置地址 |
| --- | --- |
| Stash | [Lane_stash.yaml](https://raw.githubusercontent.com/wenjinliuu/Lane/main/dist/stash/Lane_stash.yaml) |
| Loon | [Lane_loon.conf](https://raw.githubusercontent.com/wenjinliuu/Lane/main/dist/loon/Lane_loon.conf) |
| Shadowrocket | [Lane_shadowrocket.conf](https://raw.githubusercontent.com/wenjinliuu/Lane/main/dist/shadowrocket/Lane_shadowrocket.conf) |
| Surge | [Lane_surge.conf](https://raw.githubusercontent.com/wenjinliuu/Lane/main/dist/surge/Lane_surge.conf) |
| Quantumult X | [Lane_qx.conf](https://raw.githubusercontent.com/wenjinliuu/Lane/main/dist/qx/Lane_qx.conf) |
| Egern | [Lane_egern.yaml](https://raw.githubusercontent.com/wenjinliuu/Lane/main/dist/egern/Lane_egern.yaml) |

### 首次使用

1. 下载对应配置。除 Shadowrocket 外，在下表指定的订阅字段中，将 `你的订阅地址` 替换为服务提供商为该客户端提供的完整订阅链接；占位符统一不加引号。第一份模板默认启用，第二份已注释，只有一个订阅时无需改动第二份。
2. `你的订阅地址` 只是占位文字，不是有效 URL，Lane 不提供节点。部分客户端可能在导入时校验地址，请先在本地填写，再导入并复制/保存为本地配置，不让整份配置继续跟随远程更新。仅改显示名称不等于本地化；Surge 托管配置需先创建普通副本，Egern 不设置主配置 `auto_update`。
3. 保存并启用配置，在 `Manual` 中选一个节点。服务组默认跟随 `Manual`，也可选择直连或地区 Auto / Manual。Shadowrocket 不含订阅模板，继续使用应用内已有节点订阅。
4. 开启客户端的节点与规则资源自动更新。配置内能指定的更新间隔为 24 小时；Loon 的资源定时更新在应用设置中管理。客户端后台调度、联网状态和订阅可用性仍会影响实际更新时间。

| 客户端 | 第一份订阅填写位置 |
| --- | --- |
| Stash | `proxy-providers → Subscription1 → url`，使用 Stash / Clash 格式节点订阅 |
| Loon | `[Remote Proxy]` 的 `Subscription1 =` 后面，使用 Loon 支持的格式 |
| Surge | `[Proxy Group]` 的隐藏组 `Subscription1`，替换 `policy-path=` 后面的占位符；使用 Surge 节点列表或包含 `[Proxy]` 的配置 |
| Quantumult X | `[server_remote]` 中 `tag=Subscription1` 那一行的占位符，使用 QX 原生节点订阅；该段保持在 `[policy]` 之后 |
| Egern | `policy_groups → Manual → urls` 的第一个占位符，使用 Egern 支持的节点订阅 |
| Shadowrocket | 无模板，直接使用应用内已有节点订阅 |

订阅格式必须兼容目标客户端：不能保证同一条链接在六个软件里通用。本项目不代用户转换或收集私人订阅；不要把填好的配置上传到公开仓库。

Loon 用户若选择重新导入远程配置，请选择保留现有节点/订阅，不要全部覆盖。其他客户端也应先备份；换用新版完整主配置时，重新填入订阅地址并迁移个人修改。

### 多份订阅

每个带订阅模板的客户端都提供一份启用模板和一份注释模板，填写位置旁也有简短操作提示。需要第二份时，取消对应模板行首的 `#` 和紧跟的一个空格、填入第二份链接；YAML 要保留原有缩进。不要直接取消全部注释，也不要把多个链接拼进同一个 URL 字段。

| 客户端 | 第二份订阅 | 第三份及更多订阅 |
| --- | --- | --- |
| Stash | 取消 `Subscription2` 整块注释并填写 `url`，包括该块的更新与测速参数 | 复制整块，名称依次改为 `Subscription3` 等；现有 `include-all` 会纳入全部代理集，无需逐个改策略组 |
| Loon | 取消 `Subscription2 =` 行的注释并填写 | 复制该行，使用不同别名；现有节点筛选会处理所有订阅 |
| Surge | 取消隐藏组 `Subscription2` 的注释并填写，再把 Manual 的参数改为 `include-other-group="Subscription1,Subscription2"` | 新增 `Subscription3` 等隐藏组，并逐一加入 Manual 的引用列表 |
| Quantumult X | 取消 `tag=Subscription2` 那一行的注释并填写 | 复制该行，使用不同的 `tag`；现有策略组会按节点名称筛选 |
| Egern | 取消 Manual 的 `urls` 下第二个列表项的注释并填写 | 在同一 `urls` 列表下逐行追加地址，无需新增策略组 |
| Shadowrocket | 在应用内添加 | 在应用内继续添加，Lane 不放订阅模板 |

Surge 的订阅由隐藏组加载，`Manual` 通过 `include-other-group` 展开这些组的全部节点，地区组再从 Manual 中筛选，并非只取得隐藏组当前选中的一个节点。因此可见策略组仍按 Manual、服务组、地区组排列；不能只启用第二份订阅却漏改 Manual 的引用。[Surge 节点引用](https://manual.nssurge.com/policy-groups/policy-including.html)、[隐藏组参数](https://manual.nssurge.com/policy-groups/parameters.html)。

订阅别名不同不代表节点名称不会重复。多个订阅尽量避免同名节点：Surge 和 Egern 都有按名称去重的行为；Surge 如需区分，可在各订阅组分别添加 `external-policy-name-prefix=S1-`、`external-policy-name-prefix=S2-`。这不是默认配置，不影响地区正向匹配。[Surge 节点命名](https://manual.nssurge.com/policy-groups/policy-including.html)、[Egern 多订阅](https://egernapp.com/docs/configuration/policy_groups/)。

### 哪些内容会更新？

| 内容 | 更新来源 | 是否更换本地主配置 |
| --- | --- | --- |
| 节点列表 | 服务提供商订阅 | 不需要 |
| 已引用规则集中的域名、IP | Lane 的远程规则文件 | 不需要 |
| 策略组、DNS、规则引用及顺序、兼容性修复 | 新版 Lane 主配置 | 需要按升级说明迁移 |

图标通过 Qure 的公开 URL 引用：Stash/Egern 使用 `icon`，Loon/QX 使用 `img-url`。Shadowrocket 不强制自定义图标；Surge 的官方 `icon-url` 当前标注为 Mac 功能，本配置以 iOS 兼容为先，不设置它。

### 客户端兼容性

- Stash 与 Egern 保留域名正则；Loon、Shadowrocket、Surge、QX 中不支持或未确认兼容的域名正则会省略，逐规则集计数见 `dist/report.json`，不会误转换为 URL 重写。
- Egern 使用原生 YAML 规则集，保留 `no_resolve`，地区组通过 `flatten` 展开订阅节点；请使用支持 `urls` / `flatten` 的当前版本。
- QX 使用原生 `host` / `host-suffix` / `ip-cidr` / `ip6-cidr`，不写入 Surge 风格的 `no-resolve`。QX 自身的域名/IP 匹配优先级与其他内核不同，不能保证所有重叠规则逐条等价。没有额外加入抢先匹配的默认 CN/LAN 资源。
- Auto 使用各客户端原生自动测速类型，Manual 使用手动类型；Surge 自身允许临时手动覆盖自动组，Lane 不把自动组改成手动组，也不能禁用客户端的这项 UI 功能。
- 六端均通过静态结构与生成测试；测试不等于在六款付费客户端上完成真机导入、联网验证。订阅协议和空地区组行为仍需在实际客户端确认。

格式依据：[Stash 代理集](https://stash.wiki/proxy-protocols/proxy-providers)、[Loon 官方示例](https://github.com/Loon0x00/LoonExampleConfig/blob/master/example.conf)、[Surge 节点引用](https://manual.nssurge.com/policy-groups/policy-including.html)、[QX 官方示例](https://github.com/crossutility/Quantumult-X/blob/master/sample.conf)、[Egern 策略组](https://egernapp.com/docs/configuration/policy_groups/)、[Egern 规则](https://egernapp.com/docs/configuration/rules/)。

## 目录结构

```text
config/                 项目、策略、图标、上游与规则清单
rules/custom/           少量本地维护规则
src/proxyrules/         解析、编译、渲染与校验代码
dist/stash/             Stash 配置与规则
dist/loon/              Loon 配置与规则
dist/shadowrocket/      Shadowrocket 配置与规则
dist/surge/             Surge 配置与规则
dist/qx/                Quantumult X 配置与规则
dist/egern/             Egern 配置与 YAML 规则集
tests/                  单元测试
```

## 本地生成

需要 Python 3.11+ 与 Git：

```bash
python -m pip install -e '.[dev]'
lane build --refresh
python -m pytest
lane check
```

离线复现已缓存的上游版本：

```bash
lane build --offline
```

也可以传入本地的 `v2fly/domain-list-community` 仓库：

```bash
lane build --upstream-dir /path/to/domain-list-community
```

## 自动更新

GitHub Actions 每天 UTC 04:00（北京时间 12:00）执行以下流程：

1. 拉取最新 v2fly 域名库与 Telegram 官方 CIDR。
2. 编译六端规则并运行测试、结构校验。
3. 仅在 `dist/` 真实变化时创建自动更新提交。

`dist/metadata.json` 记录上游 commit、文本源 SHA-256 与规则集数量；`dist/report.json` 记录客户端转换差异。每日构建也检查主配置，但只有主配置实际内容变化才更新它及其北京时间；规则集更新不强制用户升级本地主配置。主配置里的时间不是设备上规则资源最近一次下载时间。

项目已从 `ProxyRules` 更名为 `Lane`，旧主配置文件名不再发布；请改用上面的新地址。已下载的本地副本不会随仓库重命名自动迁移，应升级一次以使用新规则 URL。历史文件可从 Git 提交记录取回。

Python 内部包名 `proxyrules` 和旧命令保留兼容，公开项目与新命令统一为 Lane。Fork 后请修改 `config/project.yaml` 中的仓库与 `raw_base`，重新生成，再启用 GitHub Actions；不要把私人订阅写入生成源。

## 规则来源与许可

- [v2fly/domain-list-community](https://github.com/v2fly/domain-list-community)（MIT）
- [Telegram 官方 CIDR](https://core.telegram.org/resources/cidr.txt)
- [Koolson/Qure](https://github.com/Koolson/Qure)（仅引用图标 URL）

本项目自身以 MIT License 发布。第三方来源与借鉴边界见 [`NOTICE.md`](NOTICE.md)。
