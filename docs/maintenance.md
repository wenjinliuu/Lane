# Lane 维护指南

本文面向项目维护者和代码代理。用户入口、下载地址和基础用法只放在根目录 README；
历史排查过程与实现细节不得重新堆回项目首页。

## 权威来源

声明式配置是策略语义的权威来源：

- `config/project.yaml`：仓库地址、测试地址和更新间隔
- `config/policies.yaml`：服务组、地区组和筛选表达式
- `config/rulesets.yaml`：规则来源、策略和首匹配顺序
- `config/sources.yaml`：上游数据、许可和校验角色
- `config/icons.yaml`：自托管图标映射
- `rules/custom/`：Lane 自行维护的最小补充规则

`src/proxyrules/` 负责解析、编译、转换和校验；`dist/` 是生成产物，不是独立编辑源。
修改策略时必须同步生成器、验证器、测试、文档和全部受影响产物。

## 构建流程

1. 从 `v2fly/domain-list-community` 解析域名分类及其 `include`、属性和归属关系。
2. 合并声明的自定义规则和文本 / CIDR 数据源。
3. 按“规则类型 + 规范值”删除同一逻辑规则集内的精确重复。
4. 保留父后缀覆盖和跨规则集覆盖候选，只在 `dist/metadata.json` 中报告。
5. 将同一逻辑规则转换为六个客户端的原生格式，并写入 `dist/<client>/rules/`。
6. 生成六端主配置、元数据、转换报告和 CN-IP 校验报告。

Google、Microsoft 等归属主要由 v2fly 上游分类决定。Lane 在 `config/rulesets.yaml` 中选择
和组合分类、应用 `@cn` 等属性、增加最小补充项，再确定策略与优先顺序；不要凭品牌名称
手工扩大生产规则。

## 规则来源

- 域名主源：`v2fly/domain-list-community`
- Telegram IP：Telegram 官方 CIDR
- 中国 IPv4/IPv6：`gaoyifan/china-operator-ip` 的 3-of-5 稳定窗口
- 中国 IPv4 独立对照：`misakaio/chnroutes2`，只验证，不并入规则
- AppleCN：`felixonmars/dnsmasq-china-list` 的 Apple 数据与 v2fly `apple@cn`
- 图标：仓库内自托管的 Qure 固定提交原文件

GoogleCN 不得恢复。DNS 加速名单不等于网络直连可达；Google 流量统一交给 Google 策略组。
AppleCN 保留，因为其大陆 CDN 例外具有独立路由意义。

## 不可破坏的规则顺序

整体采用首匹配：

1. LAN 与用户自定义规则
2. AppleCN 与各业务服务规则
3. Brokerage IP
4. China 域名
5. 完整的 `geolocation-!cn` / General Proxy
6. Telegram IP
7. CN IP
8. 客户端 `GEOIP,CN`
9. Final

关键原因：

- Brokerage IP 必须位于 China / CN IP 之前；真机交易测试已证明顺序反转会使富途交易失败。
- China 必须位于 General Proxy 之前，让已知中国域名优先直连。
- General Proxy 必须位于 CN IP 之前，保护已知境外域名不被临时解析到的中国 IP 误判。
- CN IP 不得加 `no-resolve`；否则域名请求会跳过 Lane 的 CN-IP 快照。
- `GEOIP,CN` 保留为客户端数据库的最后一层故障保险。

## 业务范围

- Brokerage：Futu / Moomoo 使用上游、补充域名和 63 个 CIDR；Tiger 仅保留
  `skytigris.cn`；Longbridge 仅保留 `geotest.lbkrs.com`；Schwab 保留独立规则文件但
  路由到 Brokerage。
- Crypto：仅 Binance、OKX、Bybit、Bitget。
- Streaming：Netflix、Disney、HBO、Prime Video、Hulu、Spotify、Twitch、Apple TV+
  和 Apple Music。
- 不内置广告拦截、业务 Reject、脚本、重写或 MitM。

