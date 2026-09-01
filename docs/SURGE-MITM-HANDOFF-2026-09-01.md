# Surge iOS MitM 拦截：已解决

> 2026-09-01 更新：用户关闭 Surge 的「HTTP 捕获」后，受影响网站立即恢复正常访问。根因已经由实机对照确认，不再需要通过 profile 写入任何 MitM 关闭项。

## 0. 最新结论

- **根因**：Surge iOS 的 HTTP 捕获处于开启状态，并通过捕获层自动 MitM 活跃主机。
- **版本证据**：Surge iOS 5.21.0 的官方更新日志明确写明，HTTP 捕获设置不再存放于配置文件；捕获开启后可为特定主机名额外开启 MitM，且不受 MitM 主开关关闭影响。
- **现象解释**：设置跨配置保留，是因为捕获层不属于 profile；所谓“名单变长”，更可能只是手机后台出现了新的 HTTPS 主机，并非机场持续注入固定广告名单。
- **处理结果**：关闭「HTTP 捕获」后恢复正常。无需修改订阅、分流规则或证书。
- **配置结论**：Lane 恢复最小原则，Surge 产物不写 `[MITM]`；捕获与解密状态留给 App 管理。

---

## 1. 项目背景

**Lane**（`github.com/wenjinliuu/Lane`）：用一份规则清单生成 Stash / Loon / Shadowrocket / Surge / Quantumult X / Egern 六种客户端的分流配置。

- Python 生成器：`src/proxyrules/`，核心是 `render.py`（渲染六端配置）和 `validate.py`（校验生成物）
- 声明式输入：`config/*.yaml`（策略组、地区正则、图标、规则清单、上游源）
- 生成产物：`dist/<client>/`，主配置 + 规则文件
- 命令：`python3 -m proxyrules build` / `python3 -m proxyrules check`；测试 `python3 -m pytest`（当前 197 项全绿）

**Lane 的设计前提**：分流只在 TCP / SNI 层做，**从不解密 HTTPS**。六端配置都不启用重写或脚本，也不配置任何 MitM 主机名、证书或解密参数；QX 仅为空配置导入保留一个空的 `[mitm]` 模块头。

---

## 2. 原问题

Surge iOS 持续对一批与 Lane 无关的域名做 MitM（HTTPS 解密），且**无法通过配置文件关闭**。被拦截的连接在 TLS 握手阶段被直接掐断，用户侧表现为"大量网站打不开"。

### 环境

| 项 | 值 |
|---|---|
| 客户端 | Surge iOS **5.21.1 (3810)**，2026-08-10 构建 |
| 系统 | iOS **26.6.1** (23G83)，未越狱 |
| 生效配置 | iCloud Drive 上的 `Lane_surge*.conf`（Lane 生成，用户手工填了订阅地址） |
| 节点来源 | 机场订阅，通过配置里 `Subscription1 = select,policy-path=<机场URL>,...` 引入 |
| 机场链接返回内容 | **一份完整的 Surge 配置**（含 `[Proxy]`、`[Rule]`、`[MITM]` 等），不是纯节点列表 |

### 被 MitM 拦截的域名（多次日志累积）

```
mbd.baidu.com      m.baidu.com        hm.baidu.com       hpd.baidu.com
h2tcbox.baidu.com  s.bdstatic.com     sv.bdstatic.com    b.bdstatic.com
search-splash.cdn.bcebos.com          dig.bdurl.net      is.snssdk.com
ci.xiaohongshu.com dispatcher.is.autonavi.com            sessions.bugsnag.com
dw-online.ksosoft.com                 shuc-ios.ksord.com www.uhdnow.com
itunes.com         www.google.com     play.google.com    news.google.com
ogads-pa.clients6.google.com          fonts.gstatic.com  www.google-analytics.com
ssl.gstatic.com    lh3~lh6.googleusercontent.com         139.227.230.40/46
```

最初这些主机被误判为机场“去广告”MitM 名单。结合 HTTP 捕获已确认开启，更准确的解释是：它们是手机前台和后台实际出现的 HTTPS 流量，捕获层逐步对新出现的主机尝试解密，因此观察到的集合持续变长。

### 两种失败形态（取决于 CA 证书状态）

**形态 A — CA 缺失或未生成**
```
<WARNING> [SGMITMConnection-9] Failed to generate MitM cert for: www.google.com.hk
```
Surge 签不出证书 → 直接关闭连接。抓包实证（tunnel 侧）：
```
SYN → SYN-ACK → ACK
ClientHello (1540 B) →
← ACK
← FIN        ← ClientHello 之后 1 毫秒，零字节返回
→ ACK, → RST
```
Safari 报"无法与服务器建立安全的连接"。

