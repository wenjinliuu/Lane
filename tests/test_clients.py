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
    CONFIG_FILENAMES, EGERN_RULE_FIELDS, SUBSCRIPTION_PLACEHOLDER, TARGETS,
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


def test_generated_rule_counts_agree_with_capability_report():
    metadata = json.loads((ROOT / "dist/metadata.json").read_text())
    report = json.loads((ROOT / "dist/report.json").read_text())
    for target in TARGETS:
        for entry in metadata["rulesets"]:
            suffix = "yaml" if target == "egern" else "list"
            path = ROOT / "dist" / target / "rules" / f"{entry['id']}.{suffix}"
            if target == "egern":
                parsed = yaml.safe_load(path.read_text())
                count = sum(len(values) for values in parsed.values() if isinstance(values, list))
            else:
                count = sum(1 for line in path.read_text().splitlines() if line and not line.startswith("#"))
            assert count + report["unsupported_rules"][target].get(entry["id"], 0) == entry["rules"]


def test_all_templates_have_one_active_subscription_and_local_update_guidance():
    for target, filename in CONFIG_FILENAMES.items():
        text = (ROOT / "dist" / target / filename).read_text()
        if target == "shadowrocket":
            assert SUBSCRIPTION_PLACEHOLDER not in text
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
    assert groups[1] == "Manual = select,include-other-group=Subscription1,include-all-proxies=true"
    for line in groups[-10:]:
        assert "include-other-group=Manual" in line
        assert "policy-regex-filter=" in line
        assert ",Manual," not in line


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
        assert not list((tmp_path / "dist" / target / "rules").iterdir())


def test_validator_rejects_broken_remote_rule_reference(tmp_path):
    shutil.copytree(ROOT / "dist", tmp_path / "dist")
    shutil.copytree(ROOT / "rules", tmp_path / "rules")
    path = tmp_path / "dist/qx/Lane_qx.conf"
    path.write_text(path.read_text().replace("/qx/rules/ai.list", "/qx/rules/missing.list"))
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
