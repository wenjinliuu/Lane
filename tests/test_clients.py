from pathlib import Path
import json
import re
import shutil

import pytest
import yaml

from proxyrules.compiler import CompiledRuleset
from proxyrules.config import load_project_config
from proxyrules.model import Rule
from proxyrules.render import (
    BASE_GROUP_NAME, CONFIG_FILENAMES, EGERN_RULE_FIELDS, GENERATED_HEADER,
    NODE_GROUP_NAME, RULES_DIR, QX_REQUIRED_EMPTY_SECTIONS, QX_REQUIRED_SECTIONS,
    STASH_PROVIDER_NAME, SUBSCRIPTION_PLACEHOLDER, TARGETS,
    render_all, render_egern_ruleset, render_rule,
)
from proxyrules.validate import ValidationError, _section, validate_generated


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("target", ["stash", "loon", "shadowrocket", "surge"])
def test_text_rules_preserve_exact_suffix_and_no_resolve(target):
    assert render_rule(Rule("full", "geotest.lbkrs.com"), target) == "DOMAIN,geotest.lbkrs.com"
    assert render_rule(Rule("domain", "skytigris.cn"), target) == "DOMAIN-SUFFIX,skytigris.cn"
    assert render_rule(Rule("ipcidr", "1.14.242.0/23"), target, True) == "IP-CIDR,1.14.242.0/23,no-resolve"
    assert render_rule(Rule("ipcidr6", "2001:db8::/32"), target, True) == "IP-CIDR6,2001:db8::/32,no-resolve"


@pytest.mark.parametrize("kind,value,expected", [
    ("full", "example.com", "host"),
    ("domain", "example.com", "host-suffix"),
    ("keyword", "example", "host-keyword"),
    ("ipcidr", "1.14.242.0/23", "ip-cidr"),
    ("ipcidr6", "2001:db8::/32", "ip6-cidr"),
])
def test_qx_native_rules_have_policies(kind, value, expected):
    assert render_rule(Rule(kind, value), "qx", True, "Brokerage") == f"{expected},{value},Brokerage"
    assert render_rule(Rule(kind, value), "qx", policy="DIRECT") == f"{expected},{value},direct"


def test_regex_is_never_converted_to_url_regex():
    rule = Rule("regexp", r"^example\d+\.com$")
    assert render_rule(rule, "stash") == "DOMAIN-REGEX," + rule.value
    for target in ("surge", "qx", "loon", "shadowrocket"):
        assert render_rule(rule, target) is None
    ruleset = CompiledRuleset("test", "Test", "Manual", (rule,))
    assert yaml.safe_load(render_egern_ruleset(ruleset)) == {"domain_regex_set": [rule.value]}
    with pytest.raises(ValueError, match="YAML"):
        render_rule(rule, "egern")


def test_egern_all_rule_kinds_and_no_resolve():
    rules = (
        Rule("full", "cdn.futustatic.com"), Rule("domain", "futu.com"),
        Rule("keyword", "futu"), Rule("regexp", r"^futu\d\.com$"),
        Rule("ipcidr", "1.14.242.0/23"), Rule("ipcidr6", "2001:db8::/32"),
    )
    result = yaml.safe_load(render_egern_ruleset(CompiledRuleset("broker", "Broker", "Brokerage", rules, True)))
    assert result["no_resolve"] is True
    for rule in rules:
        assert result[EGERN_RULE_FIELDS[rule.kind]] == [rule.value]


