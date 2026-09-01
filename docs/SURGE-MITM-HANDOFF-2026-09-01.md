# 交接：Surge iOS MitM 拦截无法关闭（未解决）

> 这是一份交给另一个 AI 助手继续排查的背景材料。前半部分是**已确证的事实**和**已排除的假设**，请不要重复验证；后半部分是**待查方向**。

---

## 1. 项目背景

**Lane**（`github.com/wenjinliuu/Lane`）：用一份规则清单生成 Stash / Loon / Shadowrocket / Surge / Quantumult X / Egern 六种客户端的分流配置。

- Python 生成器：`src/proxyrules/`，核心是 `render.py`（渲染六端配置）和 `validate.py`（校验生成物）
- 声明式输入：`config/*.yaml`（策略组、地区正则、图标、规则清单、上游源）
- 生成产物：`dist/<client>/`，主配置 + 规则文件
- 命令：`python3 -m proxyrules build` / `python3 -m proxyrules check`；测试 `python3 -m pytest`（当前 187 项全绿）

**Lane 的设计前提**：分流只在 TCP / SNI 层做，**从不解密 HTTPS**。六端配置都不含重写、不含脚本。Surge 配置里只有一个 `[MITM]` 段用于声明"不解密"。

---

## 2. 未解决的问题

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

特征：**典型的机场"去广告"MitM 名单**（国内 App 的埋点 / 开屏广告域名 + Google 广告域名），还含裸 IP 项。用户确认这不是他自己配置的。

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

### 3.5 名单不在配置文件里

用户在 Surge 内置文本编辑器里截图确认，生效配置文件末尾是：
```
93
94  # Lane 不做 HTTPS 解密；显式关闭 MitM，...
95  [MITM]
96  enable = false
```
文件到 96 行结束，**没有 `hostname` 键**。同一时刻的日志显示 MitM 拦截了 107 次。

### 3.6 名单跨配置文件存活

依次换过三个配置文件（`测试.conf` → `Lane_surge.conf` → `Lane_surge 无 mi.conf`），同一份 MitM 名单一直生效，而且**名单还在变长**（后期新增了 `ogads-pa.clients6.google.com`、`dw-online.ksosoft.com`、`shuc-ios.ksord.com`）。

### 3.7 Surge 的 `[MITM]` 段**没有 `enable` 键**

查了多份线上在用的 Surge 配置，`[MITM]` 实际使用的键只有：
```
hostname   h2   skip-server-cert-verify   ca-p12   ca-passphrase
```
决定"解密哪些域名"的是 **`hostname`**。写 `enable = false` 是无效行，Surge 忽略（日志实证：文件里写着 `enable = false`，MitM 照样跑 107 次）。

### 3.8 排除法结论

| 可能来源 | 状态 |
|---|---|
| Lane 配置文件 | ❌ 已确认没有 `hostname` |
| 机场配置经 `policy-path` | ❌ 官方明确只取 `[Proxy]` |
| Surge 模块 | ❌ 日志只有内置模块 |
| **Surge 自身存储的 MitM 设置** | ✅ **只剩这一个** |

推测：用户早期可能装过机场的完整配置作为 profile，那一次 Surge 把机场的 `[MITM]` 写进了自己的核心设置，之后换配置文件时没跟着清掉。

---

## 4. 已尝试且失败的修复

| # | 尝试 | 结果 |
|---|---|---|
| 1 | 在配置写 `[MITM]` + `enable = false` | **无效**。`enable` 不是 Surge 的键，被忽略 |
| 2 | 改成 `[MITM]` + `hostname = -*`（`-*` = 排除全部域名） | **未确证**。用户重测后 MitM 仍在，但**无法确认他装的是哪一版文件**（两次文件名相同，日志不显示内容） |
| 3 | 用户关闭 iOS 的"证书信任设置" | 反而更糟：拦截照做，只是证书没人认，从形态 A 变成形态 B |

**⚠️ 未完成的关键动作**：一直没有让用户去 **Surge App 的 MitM 设置页面**查看/清空 hostname 列表。基于 3.8 的结论，这很可能就是名单的存放处，也是唯一能真正生效的地方。

