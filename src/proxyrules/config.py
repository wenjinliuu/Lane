from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


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
    for entry in rulesets:
        rule_id = entry.get("id")
        if not rule_id or rule_id in ids:
            raise ConfigError(f"Invalid or duplicate ruleset id: {rule_id!r}")
        ids.add(rule_id)
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