**形态 B — CA 存在但设备不信任**
```
<WARNING> [SGTLSWrapperSocketCompatible] TLS handshake with play.google.com failed:
          error:10000416:SSL routines:OPENSSL_internal:SSLV3_ALERT_CERTIFICATE_UNKNOWN
<NOTIFY>  [SGMITMConnection] Client closed connection without sending any request over
          the MitM connection, it might because of certificate pinning. Host: ...
```
Surge 签出了假证书，客户端回 TLS alert 46（certificate_unknown）拒绝。

**形态 C — CA 存在且被信任**（唯一"能用"的状态）
只有做了 certificate pinning 的站点仍失败：`ssl.gstatic.com`、`fonts.gstatic.com`、`lh3~lh6.googleusercontent.com`、`www.google-analytics.com`。Google 页面的图片和字体加载不出来。

---

## 3. 已确证的事实（不要重复验证）

### 3.1 Lane 的分流规则是正确的

用配置独立复算过域名匹配，结果与 Surge 自己的日志一致：

| 域名 | 命中规则集 | 策略 |
|---|---|---|
| `www.google.com.hk` | `google.list` → `DOMAIN-SUFFIX,google.com.hk` | Google（代理） |
| `github.com` | `developer.list` → `DOMAIN-SUFFIX,github.com` | Developer（代理） |
| `gspe1-ssl.ls.apple.com` | `apple.list` → `DOMAIN-SUFFIX,apple.com` | Apple（代理） |

没有任何一条被误判成 DIRECT。规则不是原因。

### 3.2 节点和线路是好的

同一份抓包里，`gspe1-ssl.ls.apple.com` 走**同一个节点**（`🇺🇸 美国高级 IEPL 专线 3`）完成了完整 TLS 握手：ClientHello → 548 ms 后收到 3538 字节的 ServerHello + 证书。节点不是原因。

### 3.3 MitM 名单**不可能**来自 `policy-path`

Surge 官方说明：`policy-path` 的 URL 可以是纯节点列表，**也可以是一份完整 Surge 配置，Surge 会自动从中提取 `[Proxy]` 段**。只提取 `[Proxy]`，不读 `[MITM]` / `[Rule]` / `[General]`。

（这也符合安全设计：否则任何机场都能通过订阅链接开启对用户设备的 HTTPS 解密。）

用户最初怀疑是机场配置经 `policy-path` 注入的，**这个假设已被排除**。

### 3.4 不是 Surge 模块

三份日志的模块加载行都只有一条：
```
[SGTMain] Apply module: HomeKit Accessories Quirk
```
这是 Surge 内置模块。没有第三方模块。

### 3.5 解密来源不在配置文件里

用户在 Surge 内置文本编辑器里截图确认，生效配置文件末尾是：
```
93
94  # Lane 不做 HTTPS 解密；显式关闭 MitM，...
95  [MITM]
96  enable = false
```
文件到 96 行结束，**没有 `hostname` 键**。同一时刻的日志显示 MitM 拦截了 107 次。这与 5.21.0+ HTTP 捕获设置独立于配置保存的官方行为一致。

### 3.6 捕获状态跨配置文件存活

依次换过三个配置文件（`测试.conf` → `Lane_surge.conf` → `Lane_surge 无 mi.conf`），MitM 一直生效，而且观察到的主机集合还在变长（后期新增了 `ogads-pa.clients6.google.com`、`dw-online.ksosoft.com`、`shuc-ios.ksord.com`）。HTTP 捕获是配置外的 App 状态，因此切换 profile 不会将其关闭。

### 3.7 Surge 的 `[MITM]` 段**没有 `enable` 键**

查了多份线上在用的 Surge 配置，`[MITM]` 实际使用的键只有：
```
hostname   h2   skip-server-cert-verify   ca-p12   ca-passphrase
```
决定"解密哪些域名"的是 **`hostname`**。写 `enable = false` 是无效行，Surge 忽略（日志实证：文件里写着 `enable = false`，MitM 照样跑 107 次）。

### 3.8 排除法结论（已更新）

| 可能来源 | 状态 |
|---|---|
| Lane 配置文件 | ❌ 已确认没有 `hostname` |
| 机场配置经 `policy-path` | ❌ 官方明确只取 `[Proxy]` |
| Surge 模块 | ❌ 日志只有内置模块 |
| 普通 MitM 主机名列表残留 | ⚠️ 不再是首要解释 |
| **HTTP 捕获的自动 MitM** | ✅ **用户已确认捕获开关打开，且符合官方行为** |

