# Lane

一份规则清单，生成 Stash、Loon、Shadowrocket、Surge、Quantumult X 与 Egern 六种客户端配置。只有一个版本，不区分通用版与个人版；策略组、地区筛选和上游数据由同一套声明式配置管理。

**主配置本地保存，节点订阅与远程规则独立更新。** 不需要额外安装覆写、脚本或订阅转换服务。

## 当前设计

- 所有策略组名称均使用简洁英文。
- `AI`、`Google`、`Developer`、`Telegram`、`Social`、券商、交易所、视频、游戏平台等服务组均默认选择 `Manual`。
- 六端的 `Manual` 都先列出五个地区自动组，再保留用户导入的全部单节点；不排除流量、到期、高倍率或维护信息项。Surge 的五项名称为 `地区 Auto Smart`，其余五端为 `地区 Auto`。
- 地区仅保留美国、日本、香港、台湾与新加坡；每个地区分别提供 `XX Auto` 自动优选和 `XX Manual` 手动选点。
- 策略组按 `Manual`、服务组、地区组排列，十个地区 Auto / Manual 组统一放在列表末尾。
- 地区筛选只做正向匹配，不使用排除词：国旗、完整中文地区名（含繁体）、英文全称、带词边界的地区代码。城市名和单字简称均不参与匹配；新加坡额外接受 `狮` / `獅`。
- 服务组可切换到 `DIRECT`，或五个地区各自的 Auto / Manual 策略。
- `Brokerage` 合并 Futu、Moomoo、Tiger 与 Longbridge；`Schwab` 单独成组。Futu 使用 v2fly 上游、实测补充域名和既有 63 个 CIDR；Tiger 只保留 `skytigris.cn`，Longbridge 只保留 `geotest.lbkrs.com`。生成时把域名与 IP 拆成两个规则集，但仍使用同一策略组；Futu IP 按真机交易结果置于 `China` 之前。
- `Crypto` 只匹配 Binance、OKX、Bybit 与 Bitget。其他交易所不单独分类，按后续规则或 `Final` 处理。
- 中国大陆 AI 不设专门规则，自然落入 `cn` / `GEOIP,CN` 直连。
- 不设置游戏大文件下载特例，也不内置广告拦截或业务 `REJECT` 规则。Surge、Shadowrocket、Loon、QX 仅在已选节点不支持 UDP 时显式拒绝回落，避免静默直连泄漏；不全局封锁 UDP / QUIC。
- 未命中流量进入 `Final`，而 `Final` 默认跟随 `Manual`。

完整策略声明见 [`config/policies.yaml`](config/policies.yaml)，规则顺序见 [`config/rulesets.yaml`](config/rulesets.yaml)。

### Brokerage、Crypto 与 Schwab

这三个组都默认选择 `Manual`，也可独立切换为 `DIRECT` 或某个地区的 Auto / Manual。下面的直连建议不会改变配置的默认值；六端配置顶部也保留了简短说明。

| 策略组 | 覆盖范围 | 用途与选择建议 |
| --- | --- | --- |
| `Brokerage` | 富途 / Moomoo 完整覆盖；老虎 `skytigris.cn`；长桥 `geotest.lbkrs.com` | 富途保留域名与 IP 分流；老虎、长桥只代理已经实测需要的关键域名，避免把官网等无关连接一并装入证券策略组。 |
| `Crypto` | 币安 Binance、OKX、Bybit、Bitget，仅这四家 | 当前网络可以正常访问时，建议手动选择 `DIRECT`；无法正常访问时可按实际情况选择代理。其他交易所按后续规则或 `Final` 处理。 |
| `Schwab` | 嘉信 Charles Schwab | 与 `Brokerage` 分开控制网络路径；当前网络可以正常访问时，可手动选择 `DIRECT`，也保留代理选项。 |

`Brokerage` 只从 v2fly 引入 `futu`，并保留实际使用中补充的 Futu 域名与 IP 段；老虎与长桥不再引入 v2fly 的整组品牌域名，只保留 `skytigris.cn` 和精确域名 `geotest.lbkrs.com`。被移出的 `itiger` / `longbridge` 普通品牌域名仍会因 v2fly `geolocation-!cn → category-finance` 命中后面的 `General Proxy`，最终跟随 `Final`，只是不能再单独切换到 `Brokerage`。产物中的 `brokerage` 只含域名，`brokerage-ip` 只含 IP，两者仍指向同一个 `Brokerage` 策略。`brokerage-ip` 带 `no-resolve` 并位于 `China` 之前：直接访问或解析到重叠中国网段时先走 Brokerage，同时不会为了普通域名强制解析。这些规则不是对整个应用的识别；入金流程涉及的外部银行、支付页面仍按各自命中的规则处理。

