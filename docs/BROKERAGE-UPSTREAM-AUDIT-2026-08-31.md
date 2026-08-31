# 香港证券规则上游审计

- 审计日期：2026-08-31
- 审计目标：寻找可复用的香港证券规则维护项目，并判断除 Futu / Moomoo、Tiger、Longbridge 外是否有足够证据扩充 Lane 的 `Brokerage`
- 结论：本轮不新增券商品牌。v2fly 继续作为域名库存主源；新增品牌必须先有“直连失败、指定代理恢复”的交易动作实测，再以最小域名进入生产规则。

## 结论摘要

公开项目能证明“某域名被某个作者归到券商品牌”，但通常不能证明“该域名在中国大陆必须代理，且代理后入金或交易恢复”。本次找到的组合券商清单大多是个人配置、待讨论 Issue，或由同一份数据转换出的派生文件，不能按仓库数量当成独立验证。

因此 Lane 采用两层证据：

1. 上游域名库存用于发现候选、跟踪品牌域名变化；
2. 真机交易动作测试用于决定是否进入 `Brokerage` 以及规则粒度。

按这个标准，现有生产结论保持为：

| 券商 | 生产规则 | 证据与处理 |
| --- | --- | --- |
| Futu / Moomoo | v2fly `futu`、项目补充域名、63 个既有 CIDR | 已有真机交易结果，保留较完整覆盖 |
| Tiger | `DOMAIN-SUFFIX,skytigris.cn` | 保留实测关键后缀，移除整组品牌/官网域名 |
| Longbridge | `DOMAIN,geotest.lbkrs.com` | 保留实测精确域名，移除整组品牌/官网域名 |

被移出的 Tiger / Longbridge 普通品牌域名仍会经 v2fly `geolocation-!cn → category-finance` 落到 `General Proxy` / `Final`，不是改成强制直连。

## 找到的维护项目