此前“旧机场 profile 把 `[MITM]` 永久写进核心设置”的推测没有官方依据，现由 HTTP 捕获层给出了更完整、版本完全吻合的解释。

---

## 4. 已尝试且失败的修复

| # | 尝试 | 结果 |
|---|---|---|
| 1 | 在配置写 `[MITM]` + `enable = false` | **无效**。`enable` 不是 Surge 的键，被忽略 |
| 2 | 改成 `[MITM]` + `hostname = -*`（`-*` = 排除全部域名） | 不能覆盖配置外的 HTTP 捕获自动 MitM；问题解决后已从 Lane 撤回，避免过度配置 |
| 3 | 用户关闭 iOS 的"证书信任设置" | 反而更糟：拦截照做，只是证书没人认，从形态 A 变成形态 B |

**最终关键动作**：用户关闭 HTTP 捕获后，网站访问恢复正常。

---

## 5. 最终结果

关闭 Surge 的「HTTP 捕获」总开关后，原先打不开的网站恢复正常。这个 A/B 结果足以确认故障由捕获层自动 MitM 引起，而不是 Lane 分流、节点、机场 `policy-path` 或证书本身。

---

## 6. 顺带查证到的 Surge 行为（本次排查副产品，均已确证）

1. **QUIC 被阻断是正常的**。Surge 默认阻断发往代理服务器的 QUIC（`block-quic` 默认值为 `per-policy`，可选 `all-proxy` / `all` / `always-allow`），官方明确"不建议改"。抓包里对 QUIC 包回 `ICMP type=3 code=13`（管理性禁止）是预期行为，浏览器会回落 TCP。**这不是故障**。

2. **`tun-excluded-routes` 不接受 IPv6**。Surge 启动时报 `<WARNING> Invalid excluded route: ff02::fb/128` 并丢弃该条。Lane 已改为只写 IPv4（Shadowrocket 官方文档给出了 IPv6 写法，它与 Loon / Egern 保留完整列表）。**此修复已在日志中确证生效**。

3. **`policy-regex-filter` 不能加引号**。Surge 会把引号当作模式的一部分，被引号包住的正则匹配不到任何节点，策略组因此为空。Lane 已改为裸写（五个地区正则均不含逗号，本来就不需要引号保护）。

4. **Surge 支持 `icon-url`**，iOS 与 Mac 都读取。Lane 之前误以为是 Mac 专属而未写入，已补上。

---

## 7. 同期兼容性修改及后续修正

分支 `claude/config-compatibility-issues-jq1x26`，6 个 commit，已快进合并进 `main`（`6df53d1..558cffa`）。

| 客户端 | 问题 | 修复 |
|---|---|---|
| **Stash** | `proxies + include-all` 真机只显示全部节点并隐藏地区组 | 恢复 `Manual.proxies + Manual.use`：前者固定五个地区 Auto，后者显式列出代理集；新增订阅或覆写时必须同步维护完全相同的代理集名称 |
| **Quantumult X** | 中文占位符和注释订阅模板会导致完整配置导入失败；真机又依次报缺少 `[server_remote]`、`[server_local]`、`[rewrite_remote]` | 按官方顺序保留 12 个完整模块；`[server_remote]` 只有默认禁用的 Lane 空资源，其余未使用模块为空，不启用重写、脚本、后端或 MitM；`excluded_routes` 仍为纯 IPv4 |
| **Shadowrocket** | 生成了多余的 `Manual` 组 | 删除，改用内置 `PROXY` 策略（= 首页选中的节点）+ `policy-select-name=PROXY`；地区 `url-test` 组保留（它本身即自动测速，App 里那个"测试并选择最快服务器"是全局 UI 开关，与之无关） |
| **Surge** | 策略组图标不显示 / 正则被引号包住 / IPv6 排除路由被拒 | 补 `icon-url=`；`policy-regex-filter` 去引号；`tun-excluded-routes` 只写 IPv4；不再写 `[MITM]` |
| **Egern** | 2.20.0 中 `Manual` 直接混合地区 Auto 与订阅节点时只能稳定显示一侧；重复加载同一订阅又会触发节点去重 | 保持 `Manual → 五个地区 Auto + All Nodes`；订阅只在可见的 `All Nodes.urls` 填写一次，地区组从中 `flatten` 并筛选 |

validator 对以上每一条都加了断言，回退会直接构建失败。

---

## 8. 当前状态

问题已解决并完成配置收尾：HTTP 捕获关闭后访问恢复，Lane 的六端产物均保持不配置 HTTPS 解密。
