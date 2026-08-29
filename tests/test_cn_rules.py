from copy import deepcopy
import hashlib
from io import BytesIO
import ipaddress
import json
from pathlib import Path
import random
import re
import shutil
from urllib.error import URLError

import pytest
import yaml

from proxyrules.cn_validation import _subtract, compare_cn_coverage
from proxyrules.compiler import compile_rulesets
from proxyrules.config import ConfigError, load_project_config, validate_config
from proxyrules.render import CONFIG_FILENAMES, TARGETS
from proxyrules.text_sources import parse_dnsmasq_domains, parse_text_source
from proxyrules.upstream import UpstreamError, fetch_text_source
from proxyrules.validate import ValidationError, validate_generated
from proxyrules.v2fly import DomainListError, parse_cidr_text


ROOT = Path(__file__).resolve().parents[1]


def test_dnsmasq_extracts_suffixes_not_dns_addresses():
    text = "# comment\nserver=/Apps.Apple.com/.fonts.gstatic.com/114.114.114.114#53 # comment\n"
    rules = parse_dnsmasq_domains(text, "sample")
    assert [rule.routing_key for rule in rules] == [
        ("domain", "apps.apple.com"), ("domain", "fonts.gstatic.com"),
    ]
    assert all(rule.source == "sample" for rule in rules)


@pytest.mark.parametrize("text", [
    "server=114.114.114.114", "server=//114.114.114.114",
    "server=/*example.com/114.114.114.114", "server=/a..com/114.114.114.114",
    "server=/example.com//114.114.114.114", "address=/example.com/0.0.0.0",
    "<html>rate limited</html>", "server=/cn/114.114.114.114",
])
def test_dnsmasq_rejects_unsupported_or_broadened_selectors(text):
    with pytest.raises(DomainListError):
        parse_dnsmasq_domains(text, "sample")


@pytest.mark.parametrize("text,spec", [
    ("# empty", {"format": "dnsmasq"}), ("", {"format": "cidr"}),
    ("0.0.0.0/0", {"format": "cidr"}), ("::/0", {"format": "cidr"}),
    ("2001:db8::/32", {"format": "cidr", "ip_version": 4}),
    ("1.2.3.0/24", {"format": "cidr", "ip_versions": [4, 6]}),
    ("1.2.3.0/24", {"format": "unknown"}),
])
def test_sources_fail_on_empty_invalid_or_missing_family(text, spec):
    with pytest.raises(DomainListError):
        parse_text_source(text, "sample", spec)


def test_compiler_parses_independent_sources_without_reference_leakage(tmp_path):
    entries = [{"id": "apple-cn", "title": "AppleCN", "policy": "DIRECT", "text_source": "apple_cn"}]
    texts = {"apple_cn": "server=/apps.apple.com/114.114.114.114\n" * 2}
    specs = {"apple_cn": {"format": "dnsmasq", "license": "WTFPL-2.0", "url": "https://example.org/apple"}}
    result = compile_rulesets(tmp_path, entries, None, texts, specs)
    assert len(result[0].rules) == 1
    assert result[0].policy == "DIRECT"
    assert result[0].source_notices[0] == "Source: https://example.org/apple"
    specs["apple_cn"]["role"] = "validation-only"
    with pytest.raises(ValueError, match="Validation-only"):
        compile_rulesets(tmp_path, entries, None, texts, specs)


def test_coverage_compares_addresses_not_prefix_spelling():
    primary = parse_cidr_text("1.2.3.0/24\n2001:db8::/32", "primary")
    reference = parse_cidr_text("1.2.3.0/25\n1.2.3.128/25\n2001:db8::/33\n2001:db8:8000::/33", "reference")
    report = compare_cn_coverage(primary, reference)
    assert report["status"] == "match"
    assert report["independent"] is False
    assert report["families"]["ipv6"]["common_addresses"] == str(2 ** 96)


def test_coverage_records_both_directions_without_changing_primary():
    primary = parse_cidr_text("1.2.3.0/24\n2001:db8::/32", "primary")
    reference = parse_cidr_text("1.2.3.0/25\n1.2.4.0/24\n2001:db8::/32", "reference")
    before = tuple(primary)
    report = compare_cn_coverage(primary, reference)
    assert report["status"] == "differs"
    assert report["families"]["ipv4"]["primary_only_cidrs"] == ["1.2.3.128/25"]
    assert report["families"]["ipv4"]["primary_only_cidr_count"] == 1
    assert report["families"]["ipv4"]["primary_only_cidrs_truncated"] is False
    assert report["families"]["ipv4"]["reference_only_cidrs"] == ["1.2.4.0/24"]
    assert tuple(primary) == before
    with pytest.raises(ValueError, match="IPv6"):
        compare_cn_coverage(primary, reference[:1])