---

## 5. 建议的下一步

按优先级：

1. **看 Surge App 里的 MitM 页面**（底部「更多」→ MitM / HTTPS 解密），检查「主机名 / Hostname」列表。如果列着第 2 节那批域名，直接清空 —— 这大概率就是解法。

2. **确证"与订阅无关"**：把配置里 `policy-path=` 那一行整行注释掉，重连，随便开个百度页面，导出日志。MitM 报错照样出现 → 板上钉钉在本地存储。这个测试不需要节点可用，只数 `grep -c SGMITM`。

3. **确认配置版本**：让用户确认生效文件末尾是 `enable = false` 还是 `hostname = -*`，否则第 2 次尝试的结论不成立。

4. **若 UI 里清不掉**：考虑 Surge 的配置重置 / 重装，或到 Surge 官方社区（community.nssurge.com）提问"MitM hostname 列表来源与清除方式"。

### 判据

问题解决的标志：日志里 `grep -c SGMITMConnection` 和 `grep -c SGTLSWrapperSocketCompatible` **都为 0**。

---

## 6. 顺带查证到的 Surge 行为（本次排查副产品，均已确证）

1. **QUIC 被阻断是正常的**。Surge 默认阻断发往代理服务器的 QUIC（`block-quic` 默认值为 `per-policy`，可选 `all-proxy` / `all` / `always-allow`），官方明确"不建议改"。抓包里对 QUIC 包回 `ICMP type=3 code=13`（管理性禁止）是预期行为，浏览器会回落 TCP。**这不是故障**。

2. **`tun-excluded-routes` 不接受 IPv6**。Surge 启动时报 `<WARNING> Invalid excluded route: ff02::fb/128` 并丢弃该条。Lane 已改为只写 IPv4（Shadowrocket 官方文档给出了 IPv6 写法，它与 Loon / Egern 保留完整列表）。**此修复已在日志中确证生效**。

3. **`policy-regex-filter` 不能加引号**。Surge 会把引号当作模式的一部分，被引号包住的正则匹配不到任何节点，策略组因此为空。Lane 已改为裸写（五个地区正则均不含逗号，本来就不需要引号保护）。

4. **Surge 支持 `icon-url`**，iOS 与 Mac 都读取。Lane 之前误以为是 Mac 专属而未写入，已补上。

---

## 7. 本次一并修复并已合入 main 的问题（供参考，不需要处理）

分支 `claude/config-compatibility-issues-jq1x26`，6 个 commit，已快进合并进 `main`（`6df53d1..558cffa`）。

| 客户端 | 问题 | 修复 |
|---|---|---|
| **Stash** | `Manual` 组同时写 `proxies` 和 `include-all: true`，Stash 只保留后者，五个地区 Auto 组不显示 | 改用 `use: [Subscription1]` 引入节点；地区组仍用 `include-all` |
| **Quantumult X** | 导入报语法错误。`[server_remote]` 里的占位符 `你的订阅地址` 不是合法资源地址 | 两条订阅模板默认注释；`excluded_routes` 收敛为纯 IPv4 |
| **Shadowrocket** | 生成了多余的 `Manual` 组 | 删除，改用内置 `PROXY` 策略（= 首页选中的节点）+ `policy-select-name=PROXY`；地区 `url-test` 组保留（它本身即自动测速，App 里那个"测试并选择最快服务器"是全局 UI 开关，与之无关） |
| **Surge** | 策略组图标不显示 / 正则被引号包住 / IPv6 排除路由被拒 | 补 `icon-url=`；`policy-regex-filter` 去引号；`tun-excluded-routes` 只写 IPv4 |

validator 对以上每一条都加了断言，回退会直接构建失败。

---

## 8. 交接说明

请基于第 3 节的**已确证事实**继续，不要重新验证已排除的假设（尤其是"机场配置经 policy-path 注入"和"Lane 分流规则有误"这两条）。第 5 节第 1 项是最可能的解法，成本极低，建议优先。
