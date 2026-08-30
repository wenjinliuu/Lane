# Lane 路由与客户端语法决策记录

- 日期：2026-08-30
- 状态：已确认并实施；同日根据真机结果增补 D6、D7
- 初始基线：`main` @ `b278ec9`
- 增补基线：`main` @ `5eaa340`
- 增补实施分支：`codex/single-rule-tier-brokerage-order`
- 依据：分支 `claude/codex-project-audit-b2es64` 中 `docs/AUDIT-2026-08-30.md` 的审计问题，以及后续逐项复核

本文固定已经确认的产品语义和实施边界；生成器、测试与 `dist/` 均以本文为验收标准完成同步更新。

## D1. `China` 调整到 `Proxy` 前面

### 决策

域名规则尾部顺序调整为：

1. 自定义和业务专用域名规则；
2. `Brokerage IP`；
3. `China`；
4. 完整的 `Proxy`；
5. `Telegram IP`；
6. `CN-IP`；
7. 客户端 GeoIP / Final 兜底。

即：`Brokerage IP` 根据 D6 先于 `China`，`China` 必须先于 `Proxy`，而 `Proxy` 仍必须先于 Telegram、CN-IP 等后续公网 IP 规则。不要删除完整 `Proxy`，也不要把它缩成仅含少量冲突项的 `proxy-guard`。

这次修复的主体不是逐家公司维护一张手写白名单，而是让 v2fly `cn`（其中包含 `tld-cn`）的中国域名判断先于 `geolocation-!cn`。因此既能覆盖 `.cn` / `.com.cn`，也能覆盖上游明确收入中国集合的非 `.cn` 域名。

### 代表性变化

| 类别 | 代表域名 | 调整后的默认结果 |
| --- | --- | --- |
| 大陆对时 | `ntp.aliyun.com`、`ntp.tencent.com`、`ntp.ntsc.ac.cn`、`cn.pool.ntp.org` | `China` / DIRECT |
| NAS 中国入口 | `quickconnect.cn`、`myqnapcloud.cn`、`synology.cn`、`qnap.com.cn` | `China` / DIRECT |
| AWS 中国区 | `amazonaws.cn`、`amazonaws.com.cn` | `China` / DIRECT |
| 大陆金融/支付 | `hsbc.com.cn`、`visa.com.cn`、`mastercard.cn`、`paypal.com.cn` | `China` / DIRECT |
| 外企大陆站 | `nike.cn`、`ikea.cn`、`mcd.cn`、`starbucks.com.cn`、`adidas.cn` | `China` / DIRECT |
| 已特别讨论的中国入口 | `gigalife-api.tesla.cn` | `China` / DIRECT |

`bloomberg.cn`、`airbnb.cn` 这类境外品牌的中国域名也会按这项总原则改为 DIRECT。这是已知且接受的默认结果；如果日后实测某个域名必须代理，应在更靠前的业务规则或 `custom-proxy` 中做窄例外，不应恢复 `Proxy > China` 的整体顺序。

### 为什么 `Proxy` 仍放在 `CN-IP` 前面

域名身份通常比一次 DNS 解析得到的 IP 地理位置更可靠。已知境外域名可能解析到大陆 CDN、Anycast 或被客户端 GeoIP 数据库标为 CN；若先匹配 `CN-IP`，这些请求会被误判为 DIRECT。

调整后会形成以下语义：

- 已知中国域名：先由 `China` 判为 DIRECT；
- 已知境外域名：再由完整 `Proxy` 判为 Final，之后不受 CN IP 结果干扰；
- 未被域名规则识别的域名或直接访问 IP：会先检查带 `no-resolve` 的 `Brokerage IP`，再交给 China / Proxy、Telegram IP、`CN-IP` 和 GeoIP 兜底。

例如，某个已知境外域名即使临时解析到 CN 段，仍会先命中 `Proxy`；一个未知域名解析到 CN 段，则仍可命中 `CN-IP` 直连。`Proxy` 的策略虽然与最终 `MATCH` 同为 `Final`，但它的位置具有保护作用。

Google、Microsoft、AI、流媒体等业务规则继续放在 `China` 前面，所以 `google.cn` 仍命中 Google、`azure.cn` / `office365.cn` 仍命中 Microsoft，不会被这次换序改成直连。

## D2. Apple 保留“中国直连、其他可选”的拆分

### 决策

- 保留现有 `AppleCN` 直连规则，并合并 v2fly `apple` 中带 `@cn` 属性的条目；
- `AppleCN` 仍是内部规则集，不新增一个用户需要理解或手动选择的策略组；
- 其余 Apple 域名继续进入现有 Apple 策略组；
- Apple TV+、Apple Music 等更具体的业务规则仍按既有优先级先匹配；
- 不把所有 Apple 流量统一为代理或统一为直连；
- Google 和 Microsoft 保持现行策略组语义，不新增 GoogleCN / MicrosoftCN 默认直连。