def test_interval_subtraction_matches_small_exhaustive_sets():
    rng = random.Random(42)
    def intervals(values):
        output = []
        for value in sorted(values):
            if output and output[-1][1] + 1 == value:
                output[-1] = (output[-1][0], value)
            else:
                output.append((value, value))
        return output
    for _ in range(200):
        left = {value for value in range(100) if rng.random() < .6}
        right = {value for value in range(100) if rng.random() < .5}
        result = _subtract(intervals(left), intervals(right))
        assert {value for start, end in result for value in range(start, end + 1)} == left - right


def test_invalid_download_does_not_poison_valid_cache(tmp_path, monkeypatch):
    path = tmp_path / "text" / "sample.txt"
    path.parent.mkdir()
    path.write_text("1.2.3.0/24\n")
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **kw: BytesIO(b"<html>error</html>"))
    with pytest.raises(UpstreamError, match="Invalid source"):
        fetch_text_source("sample", {"url": "https://example.org"}, tmp_path, True, False)
    assert path.read_text() == "1.2.3.0/24\n"


def test_network_failure_uses_visible_cached_fallback(tmp_path, monkeypatch):
    path = tmp_path / "text" / "sample.txt"
    path.parent.mkdir()
    path.write_text("1.2.3.0/24\n")
    def fail(*args, **kwargs):
        raise URLError("offline")
    monkeypatch.setattr("urllib.request.urlopen", fail)
    with pytest.warns(UserWarning, match="using its cached"):
        content, digest = fetch_text_source("sample", {"url": "https://example.org"}, tmp_path, True, False)
    assert digest == hashlib.sha256(content.encode()).hexdigest()
    with pytest.raises(UpstreamError, match="Unable to fetch"):
        fetch_text_source("missing", {"url": "https://example.org"}, tmp_path, True, False)


@pytest.mark.parametrize(
    "change",
    ["cn-first", "cn-no-resolve", "apple-policy", "apple-late", "china-merged",
     "reference-routed", "google-cn-restored", "lan-late", "lan-resolves",
     "window-days", "presence-days", "breaker", "reference-shared"],
)
def test_manifest_rejects_cn_policy_source_and_order_regressions(change):
    config = deepcopy(load_project_config(ROOT))
    entries = config["rulesets"]["rulesets"]
    by_id = {entry["id"]: entry for entry in entries}
    if change == "cn-first":
        entries.insert(0, entries.pop())
    elif change == "cn-no-resolve":
        by_id["cn-ip"]["no_resolve"] = True
    elif change == "apple-policy":
        by_id["apple-cn"]["policy"] = "Apple"
    elif change == "apple-late":
        entries.remove(by_id["apple-cn"])
        entries.insert(-1, by_id["apple-cn"])
    elif change == "china-merged":
        by_id["china"]["text_source"] = "apple_cn"
    elif change == "google-cn-restored":
        config["sources"]["sources"]["google_cn"] = {
            "kind": "text", "format": "dnsmasq",
            "url": "https://example.invalid/google.china.conf", "license": "WTFPL-2.0",
        }
        entries.insert(
            entries.index(by_id["ai"]),
            {"id": "google-cn", "title": "GoogleCN", "policy": "DIRECT",
             "text_source": "google_cn"},
        )
    elif change == "lan-late":
        entries.remove(by_id["lan"])
        entries.insert(2, by_id["lan"])
    elif change == "lan-resolves":
        by_id["lan"].pop("no_resolve", None)
    elif change == "window-days":
        config["sources"]["sources"]["cn_ip_primary"]["window_days"] = 1
    elif change == "presence-days":
        config["sources"]["sources"]["cn_ip_primary"]["minimum_presence_days"] = 1
    elif change == "breaker":
        config["sources"]["sources"]["cn_ip_primary"]["breaker_percent"] = 5
    elif change == "reference-shared":
        config["sources"]["cross_validation"]["cn_ip"]["independent"] = False
    else:
        by_id["cn-ip"]["text_source"] = "cn_ipv4_reference"
    with pytest.raises(ConfigError):
        validate_config(config)