| 项目 | 实际来源与覆盖 | 证据等级 | Lane 的用法 |
| --- | --- | --- | --- |
| [v2fly/domain-list-community](https://github.com/v2fly/domain-list-community) | 分别维护 [`futu`](https://github.com/v2fly/domain-list-community/blob/master/data/futu)、[`itiger`](https://github.com/v2fly/domain-list-community/blob/master/data/itiger)、[`longbridge`](https://github.com/v2fly/domain-list-community/blob/master/data/longbridge)、[`ibkr`](https://github.com/v2fly/domain-list-community/blob/master/data/ibkr)；[`category-finance`](https://github.com/v2fly/domain-list-community/blob/master/data/category-finance) 汇总金融品牌 | 高质量域名库存；不是“必须代理”证明 | 继续作为主上游和变化监测源；路由策略由 Lane 单独决定 |
| [v2fly PR #3732](https://github.com/v2fly/domain-list-community/pull/3732) | 更新 Futu、Tiger、Longbridge 域名，并讨论中国大陆网络下入金/交易问题 | 有相关用户报告，但提交目标仍是域名分类 | 用于候选差分；不把整个品牌列表直接等同于最小交易链路 |
| [blackmatrix7 TigerFintech](https://github.com/blackmatrix7/ios_rule_script/tree/master/rule/Surge/TigerFintech) | README 标明规则来自 [LM-Firefly TigerFintech](https://github.com/LM-Firefly/Rules/blob/master/Domestic-Services/TigerFintech.list)，不是独立维护结论 | 可作 Tiger 候选库存；独立性有限 | 监测候选域名，不自动覆盖实测最小规则 |
| [blackmatrix7 Issue #1687](https://github.com/blackmatrix7/ios_rule_script/issues/1687) | 提议合并 Futu / Longbridge / Tiger 的宽规则；截至审计日仍是开放 Issue，未形成项目正式规则 | 讨论线索；没有合并验收，评论中的 Longbridge 反馈也不一致 | 不导入；保留为后续故障排查线索 |
| [LingJingMaster/Shadowrocket-Rules](https://github.com/LingJingMaster/Shadowrocket-Rules) | 个人 Shadowrocket 配置，组合 Futu、Longbridge、Tiger、Snowball X、IBKR、TradeUP、Schwab 等，README 明示合并其他项目 | 覆盖广但较新、派生关系多，缺少逐域名交易验证 | 只做候选池，不做生产上游 |
| [Repcz/EgernRules](https://github.com/Repcz/EgernRules) | 自动转换 blackmatrix7 规则到 Egern | 派生产物，不是第二份独立证据 | 不重复计票 |
| [Loyalsoldier/v2ray-rules-dat](https://github.com/Loyalsoldier/v2ray-rules-dat) / [MetaCubeX/meta-rules-dat](https://github.com/MetaCubeX/meta-rules-dat) | 聚合或编译 v2fly、Loyalsoldier、blackmatrix7 等既有源 | 适合多客户端发布，不增加证券路由证据 | 不作为独立证券上游 |
| [rulemesh HK securities aggressive](https://github.com/vtgpcmsvgs/rulemesh/blob/main/rules/region/hk/hk_securities_aggressive.list) | 明确标为个人 aggressive 规则，并结合 [HKEX 参与者网站快照](https://github.com/vtgpcmsvgs/rulemesh/blob/main/rules/upstream/hkex/sehk_participant_websites.list) | 适合发现券商官网；覆盖过宽，官网并非交易 API | 不导入整个清单；仅提取候选品牌供实测 |
| [Aethersailor Custom Direct](https://github.com/Aethersailor/Custom_OpenClash_Rules/blob/main/rule/Custom_Direct.list) | 社区个人收集，其中 `vbkr.com` 被标为华盛直连 | 与“证券都应代理”的假设相反，说明社区没有统一结论 | 把冲突当成必须实测的信号，不据此直接改路由 |

HKEX 的[参与者查询](https://www.hkex.com.hk/eng/plw/search.aspx?selecttype=se)和[参与者统计](https://www.hkex.com.hk/Market-Data/Statistics/Participant/Exchange-Participant-Data?sc_lang=en)适合核验机构身份。它们列出的公司或官网数量很多，但不能推出某个 App 的登录、入金、行情或下单接口必须代理；因此不能把 HKEX 官网快照整体转成 `Brokerage`。

## 其他券商候选

| 优先级 | 候选 | GitHub 维护现状 | 是否现在加入 | 后续验证重点 |
| --- | --- | --- | --- | --- |
| 1 | 华盛证券 / Valuable Capital | 没有成熟的专用代理规则；Issue 中出现 `hstong.com` 建议，[社区插件](https://github.com/fmz200/wool_scripts/blob/main/Loon/plugin/split/partH/HuaShengTong.lpx)能观察到 App 接口，其他项目却把 `vbkr.com` 标为直连 | 否 | 从 `interface.hstong.com` 及 [官方 Valuable 域名](https://www.vbkr.com/)开始抓取登录、入金、下单三个动作的连接，并做直连/HK 代理 A/B 测试 |
| 2 | uSMART | v2fly 没有专用条目；公开规则主要只出现官网或 HKEX 参与者网站 | 否 | 以[香港官网](https://www.usmart.hk/en)为品牌核验，先抓 App 实际 API，不能从官网域名反推 |
| 2 | Webull Hong Kong | v2fly 没有专用条目；公开规则主要只出现 `webull.hk` 官网 | 否 | 以[香港官方说明](https://www.webull.hk/en/help/faq/602-What-is-Webull-Securities-Limited)核验实体，分别测试登录、入金和交易 |
| 3 | Interactive Brokers Hong Kong | v2fly 有较成熟的 [`ibkr`](https://github.com/v2fly/domain-list-community/blob/master/data/ibkr) 域名库存 | 否 | 域名库存可直接用于抓包比对，但[香港实体](https://www.interactivebrokers.com.hk/en/home.php)是否需要独立于 `Final` 的证券出口仍无证据 |
| 排除 | Snowball X / 雪盈 | 个别个人组合规则有收录 | 否 | [官方披露](https://zhs.snowball-x.com/)称其未获香港 SFC 发牌且不面向香港公众，不纳入“香港证券核心覆盖” |

这里的“优先级”是测试顺序，不是品牌规模排名，也不是“必须代理”的结论。券商是否持牌、是否较大，与其交易 API 在某个网络环境下是否必须代理是两个问题。

## 以后新增规则的验收门槛

某个新券商只有同时满足以下条件才进入生产 `Brokerage`：

1. 在相同账号、设备和网络下复现目标动作直连失败；
2. 只改变网络路径后，使用指定地区代理稳定恢复；
3. 抓到目标动作实际访问的主机名，并排除统计、广告、静态资源和第三方支付页面；
4. 优先使用精确域名；只有同一服务确实轮换多个子域时才扩大为后缀；
5. 新增正向回归，同时增加相邻官网域名仍走 `Final` 的负向回归；
6. 上游只负责提示域名变化，不能绕过上述门槛自动扩大生产路由。

所以当前最合理的自动化不是把所有“香港券商官网”每天灌进规则，而是监测候选上游变更，发生变化时生成差异供 AI 审计；真实生产扩容仍绑定一次可复现的交易测试。
