# Lane 路由与客户端语法决策记录

- 日期：2026-08-30
- 状态：已确认并实施
- 基线：`main` @ `b278ec9`
- 实施分支：`codex/routing-decisions-2026-08-30`
- 依据：分支 `claude/codex-project-audit-b2es64` 中 `docs/AUDIT-2026-08-30.md` 的审计问题，以及后续逐项复核

本文固定已经确认的产品语义和实施边界；生成器、测试与 `dist/` 均以本文为验收标准完成同步更新。

## D1. `China` 调整到 `Proxy` 前面

### 决策

域名规则尾部顺序调整为：

1. 自定义和业务专用域名规则；
2. `China`；
3. 完整的 `Proxy`；
4. 业务专用 IP 规则；
5. `CN-IP`；
6. 客户端 GeoIP / Final 兜底。

即：`China` 必须先于 `Proxy`，但 `Proxy` 仍必须先于所有公网 IP 地理规则。不要删除完整 `Proxy`，也不要把它缩成仅含少量冲突项的 `proxy-guard`。

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
- 未被域名规则识别的域名或直接访问 IP：最后才交给业务 IP、`CN-IP` 和 GeoIP 兜底。

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

## D6. 补齐 Futu 三个域名，证券 IP 保持不动

### 决策

在 `brokerage` 域名规则中补充当前 Futu 来源已有而 Lane 缺少的三个后缀：

- `futubos.com`
- `futuie.com`
- `futuhainan.com`

`brokerage-ip` 继续独立拆分，保留原来的 63 个 CIDR、当前位置与 `no_resolve: true`；不扩大网段，也不把证券 IP 提前到域名规则阶段。这样先修复确认的域名缺口，同时避免共用云 IP 误伤和新的 DNS 强制解析。

## 实施验收项

1. 路由 golden cases 至少覆盖：
   - `ntp.aliyun.com -> China/DIRECT`
   - `quickconnect.cn -> China/DIRECT`
   - `amazonaws.cn -> China/DIRECT`
   - `gigalife-api.tesla.cn -> China/DIRECT`
   - `google.cn -> Google`
   - `azure.cn -> Microsoft`
   - `apple.com.cn -> AppleCN/DIRECT`
   - 已知境外域名先于 `CN-IP` 命中 `Proxy/Final`
   - 直接访问中国 IP 命中 `CN-IP/DIRECT`
2. Stash 做语义回归：精确域名不得扩大、后缀必须包含根域、多级子域仍匹配、正则策略不变、IPv4/IPv6 CIDR 均能加载。
3. Stash provider 拆分前后，对同一批 golden cases 的最终策略必须一致；允许改变的只有 D1 明确批准的 `China` / `Proxy` 重叠项。
4. Loon 生成物只出现 `ip-mode = ipv4-only`，不再出现 `ipv6 = false`。
5. 四端 UDP 回落配置各有生成器测试；Stash/Egern 不应被误加全局 QUIC 阻断。

## 主要参考

- [Stash Rule Sets](https://stash.wiki/en/rules/rule-set)
- [Mihomo rule-provider 载荷格式](https://wiki.metacubex.one/en/config/rule-providers/content/)
- [Mihomo 域名通配符语义](https://wiki.metacubex.one/en/handbook/syntax/#domain-wildcards)
- [Loon General Configuration](https://nsloon.app/en/docs/General/)
- [Surge General Section Options](https://manual.nssurge.com/profile/general.html)
- [Quantumult X 官方 sample.conf](https://github.com/crossutility/Quantumult-X/blob/master/sample.conf)
- [v2fly `apple` 数据（当前锁定修订）](https://github.com/v2fly/domain-list-community/blob/06111d32139e3497a20fded97ca2b4424ad87e60/data/apple)