@pytest.mark.parametrize("target", TARGETS)
def test_generated_cn_rules_are_dual_stack_and_direct(target):
    suffix = "yaml" if target == "egern" else "list"
    path = ROOT / "dist" / target / "rules" / f"cn-ip.{suffix}"
    text = path.read_text()
    assert "gaoyifan/china-operator-ip/tree/ip-lists" in text
    assert "License: MIT" in text
    assert "no-resolve" not in text and "no_resolve" not in text
    if target == "egern":
        data = yaml.safe_load(text)
        assert data["ip_cidr_set"] and data["ip_cidr6_set"]
    else:
        v4, v6 = ("ip-cidr,", "ip6-cidr,") if target == "qx" else ("IP-CIDR,", "IP-CIDR6,")
        active = [line for line in text.splitlines() if line and not line.startswith("#")]
        assert any(line.startswith(v4) for line in active)
        assert any(line.startswith(v6) for line in active)
        if target == "qx":
            assert all(line.endswith(",direct") for line in active)


def _domain_policy(domain):
    config = yaml.safe_load((ROOT / "dist/stash/Lane_stash.yaml").read_text())
    for ref in config["rules"]:
        if not ref.startswith("RULE-SET,"):
            continue
        _, rule_id, policy = ref.split(",")
        for line in (ROOT / "dist/stash/rules" / f"{rule_id}.list").read_text().splitlines():
            if not line or line.startswith("#"):
                continue
            # Regex quantifiers can contain commas, e.g. {1,3}.
            kind, value = line.split(",", 1)
            if ((kind == "DOMAIN" and domain == value)
                    or (kind == "DOMAIN-SUFFIX" and (domain == value or domain.endswith("." + value)))
                    or (kind == "DOMAIN-REGEX" and re.search(value, domain))):
                return policy
    return "Final"


@pytest.mark.parametrize("domain,policy", [
    ("apps.apple.com", "DIRECT"), ("music.apple.com", "DIRECT"),
    ("www.google.com", "Google"), ("www.youtube.com", "YouTube"),
    ("api.openai.com", "AI"), ("ai.google.dev", "AI"),
    ("trade.futunn.com", "Brokerage"),
])
def test_representative_domain_priority(domain, policy):
    assert _domain_policy(domain) == policy


@pytest.mark.parametrize("domain", [
    "fonts.gstatic.com", "dl.google.com", "clientservices.googleapis.com",
    "app-measurement.com", "doubleclick.net", "recaptcha.net", "2mdn.net",
])
def test_former_google_cn_domains_now_follow_the_google_group(domain):
    """GoogleCN was removed on 2026-08-29. Its entries used to resolve to DIRECT;
    they now follow the Google policy group like every other Google domain.

    This is the one routing change that removal introduces, so it is pinned here
    rather than left implicit."""

    assert _domain_policy(domain) == "Google"


@pytest.mark.parametrize("prefix", ["10.0.0.0/8", "192.168.0.0/16", "172.16.0.0/12"])
def test_private_prefixes_are_direct_and_do_not_force_resolution(prefix):
    """Without these, traffic addressed to a router or a NAS by IP matches no rule
    and is proxied by FINAL. lan is the first ruleset, so the prefixes must carry
    no-resolve or every domain request would pay for a lookup at rule one."""

    lines = (ROOT / "dist/surge/rules/lan.list").read_text().splitlines()
    assert f"IP-CIDR,{prefix},no-resolve" in lines


def test_lan_omits_the_client_fake_ip_range():
    """Every supported client uses 198.18.0.0/15 for fake IP; claiming it as LAN
    would collide with that machinery."""

    assert "198.18." not in (ROOT / "dist/surge/rules/lan.list").read_text()


def test_cn_ip_does_not_override_brokerage_ip():
    config = yaml.safe_load((ROOT / "dist/stash/Lane_stash.yaml").read_text())
    address = ipaddress.ip_address("1.14.242.1")
    for ref in config["rules"]:
        if not ref.startswith("RULE-SET,"):
            continue
        _, rule_id, policy = ref.split(",")
        for line in (ROOT / "dist/stash/rules" / f"{rule_id}.list").read_text().splitlines():
            if line.startswith("IP-CIDR,") and address in ipaddress.ip_network(line.split(",")[1]):
                assert policy == "Brokerage"
                return
    pytest.fail("Brokerage IP rule not found")


