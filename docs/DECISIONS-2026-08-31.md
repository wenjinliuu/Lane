# Lane 六端代理入口与证券最小规则决策记录

- 日期：2026-08-31
- 最近修订：2026-09-02（五端统一 `我的节点 → Proxy` 两层入口、QX 空订阅模块）
- 状态：已确认，随生成器、校验器、回归用例与六端产物同步实施
- 实施基线：`main` @ `f85cd60`
- 实施分支：`codex/manual-auto-brokerage-minimal`

本文记录本轮已经确认的产品语义。生成器、静态校验、路由回归和发布产物必须同时满足这些约束，避免以后自动更新时退回旧行为。

## D1. 五端使用两层代理入口，Shadowrocket 使用内置入口

### 决策

除 Shadowrocket 外，五端统一提供：

1. 排在最上方的 `我的节点`，汇总用户全部订阅中的真实节点；
2. 排在其后的 `Proxy`，包含美国、日本、香港、台湾、新加坡五个地区自动组和 `我的节点`。

Surge 使用原生 Smart 组，名称固定为：

- `US Auto Smart`
- `JP Auto Smart`
- `HK Auto Smart`
- `TW Auto Smart`
- `SG Auto Smart`

其余客户端使用对应的 `US/JP/HK/TW/SG Auto`。Stash 真机实测中，`proxies + include-all` 在同一组里只稳定显示一侧，因此动态节点放入独立的 `我的节点`，`Proxy.proxies` 只显式列出五个地区 Auto 与 `我的节点`。新增或重命名 `proxy-providers` 时，`我的节点.include-all` 自动纳入，不再维护 provider 名称。Egern 2.20.0 同样采用两层结构。Shadowrocket 不生成这两个基础组，由内置 `PROXY` 表示首页选择的单节点。服务策略直接选择地区自动组，或经各客户端的代理入口选择，必须指向同一个既有策略对象，不复制另一套测速策略。

Stash 覆写可以递归合并 `proxy-providers` 字典；新增代理集会被 `我的节点` 与地区 Auto / Manual 组的 `include-all` 自动纳入，不需要同步修改基础组。

### Egern 的单订阅源无循环结构

Egern 使用可见的 `我的节点`：

- `我的节点.urls` 只加载一次节点订阅；
- 十个地区 Auto / Manual 组从 `我的节点` 执行 `flatten` 与地区筛选，不反向引用 `Proxy`；
- `Proxy` 列出五个地区 Auto 与 `我的节点`；
- 用户只需填写一处订阅地址，多订阅也只在同一 `urls` 列表中追加。

这样既避免 `Proxy → 地区 Auto → Proxy` 的策略环，也规避同一订阅重复加载后节点被去重。

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

1. 除 Shadowrocket 外，五端的 `我的节点` 可选择全部订阅单节点，`Proxy` 可选择地区自动组与 `我的节点`；Shadowrocket 通过内置 `PROXY` 选点；
2. Surge 地区自动组仍是 Smart；Egern 只在 `我的节点` 加载一次订阅，地区组只从该组展开；
3. `api.skytigris.cn` 首先命中 `Brokerage`；
4. `geotest.lbkrs.com` 首先命中 `Brokerage`；
5. `www.itiger.com` 与 `www.longbridge.com` 不再命中 `Brokerage`，而是命中 `General Proxy` / `Final`；
6. 旧的 Tiger 与 Longbridge 宽泛后缀不得重新出现在生成的 `brokerage` 规则集中；
7. Futu 的 63 个 CIDR、`no_resolve` 及其位于 `China` 之前的优先级保持不变。

## 后续边界

是否把华盛、uSMART、Webull、IBKR 或其他香港券商加入 `Brokerage`，需要单独审计已有维护项目、规则来源和“必须代理”的实测证据。本次不因品牌规模或官网域名存在就直接扩张生产规则。

## D4. 策略组图标自托管

- 策略组图标统一存放在仓库的 `assets/icons/`，生成配置仅引用 Lane 自己的 GitHub Raw 地址，避免运行时依赖第三方图标仓库。
- 不再维护 Lane 自绘或二次加工图标。全部运行时 PNG 均从 Qure 指定提交原样复制到 `assets/icons/third-party/qure/`，保留来源、版本与授权提示，不纳入 Lane 的 MIT 授权声明。
- 恢复自绘改动前的映射：AI 使用 `AI`、证券使用 `Magic`、Crypto 使用 `Cryptocurrency_3`；同一地区的 Auto 与 Manual 共用普通地区图标，不添加 Auto 角标。台湾继续使用已经确定的 `China`。
- 仅保留三项替换：Apple、影视和 Final 分别使用 `Apple_1`、`Netflix` 和 `Global`。
- Stash、Loon、Quantumult X、Egern 与 Surge 输出策略组图标；Shadowrocket 维持无自定义图标输出，以符合当前客户端能力。

## D5. 嘉信规则并入 Brokerage

- 删除六端可见的 `Schwab` 策略组，不再单独占用策略选择项。
- `schwab` 逻辑规则集、v2fly `schwab` 来源与 `rules/custom/schwab.list` 全部保留，生成的独立规则文件也继续发布。
- 嘉信规则命中后统一交给 `Brokerage`，与其他证券规则共用同一策略选择；不把嘉信域名删除或改为硬编码 DIRECT。

## D6. QX 完整配置保留官方模块骨架

- QX 真机从远程 URL 导入完整配置时会逐项检查模块；已先后报缺少 `[server_remote]`、`[server_local]` 与 `[rewrite_remote]`。因此生成物按官方示例顺序保留全部 12 个模块，而不是继续逐个补洞。
- `[rewrite_remote]`、`[server_local]`、`[rewrite_local]`、`[task_local]`、`[http_backend]` 与 `[mitm]` 只保留空模块，不放置重写资源、本地节点、脚本、后端、证书或主机名。
- `[server_remote]` 也保持为空，不发布虚拟 URL、中文占位或禁用资源；用户在 `设置 → 节点 → 节点资源` 页面添加订阅。
- 配置顶部和 `[server_remote]` 段内都必须明确标出应用内添加路径。
- 校验器锁定 12 个模块的完整顺序和全部未使用空模块，防止以后把示例节点、第三方订阅、重写或 MitM 参数误当作默认配置发布。
