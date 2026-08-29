from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .text_sources import text_source_ids


class ConfigError(ValueError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigError(f"Unable to load {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"Expected a mapping in {path}")
    return data


def load_project_config(root: Path) -> dict[str, Any]:
    config_dir = root / "config"
    return {
        "project": load_yaml(config_dir / "project.yaml"),
        "sources": load_yaml(config_dir / "sources.yaml"),
        "icons": load_yaml(config_dir / "icons.yaml"),
        "policies": load_yaml(config_dir / "policies.yaml"),
        "rulesets": load_yaml(config_dir / "rulesets.yaml"),
    }


def validate_config(config: dict[str, Any]) -> None:
    policies = config["policies"]
    rulesets = config["rulesets"].get("rulesets", [])
    services = policies.get("service_groups", [])
    options = policies.get("service_options", [])
    regions = policies.get("regions", [])

    if not services or services[-1] != "Final":
        raise ConfigError("Final must be the last service group")
    if not options or options[0] != "Manual":
        raise ConfigError("Manual must be the default service option")
    if "DIRECT" not in options:
        raise ConfigError("Every service group must expose DIRECT")
    if len({item["name"] for item in regions}) != len(regions):
        raise ConfigError("Region names must be unique")
    if [item.get("code") for item in regions] != ["US", "JP", "HK", "TW", "SG"]:
        raise ConfigError("Regions must be US, JP, HK, TW and SG in that order")

    base_names = [entry.get("name") for entry in policies.get("base_groups", [])]
    if base_names != ["Manual"]:
        raise ConfigError("Manual must be the only base strategy group")

    expected_options = ["Manual", "DIRECT"]
    for region in regions:
        expected_options.extend([region.get("auto_name"), region.get("manual_name")])
    if options != expected_options:
        raise ConfigError("Service options must expose each region's Auto and Manual groups")

    allowed_policies = set(services) | {"DIRECT", "Manual"}
    ids: set[str] = set()
    sources = config["sources"]["sources"]
    for entry in rulesets:
        rule_id = entry.get("id")
        if not rule_id or rule_id in ids:
            raise ConfigError(f"Invalid or duplicate ruleset id: {rule_id!r}")
        ids.add(rule_id)
        try:
            source_ids = text_source_ids(entry)
        except (TypeError, ValueError) as exc:
            raise ConfigError(f"Invalid text sources in {rule_id}: {exc}") from exc
        for source_id in source_ids:
            source = sources.get(source_id, {})
            if source.get("kind") != "text" or source.get("role") == "validation-only":
                raise ConfigError(f"Invalid routing source {source_id!r} in {rule_id}")
        if entry.get("policy") not in allowed_policies:
            raise ConfigError(
                f"Unknown policy {entry.get('policy')!r} in ruleset {rule_id}"
            )

    forbidden_groups = {
        "Auto",
        "Fallback",
        "South Korea",
        "Global",
        "Major Crypto Exchanges",
        "Other Crypto Exchanges",
        "Reject",
    }
    configured_groups = set(services) | set(base_names) | set(options)
    if forbidden_groups.intersection(configured_groups):
        raise ConfigError("Removed policy groups must not be reintroduced")

    crypto = next((item for item in rulesets if item.get("id") == "crypto"), None)
    if not crypto:
        raise ConfigError("Crypto ruleset is required")
    if crypto.get("v2fly") != ["binance", "okx", "bybit"]:
        raise ConfigError("Crypto must contain only Binance, OKX, Bybit plus Bitget custom rules")

    ai = next((item for item in rulesets if item.get("id") == "ai"), None)
    if not ai or "category-ai-cn" in ai.get("v2fly", []):
        raise ConfigError("Mainland AI must not be captured by the AI policy")

    ordered_ids = [entry["id"] for entry in rulesets]
    by_id = {entry["id"]: entry for entry in rulesets}
    for rule_id, source_id, main_id in (("apple-cn", "apple_cn", "apple"),):
        entry = by_id.get(rule_id, {})
        if (entry.get("policy") != "DIRECT" or text_source_ids(entry) != [source_id]
                or sources[source_id].get("format") != "dnsmasq"
                or entry.get("v2fly") or entry.get("custom")):
            raise ConfigError(f"{rule_id} must be an independent DIRECT dnsmasq ruleset")
        if ordered_ids.index(rule_id) >= ordered_ids.index(main_id):
            raise ConfigError(f"{rule_id} must precede {main_id}")
    # google.china.conf is a DNS acceleration list, not a routing list: resolving
    # a domain through a Chinese resolver does not make Google's China front-end
    # addresses reachable. Reintroducing it would send dl.google.com and
    # clientservices.googleapis.com DIRECT, which is a known way to hang Chrome
    # and the Play Store. Apple's list is different and stays.
    if "google-cn" in by_id or "google_cn" in sources:
        raise ConfigError("GoogleCN was removed deliberately and must not return")

    lan = by_id.get("lan", {})
    if ordered_ids[0] != "lan" or lan.get("policy") != "DIRECT" or not lan.get("no_resolve"):
        raise ConfigError("lan must be the first ruleset, DIRECT and no-resolve")
    cn_ip = by_id.get("cn-ip", {})
    if (ordered_ids[-1] != "cn-ip" or cn_ip.get("policy") != "DIRECT"
            or text_source_ids(cn_ip) != ["cn_ip_primary"]
            or cn_ip.get("no_resolve") or cn_ip.get("v2fly") or cn_ip.get("custom")):
        raise ConfigError("cn-ip must be the last ruleset, DIRECT, using the primary CN source")
    primary_spec = sources["cn_ip_primary"]
    if primary_spec.get("format") != "cidr" or primary_spec.get("ip_versions") != [4, 6]:
        raise ConfigError("Primary CN IP source must contain IPv4 and IPv6")
    for version in (4, 6):
        spec = sources[f"cn_ipv{version}_reference"]
        if spec.get("format") != "cidr" or spec.get("ip_version") != version:
            raise ConfigError(f"CN IPv{version} source must enforce its address family")
    check = config["sources"].get("cross_validation", {}).get("cn_ip", {})
    if (check.get("ruleset") != "cn-ip"
            or check.get("reference_sources") != ["cn_ipv4_reference", "cn_ipv6_reference"]
            or check.get("independent") is not False
            or any(sources.get(key, {}).get("role") != "validation-only"
                   for key in ("cn_ipv4_reference", "cn_ipv6_reference"))):
        raise ConfigError("gaoyifan must be a validation-only, non-independent CN reference")
    if text_source_ids(by_id["china"]):
        raise ConfigError("CN exceptions and CN IP must not be merged into China")
