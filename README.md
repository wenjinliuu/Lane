# ProxyRules

一份规则清单，自动生成 Stash、Loon 与 Shadowrocket 三套配置。策略组、规则顺序、节点筛选和上游版本全部由同一套声明式配置管理，避免三个客户端各自维护后逐渐失配。

## 当前设计

- 所有策略组名称均使用简洁英文。
- `AI`、`Google`、`Developer`、`Telegram`、`Social`、券商、交易所、视频、游戏平台等服务组均默认选择 `Manual`。
- 服务组可切换到 `DIRECT`、`Auto`、`Fallback` 或六个地区组。
- 地区组包括 `United States`、`Japan`、`Hong Kong`、`Taiwan`、`Singapore`、`South Korea`，可选择地区自动优选、`Manual`、`DIRECT` 或具体地区节点。
- `Brokerage` 只合并 Futu、Tiger 与 Longbridge；`Schwab` 单独成组。
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

Stash 与 Loon 的公开配置故意使用 `https://example.com/replace-with-your-subscription` 作为节点订阅占位符。导入后请只在本地替换它，**不要把私人订阅地址提交到公开仓库**。Shadowrocket 请先在客户端中添加节点订阅，再使用本配置的策略组与规则。

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

`dist/metadata.json` 固定记录上游 commit、文本源 SHA-256 与各规则集数量；`dist/report.json` 明确记录不同客户端无法表示的规则类型。生成文件不写入当前时间，因此上游未变化时不会制造无意义提交。

## 规则来源与许可

- [v2fly/domain-list-community](https://github.com/v2fly/domain-list-community)（MIT）
- [Telegram 官方 CIDR](https://core.telegram.org/resources/cidr.txt)
- [Koolson/Qure](https://github.com/Koolson/Qure)（仅引用图标 URL）

本项目自身以 MIT License 发布。第三方来源与借鉴边界见 [`NOTICE.md`](NOTICE.md)。
