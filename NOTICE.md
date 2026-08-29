# Third-party notices

Lane compiles domain data from
[`v2fly/domain-list-community`](https://github.com/v2fly/domain-list-community),
which is distributed under the MIT License. Its copyright and license notice
remain available in the upstream repository.

Telegram network ranges are retrieved from Telegram's official
[`cidr.txt`](https://core.telegram.org/resources/cidr.txt) resource.

Policy icons are referenced by URL rather than redistributed. The primary icon
set is [`Koolson/Qure`](https://github.com/Koolson/Qure). The configuration
layout and icon approach were informed by
[`Repcz/Tool`](https://github.com/Repcz/Tool); no Repcz rule list is vendored.

Generated files record their upstream revision in `dist/metadata.json`.

## CN IP data

The primary CN IPv4/IPv6 input is the `ip-lists` git history from
[`gaoyifan/china-operator-ip`](https://github.com/gaoyifan/china-operator-ip)
(Copyright (c) 2017 Yifan Gao;
[MIT License](licenses/gaoyifan-MIT.txt)). Lane reads seven distinct daily
snapshots of `china.txt` and `china6.txt` and keeps address space present in at
least five snapshots. CIDR spelling is normalized before coverage is counted.
Generated `dist/*/rules-full/cn-ip.*` and
`dist/*/rules-profile/cn-ip.*` files are adapted MIT-licensed outputs.

[`misakaio/chnroutes2`](https://github.com/misakaio/chnroutes2) provides the
independent BGP-derived IPv4 reference used in `dist/cn-ip-validation.json`.
Copyright (c) 2021 Misaka Network, Inc.; its repository LICENSE identifies the
data as [CC BY-SA 4.0](licenses/CC-BY-SA-4.0.txt). The reference is used only for
comparison and is never merged into routing output. chnroutes2 does not publish
an IPv6 text list, which the report records explicitly.

`Loyalsoldier/geoip` remains useful for manual difference audits, but Lane no
longer consumes its release files as a build source.

## AppleCN and full-only GoogleCN

[`felixonmars/dnsmasq-china-list`](https://github.com/felixonmars/dnsmasq-china-list)
provides `apple.china.conf` and `google.china.conf`.
Copyright © Felix Yan <felixonmars@archlinux.org>.
The upstream [WTFPL 2.0 license and notice](licenses/dnsmasq-china-list-WTFPL.txt)
are preserved. Lane extracts DNS domain selectors as suffix routing rules,
normalizes and deduplicates them, and translates them to client-native syntax;
it does not import upstream DNS server settings. AppleCN remains an independent
DIRECT rule set rather than being merged into China. GoogleCN is emitted only
as a complete `rules-full/google-cn` artifact for audit and independent reuse;
no generated Lane profile references it.

Upstream is a DNS acceleration project, so its lists record which domains a
Chinese resolver answers well — not which domains are reachable directly. For
Apple the two coincide: its entries resolve to mainland CDN nodes that can be
reached without a proxy. For Google they do not, which is why Lane excludes
GoogleCN from default routing while retaining the attributed WTFPL-derived
complete artifact.

`rules-profile` files are order-dependent residual transformations of the same
attributed inputs: Lane removes entries already covered by a parent suffix or
an earlier first-match rule. This optimization does not change the upstream
license or the routing result of the generated profile.
