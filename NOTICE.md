# Third-party notices

Lane compiles domain data from
[`v2fly/domain-list-community`](https://github.com/v2fly/domain-list-community),
which is distributed under the MIT License. Its copyright and license notice
remain available in the upstream repository.

Telegram network ranges are retrieved from Telegram's official
[`cidr.txt`](https://core.telegram.org/resources/cidr.txt) resource.

Policy icons are self-hosted under `assets/icons` as a small attributed subset
copied unchanged from
[`Koolson/Qure`](https://github.com/Koolson/Qure) commit
`b16b260625f873266f6a6a9b88710132774997b8`. Qure does not publish a standard
open-source license: its README requests attribution, restricts commercial use,
and assigns the underlying marks to their respective owners. The copied files
under `assets/icons/third-party/` are therefore excluded from Lane's MIT grant;
detailed provenance and the active mapping are in `assets/icons/README.md`.

The configuration layout and icon approach were informed by
[`Repcz/Tool`](https://github.com/Repcz/Tool); no Repcz rule list is vendored.

Generated files record their upstream revision in `dist/metadata.json`.

## CN IP data

The primary CN IPv4/IPv6 input is the `ip-lists` git history from
[`gaoyifan/china-operator-ip`](https://github.com/gaoyifan/china-operator-ip)
(Copyright (c) 2017 Yifan Gao;
[MIT License](licenses/gaoyifan-MIT.txt)). Lane reads five distinct daily
snapshots of `china.txt` and `china6.txt` and keeps address space present in at
least three snapshots. CIDR spelling is normalized before coverage is counted.
Generated `dist/*/rules/cn-ip.*` files are adapted MIT-licensed outputs.

[`misakaio/chnroutes2`](https://github.com/misakaio/chnroutes2) provides the
independent BGP-derived IPv4 reference used in `dist/cn-ip-validation.json`.
Copyright (c) 2021 Misaka Network, Inc.; its repository LICENSE identifies the
data as [CC BY-SA 4.0](licenses/CC-BY-SA-4.0.txt). The reference is used only for
comparison and is never merged into routing output. chnroutes2 does not publish
an IPv6 text list, which the report records explicitly.

`Loyalsoldier/geoip` remains useful for manual difference audits, but Lane no
longer consumes its release files as a build source.

## AppleCN

[`felixonmars/dnsmasq-china-list`](https://github.com/felixonmars/dnsmasq-china-list)
provides `apple.china.conf`.
Copyright © Felix Yan <felixonmars@archlinux.org>.
The upstream [WTFPL 2.0 license and notice](licenses/dnsmasq-china-list-WTFPL.txt)
are preserved. Lane extracts DNS domain selectors as suffix routing rules,
normalizes and deduplicates them, and translates them to client-native syntax;
it does not import upstream DNS server settings. AppleCN remains an independent
DIRECT rule set rather than being merged into China.

Upstream is a DNS acceleration project, so its lists record which domains a
Chinese resolver answers well — not which domains are reachable directly. For
Apple the two coincide: its entries resolve to mainland CDN nodes that can be
reached without a proxy. Lane does not fetch, transform or publish GoogleCN.

Lane publishes one complete `rules/` tier. It removes exact duplicate entries
within a logical ruleset, but retains parent-suffix and cross-ruleset coverage
candidates; those relationships are reported only in `dist/metadata.json`.