@pytest.mark.parametrize("target", TARGETS)
def test_validator_rejects_wrong_cn_policy(target, tmp_path):
    shutil.copytree(ROOT / "dist", tmp_path / "dist")
    shutil.copytree(ROOT / "rules", tmp_path / "rules")
    path = tmp_path / "dist" / target / CONFIG_FILENAMES[target]
    text = path.read_text()
    if target == "stash":
        text = text.replace("RULE-SET,apple-cn,DIRECT", "RULE-SET,apple-cn,Manual")
    elif target == "egern":
        # Preserve the required header/notice strings when mutating just the rule.
        original = next(rule for rule in text.splitlines() if "apple-cn.yaml" in rule)
        tail = text.split(original, 1)[1]
        text = text.split(original, 1)[0] + original + tail.replace("policy: DIRECT", "policy: Manual", 1)
    else:
        lines = text.splitlines()
        index = next(i for i, line in enumerate(lines) if "apple-cn.list" in line)
        lines[index] = lines[index].replace("DIRECT", "Manual").replace("force-policy=direct", "force-policy=Manual")
        text = "\n".join(lines) + "\n"
    path.write_text(text)
    with pytest.raises(ValidationError, match="polic"):
        validate_generated(tmp_path, load_project_config(ROOT))


def test_comparison_is_independent_ipv4_and_primary_only():
    report = json.loads((ROOT / "dist/cn-ip-validation.json").read_text())
    assert report["independent"] is True
    assert report["license"] == "CC-BY-SA-4.0"
    assert list(report["sources"]["primary"]) == ["cn_ip_primary"]
    assert set(report["sources"]["reference"]) == {"cn_ipv4_reference"}
    assert set(report["families"]) == {"ipv4", "ipv6"}
    assert report["families"]["ipv4"]["reference_available"] is True
    assert report["families"]["ipv6"]["reference_available"] is False
    config = load_project_config(ROOT)
    entry = config["rulesets"]["rulesets"][-1]
    assert entry["id"] == "cn-ip" and entry["text_source"] == "cn_ip_primary"


@pytest.mark.parametrize("target", TARGETS)
def test_validator_rejects_cn_ip_before_service_rules(target, tmp_path):
    shutil.copytree(ROOT / "dist", tmp_path / "dist")
    shutil.copytree(ROOT / "rules", tmp_path / "rules")
    path = tmp_path / "dist" / target / CONFIG_FILENAMES[target]
    text = path.read_text()
    # Swap only the resource URLs; both rules use DIRECT, so policy checking
    # alone cannot detect the priority regression.
    text = (text.replace("/rules/apple-cn.", "/rules/priority-test.")
            .replace("/rules/cn-ip.", "/rules/apple-cn.")
            .replace("/rules/priority-test.", "/rules/cn-ip."))
    path.write_text(text)
    with pytest.raises(ValidationError, match="URLs or order"):
        validate_generated(tmp_path, load_project_config(ROOT))


def test_validator_rejects_mismatched_comparison_digest(tmp_path):
    shutil.copytree(ROOT / "dist", tmp_path / "dist")
    shutil.copytree(ROOT / "rules", tmp_path / "rules")
    path = tmp_path / "dist/cn-ip-validation.json"
    data = json.loads(path.read_text())
    data["sources"]["primary"]["cn_ip_primary"]["sha256"] = "0" * 64
    path.write_text(json.dumps(data))
    with pytest.raises(ValidationError, match="digests"):
        validate_generated(tmp_path, load_project_config(ROOT))


def test_validator_binds_window_digest_to_published_cn_ip(tmp_path):
    shutil.copytree(ROOT / "dist", tmp_path / "dist")
    shutil.copytree(ROOT / "rules", tmp_path / "rules")
    path = tmp_path / "dist/stash/rules/cn-ip.list"
    text = path.read_text()
    assert "IP-CIDR,1.12.0.0/14" in text
    path.write_text(text.replace("IP-CIDR,1.12.0.0/14", "IP-CIDR,1.12.0.0/15", 1))
    with pytest.raises(ValidationError, match="stable-window"):
        validate_generated(tmp_path, load_project_config(ROOT))


def test_validator_requires_explicit_breaker_acceptance(tmp_path):
    shutil.copytree(ROOT / "dist", tmp_path / "dist")
    shutil.copytree(ROOT / "rules", tmp_path / "rules")
    path = tmp_path / "dist/cn-ip-window.json"
    data = json.loads(path.read_text())
    data["breaker"]["exceeded"] = True
    data["breaker"]["accepted"] = False
    path.write_text(json.dumps(data))
    with pytest.raises(ValidationError, match="stable-window"):
        validate_generated(tmp_path, load_project_config(ROOT))

    data["breaker"]["accepted"] = True
    path.write_text(json.dumps(data))
    validate_generated(tmp_path, load_project_config(ROOT))