def test_stash_uses_specialized_payloads_without_changing_rule_semantics(tmp_path):
    config = load_project_config(ROOT)
    ruleset = CompiledRuleset(
        "sample",
        "Sample",
        "Manual",
        (
            Rule("full", "api.example.com"),
            Rule("domain", "example.com"),
            Rule("regexp", r"^edge\d{1,3}\.example\.net$"),
            Rule("ipcidr", "192.0.2.0/24"),
            Rule("ipcidr6", "2001:db8::/32"),
        ),
        True,
    )
    render_all(
        tmp_path,
        config["project"],
        config["policies"],
        config["icons"],
        [ruleset],
    )
    profile = yaml.safe_load(
        (tmp_path / "dist/stash/Lane_stash.yaml").read_text()
    )
    assert list(profile["rule-providers"]) == [
        "sample-domain", "sample-ipcidr", "sample-classical"
    ]
    assert [
        profile["rule-providers"][provider]["behavior"]
        for provider in profile["rule-providers"]
    ] == ["domain", "ipcidr", "classical"]
    assert profile["rules"][:3] == [
        "RULE-SET,sample-domain,Manual",
        "RULE-SET,sample-ipcidr,Manual,no-resolve",
        "RULE-SET,sample-classical,Manual",
    ]

    def payload(name):
        return [
            line for line in (
                tmp_path / "dist/stash/rules" / f"{name}.list"
            ).read_text().splitlines()
            if line and not line.startswith("#")
        ]

    assert payload("sample-domain") == ["api.example.com", "+.example.com"]
    assert payload("sample-ipcidr") == ["192.0.2.0/24", "2001:db8::/32"]
    assert payload("sample-classical") == [
        r"DOMAIN-REGEX,^edge\d{1,3}\.example\.net$"
    ]
    assert payload("sample") == [
        "DOMAIN,api.example.com",
        "DOMAIN-SUFFIX,example.com",
        "DOMAIN-REGEX,^edge\\d{1,3}\\.example\\.net$",
        "IP-CIDR,192.0.2.0/24,no-resolve",
        "IP-CIDR6,2001:db8::/32,no-resolve",
    ]


def test_shadowrocket_maps_shared_proxy_rule_policy_to_builtin_proxy(tmp_path):
    config = load_project_config(ROOT)
    ruleset = CompiledRuleset(
        "sample", "Sample", BASE_GROUP_NAME, (Rule("domain", "example.com"),)
    )
    render_all(
        tmp_path,
        config["project"],
        config["policies"],
        config["icons"],
        [ruleset],
    )
    text = (tmp_path / "dist/shadowrocket/Lane_shadowrocket.conf").read_text()
    assert any(
        line.startswith("RULE-SET,") and line.endswith(",PROXY")
        for line in _section(text, "Rule")
    )


def test_generated_rule_counts_agree_with_capability_report():
    metadata = json.loads((ROOT / "dist/metadata.json").read_text())
    report = json.loads((ROOT / "dist/report.json").read_text())
    for target in TARGETS:
        for entry in metadata["rulesets"]:
            suffix = "yaml" if target == "egern" else "list"
            path = ROOT / "dist" / target / RULES_DIR / f"{entry['id']}.{suffix}"
            if target == "egern":
                parsed = yaml.safe_load(path.read_text())
                count = sum(
                    len(values) for values in parsed.values() if isinstance(values, list)
                )
            else:
                count = sum(
                    1 for line in path.read_text().splitlines()
                    if line and not line.startswith("#")
                )
            assert (
                count
                + report["unsupported_rules"][target].get(entry["id"], 0)
                == entry["rules"]
            )


def test_subscription_templates_and_local_update_guidance():
    for target, filename in CONFIG_FILENAMES.items():
        text = (ROOT / "dist" / target / filename).read_text()
        if target in {"shadowrocket", "qx"}:
            assert SUBSCRIPTION_PLACEHOLDER not in text
            if target == "qx":
                for section in QX_REQUIRED_SECTIONS:
                    assert f"[{section}]" in text
                assert _section(text, "server_remote") == []
                assert "设置 → 节点 → 节点资源" in text
            continue
        occurrences = [line for line in text.splitlines() if SUBSCRIPTION_PLACEHOLDER in line
                       and not line.lstrip().startswith(("#", ";", "//"))]
        assert len(occurrences) == 1
        assert "本地配置" in text and "重新填入" in text
        assert "#!MANAGED-CONFIG" not in text
        assert "auto_update:" not in text
    stash = yaml.safe_load((ROOT / "dist/stash/Lane_stash.yaml").read_text())
    provider = stash["proxy-providers"]["Subscription1"]
    assert provider["interval"] > 0
    assert provider["benchmark-url"] == load_project_config(ROOT)["project"]["benchmark"]["url"]
    assert not (ROOT / "dist" / "qx" / "server-placeholder.conf").exists()


