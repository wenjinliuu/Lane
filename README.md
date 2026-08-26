# ProxyRules

一份规则清单，自动生成 Stash、Loon 与 Shadowrocket 三套配置。策略组、规则顺序、节点筛选和上游版本全部由同一套声明式配置管理，避免三个客户端各自维护后逐渐失配。

## 当前设计

- 所有策略组名称均使用简洁英文。
- `AI`、`Google`、`Developer`、`Telegram`、`Social`、券商、交易所、视频、游戏平台等服务组均默认选择 `Manual`。
- `Manual` 包含用户导入的全部节点，不排除流量、到期、高倍率或维护信息项。
- 地区仅保留美国、日本、香港、台湾与新加坡；每个地区分别提供 `XX Auto` 自动优选和 `XX Manual` 手动选点。
- 地区筛选只使用国旗、简体中文地区名、英文全称与常见简称做正向匹配，不使用城市、机场代码或排除词。
- 服务组可切换到 `DIRECT`，或五个地区各自的 Auto / Manual 策略。
- `Brokerage` 合并 Futu、Moomoo、Tiger 与 Longbridge；`Schwab` 单独成组。除 v2fly 上游外，还合并经过实际使用的补充域名与 Futu IP 段。
- `Crypto` 只匹配 Binance、OKX、Bybit 与 Bitget。其他交易所不单独分类，按后续规则或 `Final` 处理。
- 中国大陆 AI 不设专门规则，自然落入 `cn` / `GEOIP,CN` 直连。
- 不设置游戏大文件下载特例，不内置广告拦截，也不生成默认 `REJECT` 规则。
- 未命中流量进入 `Final`，而 `Final` 默认跟随 `Manual`。

完整策略声明见 [`config/policies.yaml`](config/policies.yaml)，规则顺序见 [`config/rulesets.yaml`](config/rulesets.yaml)。

## 使用配置

| 客户端 | 配置地址 |
| --- | --- |
| Stash | `https://raw.githubusercontent.com/wenjinliuu/ProxyRules/main/dist/stash/stash.yaml` |
| Loon | `https://raw.githubusercontent.com/wenjinliuu/ProxyRules/main/dist/loon/loon.conf` |
| Shadowrocket | `https://raw.githubusercontent.com/wenjinliuu/ProxyRules/main/dist/shadowrocket/shadowrocket.conf` |

三份公开配置均不包含订阅地址或占位符。Stash 导入后请进入「设置 → 配置文件 → 选中本配置 → 可视化编辑 → 远程代理集 → +」添加节点订阅；Loon 请进入「配置 → 节点 → + → 添加订阅」。Shadowrocket 直接使用客户端中已有的节点订阅。

图标通过 Qure 的公开 Raw URL 引用：Stash 使用 `icon`，Loon 使用 `img-url`，Shadowrocket 不强制设置自定义图标。

## 目录结构

```text
config/                 项目、策略、图标、上游与规则清单
rules/custom/           少量本地维护规则
src/proxyrules/         解析、编译、渲染与校验代码
dist/stash/             Stash 配置与规则
dist/loon/              Loon 配置与规则
dist/shadowrocket/      Shadowrocket 配置与规则
tests/                  单元测试
```

## 本地生成

需要 Python 3.11+ 与 Git：

```bash
python -m pip install -e '.[dev]'
python -m proxyrules build --refresh
python -m pytest
python -m proxyrules check
```

离线复现已缓存的上游版本：

```bash
python -m proxyrules build --offline
```

也可以传入本地的 `v2fly/domain-list-community` 仓库：

```bash
python -m proxyrules build --upstream-dir /path/to/domain-list-community
```

## 自动更新

GitHub Actions 每天 UTC 04:00（北京时间 12:00）执行以下流程：

1. 拉取最新 v2fly 域名库与 Telegram 官方 CIDR。
2. 编译三端规则并运行测试、结构校验。
3. 仅在 `dist/` 真实变化时创建自动更新提交。

`dist/metadata.json` 固定记录上游 commit、文本源 SHA-256 与各规则集数量；`dist/report.json` 明确记录不同客户端无法表示的规则类型。三份主配置记录最后一次实际内容更新的北京时间；内容未变化时保留原时间，不会制造无意义提交。

## 规则来源与许可

- [v2fly/domain-list-community](https://github.com/v2fly/domain-list-community)（MIT）
- [Telegram 官方 CIDR](https://core.telegram.org/resources/cidr.txt)
- [Koolson/Qure](https://github.com/Koolson/Qure)（仅引用图标 URL）

本项目自身以 MIT License 发布。第三方来源与借鉴边界见 [`NOTICE.md`](NOTICE.md)。