目标案例包括 `apple.com.cn`、`icloud.com.cn` 直连，同时不改变普通 `apple.com` 及 Apple 海外服务的可选策略。

## D3. Stash 按 `behavior` 拆分规则载荷

### 决策

Stash 不再把全部规则集都声明为 `behavior: classical`。后续渲染器对每个逻辑规则集按实际条目类型拆分：

| 原始规则 | Stash provider | `format: text` 载荷 |
| --- | --- | --- |
| `DOMAIN,api.example.com` | `behavior: domain` | `api.example.com` |
| `DOMAIN-SUFFIX,example.com` | `behavior: domain` | `+.example.com` |
| `IP-CIDR,1.2.3.0/24` | `behavior: ipcidr` | `1.2.3.0/24` |
| `IP-CIDR6,2001:db8::/32` | `behavior: ipcidr` | `2001:db8::/32` |
| `DOMAIN-REGEX,...` 及其他非专用类型 | `behavior: classical` | 保留完整带类型规则 |

这里 `+.example.com` 很重要：它与 `DOMAIN-SUFFIX,example.com` 一样同时匹配根域和任意层级子域；`.example.com` 不匹配根域，不能作为等价替代。精确 `DOMAIN` 则必须保持裸域名，不能误扩成后缀规则。

一个同时含域名、IP、正则的逻辑规则集会生成多个 provider，例如 `proxy-domain`、`proxy-ipcidr`、`proxy-classical`，并在 `rules:` 中连续引用、使用完全相同的策略。逻辑规则集之间的原有先后顺序不得改变。

示意：

```yaml
rule-providers:
  proxy-domain:
    type: http
    behavior: domain
    format: text
    url: https://example.invalid/proxy-domain.list
    interval: 86400
  proxy-classical:
    type: http
    behavior: classical
    format: text
    url: https://example.invalid/proxy-classical.list
    interval: 86400

rules:
  - RULE-SET,proxy-domain,Final
  - RULE-SET,proxy-classical,Final
```

这仍然是远程规则集：URL、缓存路径和更新间隔继续存在，Stash 仍可静默更新。差别只是 Stash 用专用域名/IP 索引解析绝大多数条目；官方只给出“匹配性能 Excellent、内存 Low”与 `classical` 的“Average、Average”级别，没有可据此承诺的固定百分比提升。

首版继续使用可审计的文本格式，不引入 MRS。`no-resolve` 语义保持现状：

- `brokerage-ip`、`telegram-ip` 的 `RULE-SET` 引用继续带 `no-resolve`；
- `cn-ip` 不得带 `no-resolve`，否则域名请求会跳过 Lane 的 CN-IP 快照，退回客户端自身 GeoIP 判断。

为兼容独立审计和既有复用方式，Stash 同时保留每个逻辑规则集原来的带类型规范文件；Lane 主配置只引用按 behavior 生成的专用载荷。规范文件与专用载荷由校验器逐行绑定，防止二者语义漂移。

## D4. Loon 使用现行 IPv4-only 语法

### 决策

把：

```ini
ipv6 = false
```

改为：

```ini
ip-mode = ipv4-only
```

不同时保留新旧两行。生成配置所支持的最低 Loon 版本相应明确为 3.2.3 (754)；官方已将 `ipv6` 列为由 `ip-mode` 替代的兼容旧键。

## D5. UDP 不支持时采用显式拒绝回落

### 决策

只在已有明确语法的四个客户端显式写入：

| 客户端 | 配置 |
| --- | --- |
| Surge | `udp-policy-not-supported-behaviour = REJECT` |
| Shadowrocket | `udp-policy-not-supported-behaviour = REJECT` |
| Loon | `udp-fallback-mode = REJECT` |
| Quantumult X | `fallback_udp_policy = reject` |

Stash 与 Egern 暂不新增等价全局项，保持客户端默认行为。

这只在“规则选中的节点不支持 UDP 转发”时拒绝该 UDP 流量，避免静默 DIRECT 泄漏，并让支持回退的应用尽快改走 TCP/TLS；它不是全局封锁 UDP 或 QUIC。首版不增加 `block-quic`、`udp_drop_list = QUIC`、Loon `disable-udp-ports = 443` 或 Stash 全局 QUIC 脚本。

## D6. 补齐 Futu 三个域名，证券 IP 提前到 `China` 前

### 决策