其他香港券商与社区上游的逐项结论见 [`docs/BROKERAGE-UPSTREAM-AUDIT-2026-08-31.md`](docs/BROKERAGE-UPSTREAM-AUDIT-2026-08-31.md)。目前没有把华盛、uSMART、Webull 或 IBKR 直接加入生产规则：公开域名清单可以提供候选，但不能替代“直连失败、代理恢复”的交易动作实测。

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
| Egern | `policy_groups → Node Pool → urls` 的第一个占位符，使用 Egern 支持的节点订阅；该隐藏组与 `Manual` 共享同一列表 |
| Shadowrocket | 无模板，直接使用应用内已有节点订阅 |

订阅格式必须兼容目标客户端：不能保证同一条链接在六个软件里通用。本项目不代用户转换或收集私人订阅；不要把填好的配置上传到公开仓库。

Loon 用户若选择重新导入远程配置，请选择保留现有节点/订阅，不要全部覆盖。其他客户端也应先备份；换用新版完整主配置时，重新填入订阅地址并迁移个人修改。

### 多份订阅

每个带订阅模板的客户端都提供一份启用模板和一份注释模板，填写位置旁也有简短操作提示。需要第二份时，取消对应模板行首的 `#` 和紧跟的一个空格、填入第二份链接；YAML 要保留原有缩进。不要直接取消全部注释，也不要把多个链接拼进同一个 URL 字段。

| 客户端 | 第二份订阅 | 第三份及更多订阅 |
| --- | --- | --- |
| Stash | 取消 `Subscription2` 整块注释并填写 `url`，包括该块的更新与测速参数 | 复制整块，名称依次改为 `Subscription3` 等；现有 `include-all` 会纳入全部代理集，无需逐个改策略组 |
| Loon | 取消 `Subscription2 =` 行的注释并填写 | 复制该行，使用不同别名；现有节点筛选会处理所有订阅 |
| Surge | 取消隐藏组 `Subscription2` 的注释并填写，再把隐藏 `Node Pool` 的参数改为 `include-other-group="Subscription1,Subscription2"` | 新增 `Subscription3` 等隐藏组，并逐一加入 `Node Pool` 的引用列表 |
| Quantumult X | 取消 `tag=Subscription2` 那一行的注释并填写 | 复制该行，使用不同的 `tag`；现有策略组会按节点名称筛选 |
| Egern | 取消隐藏 `Node Pool` 的 `urls` 下第二个列表项的注释并填写 | 在同一 `urls` 列表下逐行追加地址；YAML 锚点会让 `Manual` 同步使用该列表，无需重复填写 |
| Shadowrocket | 在应用内添加 | 在应用内继续添加，Lane 不放订阅模板 |