def test_proxy_exposes_regional_auto_groups_and_node_pool_on_five_clients():
    auto_names = ["US Auto", "JP Auto", "HK Auto", "TW Auto", "SG Auto"]

    stash = yaml.safe_load((ROOT / "dist/stash/Lane_stash.yaml").read_text())
    stash_groups = {group["name"]: group for group in stash["proxy-groups"]}
    assert stash_groups[NODE_GROUP_NAME]["include-all"] is True
    assert stash_groups[BASE_GROUP_NAME]["proxies"] == [*auto_names, NODE_GROUP_NAME]

    loon_groups = {
        line.split("=", 1)[0].strip(): line.split("=", 1)[1].strip()
        for line in _section((ROOT / "dist/loon/Lane_loon.conf").read_text(), "Proxy Group")
    }
    assert loon_groups[BASE_GROUP_NAME].split(",")[1:6] == auto_names
    assert loon_groups[BASE_GROUP_NAME].split(",")[6] == NODE_GROUP_NAME

    # Shadowrocket has no generated Proxy group: its built-in PROXY policy is the node picked
    # on the home screen, and every service group offers the region Auto groups.
    shadow_groups = {
        line.split("=", 1)[0].strip(): line.split("=", 1)[1].strip()
        for line in _section(
            (ROOT / "dist/shadowrocket/Lane_shadowrocket.conf").read_text(), "Proxy Group"
        )
    }
    assert BASE_GROUP_NAME not in shadow_groups
    assert shadow_groups["Final"].split(",")[1] == "PROXY"
    for name in auto_names:
        assert name in shadow_groups["Final"].split(",")
        assert shadow_groups[name].startswith("url-test,")

    surge_groups = {
        line.split("=", 1)[0].strip(): line.split("=", 1)[1].strip()
        for line in _section((ROOT / "dist/surge/Lane_surge.conf").read_text(), "Proxy Group")
    }
    assert surge_groups[BASE_GROUP_NAME].split(",")[1:6] == [
        "US Auto Smart", "JP Auto Smart", "HK Auto Smart", "TW Auto Smart", "SG Auto Smart"
    ]
    assert surge_groups[BASE_GROUP_NAME].split(",")[6] == NODE_GROUP_NAME

    qx_proxy = next(
        line for line in _section((ROOT / "dist/qx/Lane_qx.conf").read_text(), "policy")
        if line.startswith(f"static = {BASE_GROUP_NAME},")
    )
    assert [part.strip() for part in qx_proxy.split("=", 1)[1].split(",")][1:6] == auto_names
    assert [part.strip() for part in qx_proxy.split("=", 1)[1].split(",")][6] == NODE_GROUP_NAME

    egern = yaml.safe_load((ROOT / "dist/egern/Lane_egern.yaml").read_text())
    egern_groups = {
        next(iter(group.values()))["name"]: next(iter(group.values()))
        for group in egern["policy_groups"]
    }
    assert egern_groups[BASE_GROUP_NAME]["policies"] == [*auto_names, NODE_GROUP_NAME]
    assert "urls" not in egern_groups[BASE_GROUP_NAME]
    assert egern_groups[NODE_GROUP_NAME]["urls"] == [SUBSCRIPTION_PLACEHOLDER]
    assert "hidden" not in egern_groups[NODE_GROUP_NAME]
    egern_text = (ROOT / "dist/egern/Lane_egern.yaml").read_text()
    assert "&id" not in egern_text and "*id" not in egern_text


def test_brokerage_keeps_tiger_and_longbridge_to_tested_minimums():
    rules = {
        line for line in (ROOT / "dist/surge/rules/brokerage.list").read_text().splitlines()
        if line and not line.startswith("#")
    }
    assert "DOMAIN-SUFFIX,skytigris.cn" in rules
    assert "DOMAIN,geotest.lbkrs.com" in rules
    for broad_domain in (
        "itiger.com", "itigergrowth.com", "itigergrowtha.com", "itigerup.com",
        "laohu8.com", "tigerbbs.cn", "tigerbbs.com", "xiaohu8.com",
        "lbctrl.com", "lbkrs.com", "longbridge.cloud", "longbridge.cn",
        "longbridge.com", "longbridge.global", "longbridge.hk", "longbridge.sg",
        "longbridgeapp.com", "longbridgehk.com", "longportapp.com", "wbrks.com",
    ):
        assert f"DOMAIN-SUFFIX,{broad_domain}" not in rules