在 `brokerage` 域名规则中补充当前 Futu 来源已有而 Lane 缺少的三个后缀：

- `futubos.com`
- `futuie.com`
- `futuhainan.com`

`brokerage-ip` 继续独立拆分，保留原来的 63 个 CIDR 与 `no_resolve: true`，不扩大网段；但其位置从 `China` / `Proxy` 之后调整到 `China` 之前。

最初仅补域名、保持 IP 位置不变，是为了避免共用云 IP 误伤。随后真机 A/B 测试给出了更强证据：Futu 交易在 `brokerage-ip` 位于 `CN-IP` / China 判定之后时失败，手动移到 China IP 判定之前即恢复。由于首匹配规则会让重叠中国网段先被 DIRECT 捕获，位置必须前移；`no-resolve` 继续防止这组 IP 规则为普通域名强制解析。该实测结论覆盖 D6 的初版“位置不变”记录。

## D7. 单一完整规则层，只做精确去重

### 决策

- 六个客户端统一只发布 `dist/<client>/rules/`，主配置直接引用这一层；不再维护 `rules-full/` 与 `rules-profile/` 两套数据。
- 编译只删除同一逻辑规则集内“类型 + 规范值”完全相同的精确重复。当前基线删除 77 条，发布 22 个规则集、共 51,206 条。
- 不删除被同组父级后缀覆盖的条目，也不按当前规则顺序删除已被更早规则集覆盖的条目。当前 4,736 条同组父后缀候选、合计 11,060 条覆盖候选只写入 `dist/metadata.json`，不改变载荷。
- Stash 的同名带类型规范文件继续保留；主配置仍只引用 `-domain`、`-ipcidr`、`-classical` 专用载荷，校验器逐行绑定两者语义。
- GoogleCN 不再作为 full-only 特例：不抓取、不转换、不发布，Google 域名统一进入 Google 策略。
- 当前 Loon、Shadowrocket、Surge、QX 各省略 174 条 `DOMAIN-REGEX`。逐条判断是否能安全转换是独立审计事项，本次不猜测改写，也不与产物收敛混合。

### 理由

父级后缀折叠会假设六个客户端对根域、任意层级子域以及单标签后缀有完全一致的语义；跨规则集残余还把数据文件绑定到 Lane 当前的首匹配顺序。官方文档在这些边界上并不完全对齐，因此不能把推断当作删除依据。精确重复不携带这些语义风险，可以继续安全移除。

## 实施验收项

1. 路由 golden cases 至少覆盖：
   - `ntp.aliyun.com -> China/DIRECT`
   - `quickconnect.cn -> China/DIRECT`
   - `amazonaws.cn -> China/DIRECT`
   - `gigalife-api.tesla.cn -> China/DIRECT`
   - `google.cn -> Google`
   - `azure.cn -> Microsoft`
   - `apple.com.cn -> AppleCN/DIRECT`
   - `1.14.242.1 -> Brokerage`，并且 `brokerage-ip` 先于 `China`
   - 已知境外域名先于 `CN-IP` 命中 `Proxy/Final`
   - 直接访问中国 IP 命中 `CN-IP/DIRECT`
2. Stash 做语义回归：精确域名不得扩大、后缀必须包含根域、多级子域仍匹配、正则策略不变、IPv4/IPv6 CIDR 均能加载。
3. Stash provider 拆分前后，对同一批 golden cases 的最终策略必须一致；允许改变的只有 D1 明确批准的 `China` / `Proxy` 重叠项。
4. Loon 生成物只出现 `ip-mode = ipv4-only`，不再出现 `ipv6 = false`。
5. 四端 UDP 回落配置各有生成器测试；Stash/Egern 不应被误加全局 QUIC 阻断。
6. 六端只存在 `rules/`，旧 `rules-full/` / `rules-profile/` 均不存在；元数据明确标注 exact-only，父后缀和跨组关系为 report-only。

## 主要参考

- [Stash Rule Sets](https://stash.wiki/en/rules/rule-set)
- [Mihomo rule-provider 载荷格式](https://wiki.metacubex.one/en/config/rule-providers/content/)
- [Mihomo 域名通配符语义](https://wiki.metacubex.one/en/handbook/syntax/#domain-wildcards)
- [Loon General Configuration](https://nsloon.app/en/docs/General/)
- [Surge General Section Options](https://manual.nssurge.com/profile/general.html)
- [Quantumult X 官方 sample.conf](https://github.com/crossutility/Quantumult-X/blob/master/sample.conf)
- [v2fly `apple` 数据（当前锁定修订）](https://github.com/v2fly/domain-list-community/blob/06111d32139e3497a20fded97ca2b4424ad87e60/data/apple)
