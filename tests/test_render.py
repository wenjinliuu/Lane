from pathlib import Path

import yaml

from proxyrules.config import load_project_config, validate_config
from proxyrules.model import Rule
from proxyrules.render import (
    CONFIG_FILENAMES,
    HIJACK_DNS_SERVERS,
    MULTICAST_EXCLUDED_ROUTES,
    PROFILE_HEADER,
    REAL_IP_DOMAINS,
    STASH_REAL_IP_DOMAINS,
    SUBSCRIPTION_PLACEHOLDER,
    _with_stable_update_time,
    render_rule,
    render_stash_payload_rule,
)
from proxyrules.validate import validate_generated


ROOT = Path(__file__).resolve().parents[1]


def test_rule_rendering_capabilities() -> None:
    regex = Rule("regexp", r"^example\\.com$")
    assert render_rule(regex, "stash") == r"DOMAIN-REGEX,^example\\.com$"
    assert render_rule(regex, "loon") is None
    assert render_rule(regex, "shadowrocket") is None
    cidr = Rule("ipcidr", "149.154.160.0/20")
    assert render_rule(cidr, "loon", no_resolve=True).endswith(",no-resolve")
    assert render_stash_payload_rule(Rule("full", "api.example.com"), "domain") == (
        "api.example.com"
    )
    assert render_stash_payload_rule(Rule("domain", "example.com"), "domain") == (
        "+.example.com"
    )
    assert render_stash_payload_rule(cidr, "ipcidr") == "149.154.160.0/20"
    assert render_stash_payload_rule(Rule("keyword", "example"), "classical") == (
        "DOMAIN-KEYWORD,example"
    )


def test_checked_in_outputs_are_valid_and_udp_fallback_is_fail_closed() -> None:
    config = load_project_config(ROOT)
    validate_config(config)
    validate_generated(ROOT, config)

    main_configs = [ROOT / "dist" / target / filename
                    for target, filename in CONFIG_FILENAMES.items()]
    for path in main_configs:
        text = path.read_text(encoding="utf-8")
        assert text.startswith(
            PROFILE_HEADER +
            "# Last updated: "
        )
    main_text = "\n".join(
        path.read_text(encoding="utf-8") for path in main_configs
    )
    assert all(word not in main_text for word in ("剩余", "到期", "官网", "客服"))

    stash_text = main_configs[0].read_text(encoding="utf-8")
    loon_text = main_configs[1].read_text(encoding="utf-8")
    shadow_text = main_configs[2].read_text(encoding="utf-8")
    main_by_target = {
        target: (ROOT / "dist" / target / filename).read_text(encoding="utf-8")
        for target, filename in CONFIG_FILENAMES.items()
    }
    udp_fallback = {
        "loon": "udp-fallback-mode = REJECT",
        "shadowrocket": "udp-policy-not-supported-behaviour = REJECT",
        "surge": "udp-policy-not-supported-behaviour = REJECT",
        "qx": "fallback_udp_policy = reject",
    }
    for target, setting in udp_fallback.items():
        assert main_by_target[target].count(setting) == 1
    assert "ip-mode = ipv4-only" in loon_text
    assert "ipv6 = false" not in loon_text
    assert all(
        value not in main_by_target[target].lower()
        for target in CONFIG_FILENAMES
        for value in ("block-quic", "udp_drop_list", "disable-udp-ports")
    )
    assert "REJECT" not in main_by_target["stash"].upper()
    assert "REJECT" not in main_by_target["egern"].upper()

    stash = yaml.safe_load(stash_text)
    assert {provider["behavior"] for provider in stash["rule-providers"].values()} == {
        "domain", "ipcidr", "classical"
    }
    assert stash["proxy-providers"]["Subscription1"]["url"] == SUBSCRIPTION_PLACEHOLDER
    assert "Stash / Clash" in stash_text
    assert "Loon 格式" in loon_text
    assert "添加节点订阅" not in shadow_text
    assert "US Auto" in stash_text and "US Manual" in stash_text
    assert "Fallback" not in main_text
    assert "South Korea" not in main_text

    service_names = config["policies"]["service_groups"]
    region_names = [
        name
        for region in config["policies"]["regions"]
        for name in (region["auto_name"], region["manual_name"])
    ]
    expected_group_names = ["Manual", *service_names, *region_names]
    assert [group["name"] for group in stash["proxy-groups"]] == expected_group_names

    loon_group_block = loon_text.split("[Proxy Group]\n", 1)[1].split(
        "\n[Remote Rule]", 1
    )[0]
    assert [
        line.split(" = ", 1)[0]
        for line in loon_group_block.splitlines()
        if " = " in line
    ] == expected_group_names

    shadow_group_block = shadow_text.split("[Proxy Group]\n", 1)[1].split(
        "\n[Rule]", 1
    )[0]
    assert [
        line.split(" = ", 1)[0]
        for line in shadow_group_block.splitlines()
        if " = " in line
    ] == expected_group_names

    icon_config = config["icons"]
    icon_base = icon_config["base"].rstrip("/")
    for group in stash["proxy-groups"]:
        assert group["icon"] == (
            f"{icon_base}/{icon_config['icons'][group['name']]}"
        )

    expected_icons = {
        "AI": "lane/AI.png",
        "Schwab": "lane/Schwab.png",
        "Brokerage": "lane/Brokerage.png",
        "Crypto": "lane/Crypto.png",
        "Apple": "third-party/qure/Apple_1.png",
        "Streaming": "third-party/qure/Netflix.png",
        "Final": "third-party/qure/Global.png",
        "US Auto": "third-party/qure-derived/US_Auto.png",
        "JP Auto": "third-party/qure-derived/JP_Auto.png",
        "HK Auto": "third-party/qure-derived/HK_Auto.png",
        "TW Auto": "third-party/qure-derived/TW_Auto.png",
        "SG Auto": "third-party/qure-derived/SG_Auto.png",
        "US Manual": "third-party/qure/United_States.png",
        "JP Manual": "third-party/qure/Japan.png",
        "HK Manual": "third-party/qure/Hong_Kong.png",
        "TW Manual": "third-party/qure/China.png",
        "SG Manual": "third-party/qure/Singapore.png",
    }
    for name, relative in expected_icons.items():
        assert icon_config["icons"][name] == relative

    for name, relative in icon_config["icons"].items():
        path = ROOT / "assets/icons" / relative
        data = path.read_bytes()
        assert data[:8] == b"\x89PNG\r\n\x1a\n", name
        assert (int.from_bytes(data[16:20], "big"),
                int.from_bytes(data[20:24], "big")) == (144, 144), name

    for target in ("stash", "loon", "qx", "egern"):
        text = main_by_target[target]
        assert all(
            f"{icon_base}/{relative}" in text
            for relative in icon_config["icons"].values()
        )
        assert "raw.githubusercontent.com/Koolson/Qure" not in text