def test_region_groups_match_only_positive_terms_even_with_high_multiplier():
    text = (ROOT / "dist/egern/Lane_egern.yaml").read_text()
    groups = yaml.safe_load(text)["policy_groups"]
    regional = {next(iter(group.values()))["name"]: next(iter(group.values())) for group in groups[-10:]}
    for code, label in (("US", "美国"), ("JP", "日本"), ("HK", "香港"), ("TW", "台湾"), ("SG", "新加坡")):
        for mode in ("Auto", "Manual"):
            group = regional[f"{code} {mode}"]
            expression = group["filter"]
            assert group["flatten"] is True
            assert re.search(expression, f"{label} 10x 高倍率")
            assert re.search(expression, f"{code.lower()} 01")
            assert re.search(expression, f"S1-{code.lower()} 01")
            assert not re.search(expression, "韩国 KR 01")
            assert "(?!" not in expression


def test_surge_expands_subscription_members_instead_of_selected_node():
    groups = _section((ROOT / "dist/surge/Lane_surge.conf").read_text(), "Proxy Group")
    assert "policy-path=" in groups[0]
    assert groups[0].startswith("Subscription1 = select,")
    assert groups[0].endswith(",hidden=true")
    assert groups[1] == (
        f"{NODE_GROUP_NAME} = select,include-other-group=Subscription1,"
        "include-all-proxies=true,icon-url=https://raw.githubusercontent.com/"
        "wenjinliuu/Lane/main/assets/icons/third-party/qure/Proxy.png"
    )
    assert groups[2].startswith(
        f"{BASE_GROUP_NAME} = select,US Auto Smart,JP Auto Smart,HK Auto Smart,"
        f"TW Auto Smart,SG Auto Smart,{NODE_GROUP_NAME},icon-url="
    )
    for line in groups[-10:]:
        assert f"include-other-group={NODE_GROUP_NAME}" in line
        assert "policy-regex-filter=" in line
        assert f",{BASE_GROUP_NAME}," not in line
    # The hidden subscription source has no icon; every visible group does.
    assert "icon-url=" not in groups[0]
    for line in groups[1:]:
        assert "icon-url=" in line


def test_changed_rules_do_not_change_profile_timestamps(tmp_path):
    config = load_project_config(ROOT)
    rule = Rule("domain", "example.com")
    base = CompiledRuleset("sample", "Sample", "Manual", (rule,))
    args = (tmp_path, config["project"], config["policies"], config["icons"])
    render_all(*args, [base])
    before = {target: (tmp_path / "dist" / target / filename).read_bytes()
              for target, filename in CONFIG_FILENAMES.items()}
    changed = CompiledRuleset("sample", "Sample", "Manual", (rule, Rule("full", "api.example.com")))
    render_all(*args, [changed])
    for target, filename in CONFIG_FILENAMES.items():
        assert (tmp_path / "dist" / target / filename).read_bytes() == before[target]
    first = {str(path.relative_to(tmp_path)): path.read_bytes() for path in (tmp_path / "dist").rglob("*") if path.is_file()}
    render_all(*args, [changed])
    assert first == {str(path.relative_to(tmp_path)): path.read_bytes() for path in (tmp_path / "dist").rglob("*") if path.is_file()}


def test_egern_stale_generated_rule_files_are_removed(tmp_path):
    config = load_project_config(ROOT)
    args = (tmp_path, config["project"], config["policies"], config["icons"])
    old = CompiledRuleset("obsolete", "Obsolete", "Manual", (Rule("domain", "example.com"),))
    render_all(*args, [old])
    render_all(*args, [])
    for target in TARGETS:
        path = tmp_path / "dist" / target / RULES_DIR
        assert path.is_dir() and not list(path.iterdir())
        assert not (tmp_path / "dist" / target / "rules-full").exists()
        assert not (tmp_path / "dist" / target / "rules-profile").exists()