Surge 的订阅先进入隐藏 `Node Pool`，五个 `US/JP/HK/TW/SG Auto Smart` 与地区 Manual 组都从中展开真实节点。顶层 `Manual` 同时列出五个 Smart 组和全部单节点，因此服务组直接选择某个 Smart，与服务组选择 Manual、再由 Manual 选择同一个 Smart，最终使用的是同一策略对象。该结构也避免了 Manual 与地区组互相引用的循环。[Surge Smart](https://manual.nssurge.com/policy-groups/smart.html)、[Surge 节点引用](https://manual.nssurge.com/policy-groups/policy-including.html)。

Stash、Loon、Shadowrocket、Quantumult X 与 Egern 的 `Manual` 同样列出五个原生 `地区 Auto`，同时保留全部单节点。Egern 额外使用隐藏 `Node Pool` 作为地区组的节点来源，并以 YAML 锚点让 `Manual` 共享同一份订阅地址；这样地区组不反向引用 `Manual`，不会形成循环，用户也只需填写一次订阅。

订阅别名不同不代表节点名称不会重复。多个订阅尽量避免同名节点：Surge 和 Egern 都有按名称去重的行为；Surge 如需区分，可在各订阅组分别添加 `external-policy-name-prefix=S1-`、`external-policy-name-prefix=S2-`。这不是默认配置，不影响地区正向匹配。[Surge 节点命名](https://manual.nssurge.com/policy-groups/policy-including.html)、[Egern 多订阅](https://egernapp.com/docs/configuration/policy_groups/)。

### 哪些内容会更新？

| 内容 | 更新来源 | 是否更换本地主配置 |
| --- | --- | --- |
| 节点列表 | 服务提供商订阅 | 不需要 |
| 已引用规则集中的域名、IP | Lane 的远程规则文件 | 不需要 |
| 策略组、DNS、规则引用及顺序、兼容性修复 | 新版 Lane 主配置 | 需要按升级说明迁移 |

### 单一、可独立复用的规则产物

每个客户端只发布一组 `rules/` 文件，Lane 主配置也直接引用这一组。编译只按“规则类型 + 规范值”删除精确重复，不做父级后缀折叠，也不按当前配置顺序删除已被前面规则覆盖的条目；当前规则总数和精确去重数由每次构建写入 `dist/metadata.json`。因此任意单个规则文件都不依赖 Lane 的整体顺序，可以独立审计和复用。

`dist/metadata.json` 仍会以只读方式报告同组父后缀、跨组精确重复和跨组父后缀等潜在冗余关系，但这些条目全部保留，不参与优化；统计值随上游变化自动更新，不作为固定测试常量。这样避免把六个客户端没有一致明文保证的根域、单标签后缀和跨组优先级假设固化成数据删除。

Stash 在同一个 `rules/` 目录中保留每个逻辑规则集的原始带类型规范文件，同时生成 `-domain`、`-ipcidr`、`-classical` 专用载荷；主配置只引用专用载荷，规范文件用于审计、回退和语义校验。其他五端各发布一个对应客户端语法的逻辑规则文件。客户端不支持的转换仍逐项记录在 `dist/report.json`；当前 Loon、Shadowrocket、Surge 与 QX 各省略 174 条 `DOMAIN-REGEX`，详细转换审计另行处理，不在本次产物收敛中猜测改写。

旧的 `rules-full/`、`rules-profile/` 已统一回 `rules/`，GoogleCN 也不再抓取或发布。已经保存旧版 Lane 配置的用户必须升级一次完整主配置，重新填入节点订阅并迁移个人修改；之后规则资源仍可独立自动更新。

全部策略图标都保存在本仓库的 [`assets/icons/`](assets/icons/) 并通过 Lane 自己的 Raw URL 发布，不再在运行时依赖外部图标仓库。Apple 使用 `Apple_1`，Streaming 使用 Netflix，Final 使用 Global；AI、Brokerage、Schwab 与 Crypto 使用 Lane 自绘图标。五个地区 Auto 在地区图标右下角增加蓝色循环箭头角标，Manual 保留普通地区图标。Stash/Egern 使用 `icon`，Loon/QX 使用 `img-url`；Shadowrocket 不强制自定义图标，Surge 的官方 `icon-url` 当前标注为 Mac 功能，本配置以 iOS 兼容为先，不设置它。

### 客户端兼容性

- Stash 将精确域名与后缀放入 `behavior: domain`（后缀使用同时覆盖根域和子域的 `+.` 形式），CIDR 放入 `behavior: ipcidr`，正则/关键词保留在 `behavior: classical`；三类仍是远程更新的文本 provider。Egern 继续用原生 YAML 保留域名正则。
- Loon、Shadowrocket、Surge、QX 中不支持或未确认兼容的域名正则会省略，逐规则集计数见 `dist/report.json`，不会误转换为 URL 重写。Loon 使用现行 `ip-mode = ipv4-only`，最低支持版本为 3.2.3 (754)。
- Surge、Shadowrocket、Loon、QX 在节点不支持 UDP 时分别使用客户端原生的拒绝回落项；Stash/Egern 保持默认行为。配置不包含 `block-quic`、`udp_drop_list = QUIC` 或 `disable-udp-ports = 443`。
- Egern 使用原生 YAML 规则集，保留 `no_resolve`；隐藏 `Node Pool` 加载订阅，地区组通过 `flatten` 展开其中节点，`Manual` 共享订阅并列出地区 Auto；请使用支持 `urls` / `flatten` 的当前版本。
- QX 使用原生 `host` / `host-suffix` / `ip-cidr` / `ip6-cidr`，不写入 Surge 风格的 `no-resolve`。QX 自身的域名/IP 匹配优先级与其他内核不同，不能保证所有重叠规则逐条等价。没有额外加入抢先匹配的默认 CN/LAN 资源。
- Stash、Loon、Shadowrocket、QX 与 Egern 的 Auto 使用各自原生自动测速类型；Surge 使用原生 Smart 算法并命名为 `地区 Auto Smart`。六端 Manual 组保持手动选择，并可直接选择对应地区自动组。
- 六端均通过静态结构与生成测试；测试不等于在六款付费客户端上完成真机导入、联网验证。订阅协议和空地区组行为仍需在实际客户端确认。

格式依据：[Stash 规则集](https://stash.wiki/en/rules/rule-set)、[Stash 代理集](https://stash.wiki/proxy-protocols/proxy-providers)、[Loon General](https://nsloon.app/en/docs/General/)、[Loon 官方示例](https://github.com/Loon0x00/LoonExampleConfig/blob/master/example.conf)、[Surge 节点引用](https://manual.nssurge.com/policy-groups/policy-including.html)、[QX 官方示例](https://github.com/crossutility/Quantumult-X/blob/master/sample.conf)、[Egern 策略组](https://egernapp.com/docs/configuration/policy_groups/)、[Egern 规则](https://egernapp.com/docs/configuration/rules/)。

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
dist/*/rules/           唯一的完整、可独立复用规则；主配置直接引用
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

CN-IP 3-of-5 共识窗相对上一个已发布版本的地址空间变化超过 1% 时，构建会在写入
`dist` 前停止并生成 AI 诊断文件。人工核对后，只能运行
`lane build --refresh --accept-cn-ip-sha256 <候选 SHA256>` 接受该确切候选；定时任务
不会自动绕过熔断，也不存在可长期放行后续候选的通用开关。

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

1. 拉取 v2fly、Telegram 官方 CIDR、gaoyifan `ip-lists` git 历史、misakaio 独立 IPv4 对照数据，以及 felixonmars 的 AppleCN 名单。
2. 从 gaoyifan 最近七个不同 UTC 日期的提交中读取 `china.txt` / `china6.txt`，按地址空间统计，只保留至少五份快照都出现的范围。
3. 对窗口结果执行 1% 地址空间变化熔断，并与 misakaio 做独立 IPv4 交叉验证；所有快照和地址族验证通过后才原子替换缓存。
4. 编译六端规则、运行测试和结构校验；仅在 `dist/` 真实变化时创建自动更新提交。

`dist/metadata.json` 记录上游 commit、文本源 SHA-256 与规则集数量；`dist/report.json` 记录客户端转换差异。每日构建也检查主配置，但只有主配置实际内容变化才更新它及其北京时间；规则集更新不强制用户升级本地主配置。主配置里的时间不是设备上规则资源最近一次下载时间。

### 国内服务例外与 CN IP 兜底

| 规则集 | 来源 | 默认策略与位置 |
| --- | --- | --- |
| `apple-cn`（AppleCN） | felixonmars `apple.china.conf` + v2fly `apple@cn` | `DIRECT`，本地自定义规则之后、服务规则之前，优先于 Apple 主规则 |
| `cn-ip`（CN IP） | gaoyifan `ip-lists` 的 3-of-5 共识窗 | `DIRECT`，包含 IPv4 + IPv6，位于 Brokerage IP、China、Proxy 与 Telegram IP 之后、原有 GEOIP 与最终兜底之前 |

两者均为独立远程规则集，不并入 `china`，也不新增策略组。AppleCN 从 felixonmars 提取域名后缀，不复制 dnsmasq 的 DNS 服务器或其他指令；同时只合并 v2fly `apple` include 链中明确带 `@cn` 的条目，不把普通 Apple 域名扩大为直连。它不是整个 Apple 直连开关；未命中例外名单的连接仍由 Apple 策略组处理。上游说明 Apple 国内 CDN 在部分运营商网络下可能不可用，出现问题时可停止引用该规则集。

**GoogleCN 已完全移除。** felixonmars/dnsmasq-china-list 是 DNS 加速项目，`google.china.conf` 的语义是“用国内 DNS 解析这些域名会得到 Google 的中国前端地址”；解析得到不等于直连可达。Lane 不再抓取、转换或发布这份名单，Google 域名统一走 Google 策略组。Apple 的情况不同——其条目解析到可直连的大陆 CDN 节点，因此 AppleCN 仍保留在默认分流。

### 局域网

`lan` 规则集位于所有规则之前，除 v2fly `private` 的本地域名外，还包含 RFC 1918 / 5735 / 5737 / 6598 / 4193 / 4291 的私有与特殊用途网段（见 [`rules/custom/lan.list`](rules/custom/lan.list)）。这些前缀不随上游变化，因此直接固定在仓库内。

该规则集设置 `no_resolve`，只作用于 IP 规则：`lan` 是配置中的第一条规则，不带 `no-resolve` 的话，任何域名请求在第一步就会被迫做一次本地解析。`198.18.0.0/15` 被有意排除——六个客户端都用它作为 fake-IP 段。Quantumult X 的原生 IP 匹配语义不接受 Surge 式修饰符，因此其产物不含 `no-resolve`，这与既有的 Brokerage / Telegram IP 处理一致。

CN IP 的唯一发布主源是 **gaoyifan/china-operator-ip**，但不直接采用最新一天。构建从 git 历史选择最近五个不同 UTC 日期的快照，在合并过等价 CIDR 覆盖后，只发布至少三份快照均出现的地址空间。这样单日的异常增减不会立刻进入规则。保留已有 `GEOIP,CN,DIRECT` 作为第二层故障保险；`Final` 及其他服务组的默认选择不变。`cn-ip` 仍然不加 `no-resolve`。

[`dist/cn-ip-window.json`](dist/cn-ip-window.json) 记录五个日期、commit、双栈文件摘要、每天与最终窗口的规则数/地址覆盖，以及相对上次发布的变化。熔断按每个地址族的**对称地址空间差**计算，而不是按 CIDR 行数：等价的拆分/聚合不会误报，等量替换仍能被发现。变化超过 1% 时定时构建停止，旧 `dist` 和 last-known-good 缓存保持不变；诊断工件会记录候选摘要，接受操作必须绑定其准确 SHA256。

[`dist/cn-ip-validation.json`](dist/cn-ip-validation.json) 使用 **misakaio/chnroutes2** 做独立 BGP IPv4 交叉验证，记录两侧地址覆盖，以及独有范围的总数、完整摘要和前 100 条样本，但绝不把参考源并入路由。misakaio 没有 IPv6 文本清单，因此报告会明确写 `IPv6 reference_available: false`；IPv6 仍经过 3-of-5 窗口与格式验证，不冒充独立双栈验证。空名单、缺失主源地址族、默认路由、无效快照或缓存摘要不一致都会中止构建。

候选 git 仓库先克隆到 staging，五份快照、双栈、窗口与熔断全部通过后，才用单一缓存工件做原子替换。网络失败且有有效缓存时会明确回退；首次拉取失败则中止。Loyalsoldier 三个仓库只保留作人工差分审计，不再作为 Lane 主上游。

单一 `rules/` 产物恢复后，旧 `rules-full/` / `rules-profile/` URL 停止发布。已有用户需要手动升级一次完整配置；升级时请保留或重新填入自己的节点订阅及个人修改。之后这些远程规则可继续独立更新。

项目已从 `ProxyRules` 更名为 `Lane`，旧主配置文件名不再发布；请改用上面的新地址。已下载的本地副本不会随仓库重命名自动迁移，应升级一次以使用新规则 URL。历史文件可从 Git 提交记录取回。

Python 内部包名 `proxyrules` 和旧命令保留兼容，公开项目与新命令统一为 Lane。Fork 后请修改 `config/project.yaml` 中的仓库与 `raw_base`，重新生成，再启用 GitHub Actions；不要把私人订阅写入生成源。

## 规则来源与许可

- [v2fly/domain-list-community](https://github.com/v2fly/domain-list-community)（MIT）
- [Telegram 官方 CIDR](https://core.telegram.org/resources/cidr.txt)
- [gaoyifan/china-operator-ip](https://github.com/gaoyifan/china-operator-ip)（MIT；CN IP 双栈 3-of-5 共识窗主源）
- [misakaio/chnroutes2](https://github.com/misakaio/chnroutes2)（CC BY-SA 4.0；独立 IPv4 交叉验证，不并入路由）
- [Loyalsoldier/geoip](https://github.com/Loyalsoldier/geoip)（仅用于人工差分审计，不参与构建）
- [felixonmars/dnsmasq-china-list](https://github.com/felixonmars/dnsmasq-china-list)（WTFPL 2.0；仅使用 AppleCN）
- [Koolson/Qure](https://github.com/Koolson/Qure)（仓库内保留经注明来源的图标子集；不属于 Lane MIT 授权，详见 [`assets/icons/README.md`](assets/icons/README.md)）

本项目自身代码以 MIT License 发布，第三方规则数据遵循各自许可。第三方来源、转换说明与借鉴边界见 [`NOTICE.md`](NOTICE.md) 和 [`licenses/`](licenses/)。
