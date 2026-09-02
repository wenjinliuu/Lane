from __future__ import annotations

from pathlib import Path, PurePosixPath
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
    if not options or options[0] != "Proxy":
        raise ConfigError("Proxy must be the default service option")
    if "DIRECT" not in options:
        raise ConfigError("Every service group must expose DIRECT")
    if len({item["name"] for item in regions}) != len(regions):
        raise ConfigError("Region names must be unique")
    if [item.get("code") for item in regions] != ["US", "JP", "HK", "TW", "SG"]:
        raise ConfigError("Regions must be US, JP, HK, TW and SG in that order")
    expected_smart_names = [f"{item['code']} Auto Smart" for item in regions]
    if [item.get("surge_smart_name") for item in regions] != expected_smart_names:
        raise ConfigError("Surge Smart groups must use '<region> Auto Smart' names")

    base_names = [entry.get("name") for entry in policies.get("base_groups", [])]
    if base_names != ["Proxy"]:
        raise ConfigError("Proxy must be the only base strategy group")

    expected_options = ["Proxy", "DIRECT"]
    for region in regions:
        expected_options.extend([region.get("auto_name"), region.get("manual_name")])
    if options != expected_options:
        raise ConfigError("Service options must expose each region's Auto and Manual groups")

    icon_config = config["icons"]
    icon_map = icon_config.get("icons")
    expected_icon_names = ["Proxy", *services]
    for region in regions:
        expected_icon_names.extend([region["auto_name"], region["manual_name"]])
    expected_icon_base = (
        f"{config['project']['project']['raw_base'].rstrip('/')}/assets/icons"
    )
    if icon_config.get("base") != expected_icon_base:
        raise ConfigError("Policy icons must use the project's self-hosted assets/icons base")
    if not isinstance(icon_map, dict) or list(icon_map) != expected_icon_names:
        raise ConfigError("Every visible icon-capable policy group must have one ordered icon")
    for name, value in icon_map.items():
        if not isinstance(value, str):
            raise ConfigError(f"Invalid icon path for {name}")
        path = PurePosixPath(value)
        if path.is_absolute() or ".." in path.parts or path.suffix.lower() != ".png":
            raise ConfigError(f"Invalid icon path for {name}: {value!r}")

    allowed_policies = set(services) | {"DIRECT", "Proxy"}
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
            if (source.get("kind") not in {"text", "git-history-cidr"}
                    or source.get("role") in {"validation-only", "full-only"}):
                raise ConfigError(f"Invalid routing source {source_id!r} in {rule_id}")
        required_attributes = entry.get("v2fly_require", [])
        if (not isinstance(required_attributes, list)
                or any(not isinstance(value, str) or not value or value.startswith("@")
                       for value in required_attributes)
                or (required_attributes and not entry.get("v2fly"))):
            raise ConfigError(f"Invalid v2fly attribute filter in {rule_id}")
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
        "Schwab",
    }
    configured_groups = set(services) | set(base_names) | set(options)
    if forbidden_groups.intersection(configured_groups):
        raise ConfigError("Removed policy groups must not be reintroduced")

    crypto = next((item for item in rulesets if item.get("id") == "crypto"), None)
    if not crypto:
        raise ConfigError("Crypto ruleset is required")
    if crypto.get("v2fly") != ["binance", "okx", "bybit"]:
        raise ConfigError("Crypto must contain only Binance, OKX, Bybit plus Bitget custom rules")

    schwab = next((item for item in rulesets if item.get("id") == "schwab"), None)
    if (not schwab
            or schwab.get("policy") != "Brokerage"
            or schwab.get("v2fly") != ["schwab"]
            or schwab.get("custom") != "rules/custom/schwab.list"):
        raise ConfigError("Schwab rules must remain intact and use the Brokerage policy")

    ai = next((item for item in rulesets if item.get("id") == "ai"), None)
    if not ai or "category-ai-cn" in ai.get("v2fly", []):
        raise ConfigError("Mainland AI must not be captured by the AI policy")

    ordered_ids = [entry["id"] for entry in rulesets]
    by_id = {entry["id"]: entry for entry in rulesets}
    for rule_id, source_id, main_id in (("apple-cn", "apple_cn", "apple"),):
        entry = by_id.get(rule_id, {})
        if (entry.get("policy") != "DIRECT" or text_source_ids(entry) != [source_id]
                or sources[source_id].get("format") != "dnsmasq"
                or entry.get("v2fly") != ["apple"]
                or entry.get("v2fly_require") != ["cn"]
                or entry.get("custom")):
            raise ConfigError(
                f"{rule_id} must combine the DIRECT dnsmasq source with v2fly apple@cn"
            )
        if ordered_ids[:4] != ["lan", "custom-direct", "custom-proxy", "apple-cn"]:
            raise ConfigError("apple-cn must remain after custom overrides and before services")
        if any(ordered_ids.index(rule_id) >= ordered_ids.index(later)
               for later in ("streaming", "developer", main_id)):
            raise ConfigError(f"{rule_id} must precede Streaming, Developer and {main_id}")
    # Resolving a Google domain through a Chinese DNS server is not a direct-
    # reachability guarantee. GoogleCN is therefore neither routed nor emitted.
    if ("google-cn" in by_id
            or "google_cn" in sources
            or "full_only_rulesets" in config["rulesets"]
            or any("google_cn" in text_source_ids(entry) for entry in rulesets)):
        raise ConfigError("GoogleCN and full-only rule artifacts must not be published")

    lan = by_id.get("lan", {})
    if ordered_ids[0] != "lan" or lan.get("policy") != "DIRECT" or not lan.get("no_resolve"):
        raise ConfigError("lan must be the first ruleset, DIRECT and no-resolve")
    brokerage = by_id.get("brokerage", {})
    brokerage_ip = by_id.get("brokerage-ip", {})
    if (brokerage.get("policy") != "Brokerage"
            or brokerage.get("v2fly") != ["futu"]
            or brokerage.get("custom") != "rules/custom/brokerage-domain.list"
            or brokerage.get("no_resolve")
            or text_source_ids(brokerage)
            or brokerage_ip.get("policy") != "Brokerage"
            or brokerage_ip.get("custom") != "rules/custom/brokerage-ip.list"
            or brokerage_ip.get("no_resolve") is not True
            or brokerage_ip.get("v2fly") or text_source_ids(brokerage_ip)):
        raise ConfigError(
            "Brokerage must keep Futu upstream domains separate from its IP rules; "
            "Tiger and Longbridge stay on tested custom domains only"
        )
    if ordered_ids[-5:] != [
        "brokerage-ip", "china", "proxy", "telegram-ip", "cn-ip"
    ]:
        raise ConfigError(
            "Brokerage IP must precede China and Proxy, followed only by Telegram and CN IP"
        )
    cn_ip = by_id.get("cn-ip", {})
    if (ordered_ids[-1] != "cn-ip" or cn_ip.get("policy") != "DIRECT"
            or text_source_ids(cn_ip) != ["cn_ip_primary"]
            or cn_ip.get("no_resolve") or cn_ip.get("v2fly") or cn_ip.get("custom")):
        raise ConfigError("cn-ip must be the last ruleset, DIRECT, using the primary CN source")
    primary_spec = sources["cn_ip_primary"]
    if (primary_spec.get("kind") != "git-history-cidr"
            or primary_spec.get("format") != "cidr"
            or primary_spec.get("ip_versions") != [4, 6]
            or primary_spec.get("repository") != "https://github.com/gaoyifan/china-operator-ip.git"
            or primary_spec.get("ref") != "ip-lists"
            or primary_spec.get("files") != {"ipv4": "china.txt", "ipv6": "china6.txt"}
            or primary_spec.get("window_days") != 5
            or primary_spec.get("minimum_presence_days") != 3
            or primary_spec.get("breaker_percent") != 1
            or primary_spec.get("license") != "MIT"):
        raise ConfigError("Primary CN IP source must be gaoyifan's 3-of-5 dual-stack window")
    reference_spec = sources.get("cn_ipv4_reference", {})
    if (reference_spec.get("kind") != "text"
            or reference_spec.get("format") != "cidr"
            or reference_spec.get("ip_version") != 4
            or reference_spec.get("role") != "validation-only"
            or "misakaio/chnroutes2" not in reference_spec.get("url", "")):
        raise ConfigError("CN IPv4 reference must be independent misakaio/chnroutes2 data")
    if "cn_ipv6_reference" in sources:
        raise ConfigError("No independent CN IPv6 reference is currently configured")
    check = config["sources"].get("cross_validation", {}).get("cn_ip", {})
    if (check.get("ruleset") != "cn-ip"
            or check.get("reference_sources") != ["cn_ipv4_reference"]
            or check.get("independent") is not True):
        raise ConfigError("misakaio must be the independent CN IPv4 reference")
    if text_source_ids(by_id["china"]):
        raise ConfigError("CN exceptions and CN IP must not be merged into China")