def test_legacy_migration_preserves_unrecognized_rule_files(tmp_path):
    config = load_project_config(ROOT)
    args = (tmp_path, config["project"], config["policies"], config["icons"])
    for target in TARGETS:
        suffix = "yaml" if target == "egern" else "list"
        for directory in ("rules-full", "rules-profile"):
            legacy = tmp_path / "dist" / target / directory
            legacy.mkdir(parents=True)
            (legacy / f"generated.{suffix}").write_text(
                GENERATED_HEADER + "DOMAIN-SUFFIX,example.com\n"
            )
            (legacy / f"personal.{suffix}").write_text("personal content\n")

    render_all(*args, [])

    for target in TARGETS:
        suffix = "yaml" if target == "egern" else "list"
        for directory in ("rules-full", "rules-profile"):
            legacy = tmp_path / "dist" / target / directory
            assert not (legacy / f"generated.{suffix}").exists()
            assert (legacy / f"personal.{suffix}").read_text() == "personal content\n"


def test_validator_rejects_broken_remote_rule_reference(tmp_path):
    shutil.copytree(ROOT / "dist", tmp_path / "dist")
    shutil.copytree(ROOT / "rules", tmp_path / "rules")
    shutil.copytree(ROOT / "assets/icons", tmp_path / "assets/icons")
    path = tmp_path / "dist/qx/Lane_qx.conf"
    path.write_text(
        path.read_text().replace(
            "/qx/rules/ai.list", "/qx/rules/missing.list"
        )
    )
    with pytest.raises(ValidationError, match="remote rule URLs"):
        validate_generated(tmp_path, load_project_config(ROOT))


def test_canonical_names_and_new_repository_urls():
    expected = {"Lane_stash.yaml", "Lane_loon.conf", "Lane_shadowrocket.conf",
                "Lane_surge.conf", "Lane_qx.conf", "Lane_egern.yaml"}
    assert set(CONFIG_FILENAMES.values()) == expected
    config = load_project_config(ROOT)
    assert config["project"]["project"]["name"] == "Lane"
    for target, filename in CONFIG_FILENAMES.items():
        text = (ROOT / "dist" / target / filename).read_text()
        assert "/wenjinliuu/Lane/" in text
        assert "/ProxyRules/" not in text
        assert not (ROOT / "dist" / target / f"{target}.conf").exists()
        assert not (ROOT / "dist" / target / f"{target}.yaml").exists()


def test_surge_carries_policy_group_icons_and_shadowrocket_does_not():
    """Surge iOS and Mac both read icon-url; Shadowrocket has no such parameter."""

    config = load_project_config(ROOT)
    icon_config = config["icons"]
    icon_base = icon_config["base"].rstrip("/")
    surge_groups = {
        line.split(" = ", 1)[0]: line.split(" = ", 1)[1]
        for line in _section((ROOT / "dist/surge/Lane_surge.conf").read_text(), "Proxy Group")
    }
    policies = config["policies"]
    for name in [BASE_GROUP_NAME, *policies["service_groups"]]:
        expected = f"{icon_base}/{icon_config['icons'][name]}"
        assert surge_groups[name].endswith(f",icon-url={expected}")
    for region in policies["regions"]:
        # icons.yaml stays client neutral, so the Smart group reuses the Auto icon.
        smart = f"{icon_base}/{icon_config['icons'][region['auto_name']]}"
        manual = f"{icon_base}/{icon_config['icons'][region['manual_name']]}"
        assert surge_groups[region["surge_smart_name"]].endswith(f",icon-url={smart}")
        assert surge_groups[region["manual_name"]].endswith(f",icon-url={manual}")
    assert "icon-url=" not in surge_groups["Subscription1"]
    assert surge_groups[NODE_GROUP_NAME].endswith(
        f"icon-url={icon_base}/{icon_config['icons'][BASE_GROUP_NAME]}"
    )
    assert icon_base not in (ROOT / "dist/shadowrocket/Lane_shadowrocket.conf").read_text()


