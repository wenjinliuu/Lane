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

The primary CN IPv4/IPv6 input is
[`Loyalsoldier/geoip`](https://github.com/Loyalsoldier/geoip), specifically
[`release/text/cn.txt`](https://github.com/Loyalsoldier/geoip/blob/release/text/cn.txt).
It is attributed to Loyalsoldier and contributors and distributed under
[CC BY-SA 4.0](licenses/Loyalsoldier-CC-BY-SA-4.0.txt).
Lane normalizes/deduplicates CIDRs and translates them into client-native syntax.
Generated `dist/*/rules/cn-ip.*` and the derived CN IP comparison data retain
CC BY-SA 4.0; Lane's MIT code license does not replace the data license.

CN data in that project also derives from
[`gaoyifan/china-operator-ip`](https://github.com/gaoyifan/china-operator-ip)
(Copyright (c) 2017 Yifan Gao;
[MIT License](licenses/gaoyifan-MIT.txt)). Lane uses gaoyifan's `ip-lists/china.txt`
and `china6.txt` for comparison only, not as an additional routing source.
This is a shared-upstream consistency check, not independent geolocation validation.

## AppleCN / GoogleCN

[`felixonmars/dnsmasq-china-list`](https://github.com/felixonmars/dnsmasq-china-list)
provides `apple.china.conf` and `google.china.conf`.
Copyright © Felix Yan <felixonmars@archlinux.org>.
The upstream [WTFPL 2.0 license and notice](licenses/dnsmasq-china-list-WTFPL.txt)
are preserved. Lane extracts DNS domain selectors as suffix routing rules,
normalizes and deduplicates them, and translates them to client-native syntax;
it does not import upstream DNS server settings. These remain independent
DIRECT rule sets rather than being merged into China.
