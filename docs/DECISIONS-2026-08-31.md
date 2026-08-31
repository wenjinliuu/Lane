# Lane 六端 Manual 与证券最小规则决策记录

- 日期：2026-08-31
- 状态：已确认，随生成器、校验器、回归用例与六端产物同步实施
- 实施基线：`main` @ `f85cd60`
- 实施分支：`codex/manual-auto-brokerage-minimal`

本文记录本轮已经确认的产品语义。生成器、静态校验、路由回归和发布产物必须同时满足这些约束，避免以后自动更新时退回旧行为。

## D1. 六端 Manual 都提供五个地区自动组

### 决策

Stash、Loon、Shadowrocket、Surge、Quantumult X 与 Egern 的顶层 `Manual` 都必须同时提供：

1. 美国、日本、香港、台湾、新加坡五个地区自动组；
2. 用户订阅中的全部单节点。

Surge 使用原生 Smart 组，名称固定为：

- `US Auto Smart`
- `JP Auto Smart`
- `HK Auto Smart`
- `TW Auto Smart`
- `SG Auto Smart`

其余五端使用对应的 `US/JP/HK/TW/SG Auto`。服务策略直接选择地区自动组，或先选择 `Manual`、再在其中选择同一个地区自动组，必须指向同一个既有策略对象，不复制另一套测速策略。

### Egern 的无循环结构

Egern 新增隐藏 `Node Pool`：

- `Node Pool` 加载节点订阅；
- 十个地区 Auto / Manual 组从 `Node Pool` 执行 `flatten` 与地区筛选，不再反向引用 `Manual`；
- `Manual` 列出五个地区 Auto，并继续加载全部单节点；
- `Node Pool.urls` 与 `Manual.urls` 使用 YAML 锚点共享同一列表，用户只填写一次订阅地址。

这样既保留 Manual 的地区自动选择和原始单节点，也避免 `Manual → 地区 Auto → Manual` 的策略环。

## D2. 老虎与长桥只保留实测关键域名

### 决策

`Brokerage` 的来源收敛为：

| 券商 | Brokerage 中保留的范围 |
| --- | --- |
| Futu / Moomoo | v2fly `futu`、项目补充域名、既有 63 个 Futu CIDR |
| Tiger | `DOMAIN-SUFFIX,skytigris.cn` |
| Longbridge | `DOMAIN,geotest.lbkrs.com` |

不再把 v2fly `itiger` 与 `longbridge` 整组引入 `Brokerage`。因此老虎移除 8 个宽泛后缀，长桥移除 12 个宽泛后缀；Futu 域名和 63 个 CIDR 不随本项缩减。

这项调整只缩小“可单独切换证券出口”的范围。v2fly `geolocation-!cn` 包含 `category-finance`，而该分类仍包含 `itiger` 与 `longbridge`，所以 `www.itiger.com`、`www.longbridge.com` 等普通品牌域名仍在后面的 `General Proxy` 命中并跟随 `Final`，不会因为退出 `Brokerage` 而自动变为 DIRECT。

`geotest.lbkrs.com` 必须保持精确域名，不能扩成整个 `lbkrs.com`；`skytigris.cn` 保持后缀规则，以覆盖其实际使用的 API 子域名。

## D3. 回归验收

每次生成与上游更新都必须验证：

1. 六端 `Manual` 的前五个可选项是对应的地区自动组，随后仍能选择订阅单节点；
2. Surge 地区自动组仍是 Smart，Egern `Node Pool` 仍隐藏且地区组只从该池展开；
3. `api.skytigris.cn` 首先命中 `Brokerage`；
4. `geotest.lbkrs.com` 首先命中 `Brokerage`；
5. `www.itiger.com` 与 `www.longbridge.com` 不再命中 `Brokerage`，而是命中 `General Proxy` / `Final`；
6. 旧的 Tiger 与 Longbridge 宽泛后缀不得重新出现在生成的 `brokerage` 规则集中；
7. Futu 的 63 个 CIDR、`no_resolve` 及其位于 `China` 之前的优先级保持不变。

## 后续边界

是否把华盛、uSMART、Webull、IBKR 或其他香港券商加入 `Brokerage`，需要单独审计已有维护项目、规则来源和“必须代理”的实测证据。本次不因品牌规模或官网域名存在就直接扩张生产规则。