def test_shadowrocket_service_groups_follow_the_built_in_proxy_policy():
    """Shadowrocket's PROXY policy is the node picked on the home screen."""

    config = load_project_config(ROOT)
    policies = config["policies"]
    text = (ROOT / "dist/shadowrocket/Lane_shadowrocket.conf").read_text()
    groups = {
        line.split(" = ", 1)[0]: line.split(" = ", 1)[1]
        for line in _section(text, "Proxy Group")
    }
    assert BASE_GROUP_NAME not in groups
    assert BASE_GROUP_NAME not in [line.split(",")[-1] for line in _section(text, "Rule")]
    expected_options = [
        "PROXY" if option == BASE_GROUP_NAME else option
        for option in policies["service_options"]
    ]
    for service in policies["service_groups"]:
        assert groups[service] == (
            f"select,{','.join(expected_options)},policy-select-name=PROXY"
        )
    for region in policies["regions"]:
        # url-test is Shadowrocket's automatic type; no extra switch enables it.
        assert groups[region["auto_name"]].startswith("url-test,")
        assert "interval=" in groups[region["auto_name"]]
        assert groups[region["manual_name"]].startswith("select,")


@pytest.mark.parametrize("target,old,new,error", [
    ("surge", ",icon-url=", ",icon-uri=", "Surge 我的节点"),
    ("surge", "policy-regex-filter=(?i)", 'policy-regex-filter="(?i)', "must not be quoted"),
    ("surge", "Google_Search.png", "Missing.png", "missing self-hosted icon"),
    ("stash", "  include-all: true\n",
     "  include-all: false\n", "Stash 我的节点"),
    ("shadowrocket", "Final = select,PROXY,",
     "Final = select,Proxy,", "must default to PROXY"),
    ("qx", "excluded_routes = 224.0.0.0/4, 239.255.255.250/32",
     "excluded_routes = 224.0.0.0/4, 239.255.255.250/32, ff02::fb/128",
     "excluded_routes"),
    ("surge", "tun-excluded-routes = 224.0.0.0/4, 239.255.255.250/32",
     "tun-excluded-routes = 224.0.0.0/4, 239.255.255.250/32, ff02::fb/128",
     "tun-excluded-routes"),
])
def test_validator_rejects_client_capability_regressions(tmp_path, target, old, new, error):
    shutil.copytree(ROOT / "dist", tmp_path / "dist")
    shutil.copytree(ROOT / "rules", tmp_path / "rules")
    shutil.copytree(ROOT / "assets/icons", tmp_path / "assets/icons")
    path = tmp_path / "dist" / target / CONFIG_FILENAMES[target]
    text = path.read_text(encoding="utf-8")
    assert old in text
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    with pytest.raises(ValidationError, match=error):
        validate_generated(tmp_path, load_project_config(ROOT))


def test_no_profile_decrypts_https():
    """Lane routes on TCP/SNI and does not configure HTTPS decryption."""

    for target, filename in CONFIG_FILENAMES.items():
        text = (ROOT / "dist" / target / filename).read_text()
        assert "[MITM]" not in text
        assert "hostname" not in text
        if target == "qx":
            assert _section(text, "mitm") == []
            for section in QX_REQUIRED_EMPTY_SECTIONS:
                assert _section(text, section) == []
        else:
            assert "[mitm]" not in text


def test_validator_rejects_any_profile_mitm_section(tmp_path):
    shutil.copytree(ROOT / "dist", tmp_path / "dist")
    shutil.copytree(ROOT / "rules", tmp_path / "rules")
    shutil.copytree(ROOT / "assets/icons", tmp_path / "assets/icons")
    path = tmp_path / "dist/surge/Lane_surge.conf"
    path.write_text(
        path.read_text(encoding="utf-8") + "\n[MITM]\nhostname = *\n",
        encoding="utf-8",
    )
    with pytest.raises(ValidationError, match="must not configure HTTPS decryption"):
        validate_generated(tmp_path, load_project_config(ROOT))