def test_client_dns_and_multicast_capability_matrix() -> None:
    paths = {
        target: ROOT / "dist" / target / filename
        for target, filename in CONFIG_FILENAMES.items()
    }
    text = {target: path.read_text() for target, path in paths.items()}
    route_csv = ", ".join(MULTICAST_EXCLUDED_ROUTES)
    real_ip_csv = ", ".join(REAL_IP_DOMAINS)
    hijack_csv = ", ".join(HIJACK_DNS_SERVERS)

    assert f"bypass-tun = {route_csv}" in text["loon"]
    assert f"tun-excluded-routes = {route_csv}" in text["shadowrocket"]
    assert f"tun-excluded-routes = {route_csv}" in text["surge"]
    assert f"excluded_routes = {route_csv}" in text["qx"]
    egern = yaml.safe_load(text["egern"])
    assert egern["vif_excluded_routes"] == list(MULTICAST_EXCLUDED_ROUTES)
    assert "excluded" not in text["stash"]

    stash = yaml.safe_load(text["stash"])
    assert stash["dns"]["fake-ip-filter"] == list(STASH_REAL_IP_DOMAINS)
    assert f"real-ip = {real_ip_csv}" in text["loon"]
    assert f"always-real-ip = {real_ip_csv}" in text["shadowrocket"]
    assert f"always-real-ip = {real_ip_csv}" in text["surge"]
    assert f"dns_exclusion_list = {real_ip_csv}" in text["qx"]
    assert egern["real_ip_domains"] == list(REAL_IP_DOMAINS)

    for target in ("loon", "shadowrocket", "surge"):
        assert f"hijack-dns = {hijack_csv}" in text[target]
    assert egern["hijack_dns"] == list(HIJACK_DNS_SERVERS)
    assert "hijack-dns" not in text["stash"]
    assert "hijack-dns" not in text["qx"]
    assert "*:53" not in "\n".join(text.values())
    assert "dns-server = system" in text["surge"]
    # QX's [dns] server takes resolver addresses only; the system resolvers are
    # the default and are disabled with no-system, so `server = system` is not a
    # value it accepts.
    assert "\n[dns]\nno-ipv6\n" in text["qx"]
    assert "server = system" not in text["qx"]
    assert egern["dns"]["bootstrap"] == ["system"]

    all_profiles = "\n".join(text.values())
    assert "lancache.steamcontent.com" not in all_profiles
    assert "appboot.netflix.com" not in all_profiles


def test_update_time_is_preserved_when_content_is_unchanged(tmp_path: Path) -> None:
    path = tmp_path / "config.conf"
    body = PROFILE_HEADER + "value=one\n"
    first = _with_stable_update_time(path, body)
    path.write_text(first, encoding="utf-8")

    assert "# Last updated: " in first
    assert _with_stable_update_time(path, body) == first

    changed = _with_stable_update_time(path, body.replace("one", "two"))
    assert "value=two" in changed
    assert changed != first