新增券商品牌或扩大域名范围必须先取得目标操作“直连失败、指定代理恢复”的可复现实测，
并优先使用精确域名。上游列表只能作为候选库存，不能自动证明某域名必须代理。

## 客户端约束

### Stash

- `我的节点` 使用 `include-all` 汇总全部 provider。
- `Proxy` 先列 `我的节点`，再列五个地区 Auto。
- 域名、CIDR 和其他规则分别使用 `domain`、`ipcidr`、`classical` provider；规范规则文件
  仍保留用于审计。

### Loon

- `我的节点` 是无图标的 Remote Filter，`Proxy` 组合地区 Auto 与全部真实节点。
- 使用 `ip-mode = ipv4-only`，不要恢复旧的 `ipv6 = false`。

### Surge

- 订阅先进入隐藏的 `SubscriptionN`，可见的 `我的节点` 再展开真实节点。
- `Proxy` 先列 `我的节点`，再列五个 `XX Auto Smart`。
- `policy-regex-filter` 不加引号；`tun-excluded-routes` 只写 IPv4。
- HTTP 捕获属于 App 状态；Lane 不通过配置控制或启用 MitM。

### Quantumult X

- QX 的 `proxy` 是内置保留策略名，共享 `Proxy` 组必须显示为 `代理选择`。
- 不生成重复的 `我的节点`；`代理选择` 直接使用 `server-tag-regex=.+` 纳入全部节点，并
  保留五个地区 Auto。
- `[server_remote]` 保持为空，用户在 App 的节点资源页面添加订阅。
- 保留官方顺序的完整模块骨架；未使用的重写、脚本、后端和 MitM 模块必须为空。
- 使用原生 host / IP 语法，不写 Surge 风格的 `no-resolve`。

### Egern

- 订阅只在 `我的节点.urls` 加载一次；地区组从该组 `flatten` 后筛选。
- `Proxy` 先列 `我的节点`，再列五个地区 Auto，避免重复加载与策略环。

### Shadowrocket

- 不生成 `我的节点` 或 `Proxy` 基础组；服务组使用 App 内置 `PROXY`。
- 不写策略组图标参数。

## 节点与图标

地区只保留 US、JP、HK、TW、SG。筛选采用国旗、完整中文名、英文全称和带边界的地区代码；
新加坡额外接受 `狮` / `獅`。不要随意加入容易误匹配的单字。

策略图标必须先复制到 `assets/icons/third-party/qure/`，再由 `config/icons.yaml` 指向 Lane
自己的 Raw URL。不要让运行时直接依赖第三方图标 URL，也不要重新引入自绘或二次加工图标。
`我的节点` 当前使用 `Rocket.png`；QX 和 Loon 不显示该图标，Shadowrocket 不输出图标。

## CN-IP 安全更新

构建读取 gaoyifan 最近五个不同 UTC 日期的 IPv4/IPv6 快照，只保留至少三份均出现的地址
空间。相对上一个已发布版本的对称地址空间变化超过 1% 时必须停止，不能让定时任务自动
绕过。人工接受只能绑定诊断产物给出的准确候选 SHA-256。

## 验证命令

需要 Python 3.11+ 与 Git：

```bash
python -m pip install -e '.[dev]'
lane build --refresh
python -m pytest
lane check
```

离线缓存完整时可使用 `lane build --offline`。CN-IP 熔断后的人工接受命令为：

```bash
lane build --refresh --accept-cn-ip-sha256 <候选 SHA256>
```

提交前必须确保生成物与源一致、`lane check` 通过、全部测试通过，并检查 `git diff --check`。

## 历史记录

`docs/DECISIONS-*.md`、`docs/BROKERAGE-UPSTREAM-AUDIT-2026-08-31.md` 和
`docs/SURGE-MITM-HANDOFF-2026-09-01.md` 保存当时的证据与排查过程。它们是历史记录，
可能早于当前实现；发生冲突时以当前 `config/`、生成器、测试和本文为准。
