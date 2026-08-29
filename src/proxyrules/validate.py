from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

from .cn_window import canonical_cidr_text, coverage_stats
from .filters import build_filters
from .render import CONFIG_FILENAMES, SUBSCRIPTION_PLACEHOLDER, rule_filename
from .v2fly import DomainListError, parse_cidr_text, parse_custom_file


class ValidationError(ValueError):
    pass


def _validate_policy_graph(policies: dict[str, Any]) -> None:
    base_names = {entry["name"] for entry in policies["base_groups"]}
    regions = policies["regions"]
    region_auto_names = {entry["auto_name"] for entry in regions}
    region_manual_names = {entry["manual_name"] for entry in regions}
    services = set(policies["service_groups"])
    all_groups = base_names | region_auto_names | region_manual_names | services

    graph: dict[str, set[str]] = {name: set() for name in all_groups}
    for service in services:
        graph[service].update(
            option for option in policies["service_options"] if option in all_groups
        )

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(name: str, chain: tuple[str, ...]) -> None:
        if name in visiting:
            raise ValidationError(f"Policy cycle: {' -> '.join((*chain, name))}")
        if name in visited:
            return
        visiting.add(name)
        for child in graph[name]:
            visit(child, (*chain, name))
        visiting.remove(name)
        visited.add(name)

    for group in sorted(graph):
        visit(group, ())


def _section(text: str, name: str) -> list[str]:
    lines: list[str] = []
    active = False
    for raw in text.splitlines():
        stripped = raw.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            active = stripped == f"[{name}]"
            continue
        if active and stripped and not stripped.startswith(("#", ";", "//")):
            lines.append(stripped)
    return lines


def _validate_subscription_template(target: str, text: str) -> None:
    active = [
        line for line in text.splitlines()
        if SUBSCRIPTION_PLACEHOLDER in line
        and not line.lstrip().startswith(("#", ";", "//"))
    ]
    if target == "shadowrocket":
        if SUBSCRIPTION_PLACEHOLDER in text:
            raise ValidationError("Shadowrocket must not contain subscription templates")
        return
    if len(active) != 1:
        raise ValidationError(f"{target}: exactly one active subscription placeholder is required")
    if any(f"{quote}{SUBSCRIPTION_PLACEHOLDER}{quote}" in text for quote in ('"', "'")):
        raise ValidationError(f"{target}: subscription placeholders must not be quoted")
    optional_templates = {
        "stash": f"  # Subscription2:\n  #   url: {SUBSCRIPTION_PLACEHOLDER}\n",
        "loon": f"# Subscription2 = {SUBSCRIPTION_PLACEHOLDER}\n",
        "surge": f"# Subscription2 = select,policy-path={SUBSCRIPTION_PLACEHOLDER},",
        "qx": f"# {SUBSCRIPTION_PLACEHOLDER}, tag=Subscription2,",
        "egern": f"    # - {SUBSCRIPTION_PLACEHOLDER}\n",
    }
    if optional_templates[target] not in text:
        raise ValidationError(f"{target}: a commented second subscription template is required")


def _active_rule_ids(root: Path, entries: list[dict[str, Any]]) -> list[str]:
    output: list[str] = []
    for entry in entries:
        if entry.get("omit_if_empty"):
            custom = entry.get("custom")
            if custom and not parse_custom_file(root / custom):
                continue
        output.append(entry["id"])
    return output


def validate_generated(root: Path, config: dict[str, Any]) -> None:
    _validate_policy_graph(config["policies"])
    dist = root / "dist"
    required = [
        *(dist / target / filename for target, filename in CONFIG_FILENAMES.items()),
        dist / "metadata.json",
        dist / "report.json",
        dist / "cn-ip-window.json",
        dist / "cn-ip-validation.json",
    ]
    missing = [str(path.relative_to(root)) for path in required if not path.is_file()]
    if missing:
        raise ValidationError(f"Missing generated files: {', '.join(missing)}")

    texts = {target: (dist / target / filename).read_text(encoding="utf-8")
             for target, filename in CONFIG_FILENAMES.items()}
    stash = yaml.safe_load(texts["stash"])
    expected_groups = (
        {item["name"] for item in config["policies"]["base_groups"]}
        | {item["auto_name"] for item in config["policies"]["regions"]}
        | {item["manual_name"] for item in config["policies"]["regions"]}
        | set(config["policies"]["service_groups"])
    )
    stash_groups = {entry["name"] for entry in stash.get("proxy-groups", [])}
    if stash_groups != expected_groups:
        raise ValidationError("Stash strategy groups do not match the policy manifest")

    rulesets = config["rulesets"]["rulesets"]
    expected_rule_ids = _active_rule_ids(root, rulesets)
    expected_policies = {entry["id"]: entry["policy"] for entry in rulesets}
    if list(stash.get("rule-providers", {})) != expected_rule_ids:
        raise ValidationError("Stash rule-provider order differs from the manifest")
    if stash.get("rules", [])[-2:] != ["GEOIP,CN,DIRECT", "MATCH,Final"]:
        raise ValidationError("Stash final routing rules are invalid")

    loon_text = texts["loon"]
    shadow_text = texts["shadowrocket"]
    loon_groups = {line.split("=", 1)[0].strip() for line in _section(loon_text, "Proxy Group")}
    shadow_groups = {
        line.split("=", 1)[0].strip()
        for line in _section(shadow_text, "Proxy Group")
    }
    if loon_groups != expected_groups or shadow_groups != expected_groups:
        raise ValidationError("Loon or Shadowrocket strategy groups differ from the manifest")

    for service in config["policies"]["service_groups"]:
        expected_default = f"{service} = select,Manual,"
        if expected_default not in loon_text or expected_default not in shadow_text:
            raise ValidationError(f"{service} must default to Manual")

    policies = config["policies"]
    expected_order = ["Manual", *policies["service_groups"], *[
        name for region in policies["regions"]
        for name in (region["auto_name"], region["manual_name"])
    ]]
    filters = build_filters(policies)
    options = list(policies["service_options"])
    stash_by_name = {group["name"]: group for group in stash["proxy-groups"]}
    if list(stash_by_name) != expected_order:
        raise ValidationError("Stash groups must be base, services, then regions")
    if (list(stash.get("proxy-providers", {})) != ["Subscription1"]
            or stash["proxy-providers"]["Subscription1"]["url"] != SUBSCRIPTION_PLACEHOLDER):
        raise ValidationError("Stash must contain the public subscription placeholder")
    if not stash_by_name["Manual"].get("include-all"):
        raise ValidationError("Stash Manual must include subscription nodes")
    for service in policies["service_groups"]:
        if stash_by_name[service].get("proxies") != options:
            raise ValidationError(f"Stash {service} options differ from the manifest")

    for target in ("loon", "shadowrocket", "surge"):
        groups = {line.split("=", 1)[0].strip(): line.split("=", 1)[1].strip()
                  for line in _section(texts[target], "Proxy Group")}
        target_order = ["Subscription1", *expected_order] if target == "surge" else expected_order
        if list(groups) != target_order:
            raise ValidationError(f"{target}: invalid group order or missing groups")
        for service in policies["service_groups"]:
            if not groups[service].startswith(f"select,{','.join(options)}"):
                raise ValidationError(f"{target}: {service} must default to Manual")
    if _section(loon_text, "Remote Proxy") != [f"Subscription1 = {SUBSCRIPTION_PLACEHOLDER}"]:
        raise ValidationError("Loon subscription template must be enabled")
    surge_groups = {
        line.split("=", 1)[0].strip(): line.split("=", 1)[1].strip()
        for line in _section(texts["surge"], "Proxy Group")
    }
    node_interval = config["project"]["updates"]["node_interval"]
    if surge_groups["Subscription1"] != (
        f"select,policy-path={SUBSCRIPTION_PLACEHOLDER},update-interval={node_interval},hidden=true"
    ):
        raise ValidationError("Surge must load subscriptions through a hidden source group")
    if surge_groups["Manual"] != "select,include-other-group=Subscription1,include-all-proxies=true":
        raise ValidationError("Surge Manual must expand the hidden subscription group")
    for region in policies["regions"]:
        for name, group_type in ((region["auto_name"], "url-test"), (region["manual_name"], "select")):
            group = stash_by_name[name]
            if (group["type"] != group_type or not group.get("include-all")
                    or group.get("filter") != filters["regions"][region["name"]]):
                raise ValidationError(f"Invalid Stash region group: {name}")
            surge_line = next(line for line in _section(texts["surge"], "Proxy Group")
                              if line.startswith(f"{name} = "))
            if f"{name} = {group_type},include-other-group=Manual," not in surge_line:
                raise ValidationError(f"Surge {name} must expand subscription nodes")

    egern = yaml.safe_load(texts["egern"])
    egern_groups = {next(iter(group.values()))["name"]: group for group in egern["policy_groups"]}
    if list(egern_groups) != expected_order:
        raise ValidationError("Egern group order differs from the manifest")
    if egern_groups["Manual"]["select"]["urls"] != [SUBSCRIPTION_PLACEHOLDER]:
        raise ValidationError("Egern subscription template must be enabled")
    for service in policies["service_groups"]:
        if egern_groups[service]["select"]["policies"] != options:
            raise ValidationError(f"Egern {service} options differ from the manifest")
    for region in policies["regions"]:
        for name, kind in ((region["auto_name"], "auto_test"), (region["manual_name"], "select")):
            group = egern_groups[name][kind]
            if (group.get("policies") != ["Manual"] or not group.get("flatten")
                    or group.get("filter") != filters["regions"][region["name"]]):
                raise ValidationError(f"Egern {name} must flatten and filter nodes")
    if egern["rules"][-2:] != [{"geoip": {"match": "CN", "policy": "DIRECT"}},
                               {"default": {"policy": "Final"}}]:
        raise ValidationError("Egern final routing rules are invalid")
    if "auto_update" in egern:
        raise ValidationError("Egern must not automatically replace the local profile")

    qx_groups = {}
    for line in _section(texts["qx"], "policy"):
        kind, value = line.split("=", 1)
        name = value.split(",", 1)[0].strip()
        qx_groups[name] = (kind.strip(), value.strip())
    if list(qx_groups) != expected_order:
        raise ValidationError("QX group order differs from the manifest")
    qx_options = ", ".join("direct" if option == "DIRECT" else option for option in options)
    for service in policies["service_groups"]:
        kind, value = qx_groups[service]
        if kind != "static" or not value.startswith(f"{service}, {qx_options}"):
            raise ValidationError(f"QX {service} must default to Manual")
    for region in policies["regions"]:
        for name, kind in ((region["auto_name"], "url-latency-benchmark"), (region["manual_name"], "static")):
            actual, value = qx_groups[name]
            if actual != kind or f"server-tag-regex={filters['regions'][region['name']]}" not in value:
                raise ValidationError(f"Invalid QX region group: {name}")
    if _section(texts["qx"], "server_remote") != [
        f"{SUBSCRIPTION_PLACEHOLDER}, tag=Subscription1, update-interval={node_interval}, enabled=true"
    ]:
        raise ValidationError("QX subscription template must be enabled")
    if texts["qx"].index("\n[server_remote]\n") < texts["qx"].index("\n[policy]\n"):
        raise ValidationError("QX subscription section must remain after policy groups")
    if _section(texts["qx"], "filter_local")[-2:] != ["geoip,cn,direct", "final,Final"]:
        raise ValidationError("QX final routing rules are invalid")

    raw_base = config["project"]["project"]["raw_base"].rstrip("/")
    for target, text in texts.items():
        _validate_subscription_template(target, text)
        if "# Last updated: " not in text:
            raise ValidationError(f"{target}: missing update timestamp")
        if target == "stash":
            actual_urls = [entry["url"] for entry in stash["rule-providers"].values()]
        elif target == "egern":
            actual_urls = [entry["rule_set"]["match"] for entry in egern["rules"] if "rule_set" in entry]
        elif target == "qx":
            actual_urls = [line.split(",", 1)[0] for line in _section(text, "filter_remote")]
        elif target == "loon":
            actual_urls = [line.split(",", 1)[0] for line in _section(text, "Remote Rule")]
        else:
            actual_urls = [line.split(",")[1] for line in _section(text, "Rule") if line.startswith("RULE-SET,")]
        expected_urls = [f"{raw_base}/dist/{target}/rules/{rule_filename(target, rule_id)}"
                         for rule_id in expected_rule_ids]
        if actual_urls != expected_urls:
            raise ValidationError(f"{target}: remote rule URLs or order differ from the manifest")
        expected_policy_list = [expected_policies[rule_id] for rule_id in expected_rule_ids]
        if target == "stash":
            expected_routes = [f"RULE-SET,{rule_id},{expected_policies[rule_id]}"
                               for rule_id in expected_rule_ids]
            if stash["rules"] != expected_routes + ["GEOIP,CN,DIRECT", "MATCH,Final"]:
                raise ValidationError("Stash routing policies or priority differ from the manifest")
        elif target == "egern":
            actual_policies = [entry["rule_set"]["policy"] for entry in egern["rules"] if "rule_set" in entry]
            if actual_policies != expected_policy_list:
                raise ValidationError("Egern routing policies differ from the manifest")
        elif target in {"surge", "shadowrocket"}:
            actual_policies = [line.split(",")[2].strip() for line in _section(text, "Rule")
                               if line.startswith("RULE-SET,")]
            if actual_policies != expected_policy_list:
                raise ValidationError(f"{target}: routing policies differ from the manifest")
            if _section(text, "Rule")[-2:] != ["GEOIP,CN,DIRECT", "FINAL,Final"]:
                raise ValidationError(f"{target}: final routing rules are invalid")
        else:
            section = "Remote Rule" if target == "loon" else "filter_remote"
            key = "policy" if target == "loon" else "force-policy"
            actual_policies = []
            for line in _section(text, section):
                settings = dict(part.strip().split("=", 1) for part in line.split(",")[1:] if "=" in part)
                settings = {name.strip(): value.strip() for name, value in settings.items()}
                actual_policies.append(settings.get(key))
            expected_native = ["direct" if target == "qx" and p == "DIRECT" else p
                               for p in expected_policy_list]
            if actual_policies != expected_native:
                raise ValidationError(f"{target}: routing policies differ from the manifest")
            if target == "loon" and _section(text, "Rule") != ["GEOIP,CN,DIRECT", "FINAL,Final"]:
                raise ValidationError("Loon local rules must only contain final routing")
        for rule_id in expected_rule_ids:
            path = dist / target / "rules" / rule_filename(target, rule_id)
            if not path.is_file():
                raise ValidationError(f"Missing referenced rule file: {path}")
            if target == "egern" and not isinstance(yaml.safe_load(path.read_text()), dict):
                raise ValidationError(f"Invalid Egern rule set: {path}")

    generated_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in dist.rglob("*")
        if path.is_file() and path.suffix in {".yaml", ".conf", ".list"}
    )
    if "REJECT" in generated_text.upper():
        raise ValidationError("Generated routing must not contain a REJECT policy")

    forbidden_ids = {"ads", "adblock", "advertising", "reject", "game-download", "download"}
    if forbidden_ids.intersection(expected_rule_ids):
        raise ValidationError("Ad blocking and special download routing are out of scope")

    metadata = json.loads((dist / "metadata.json").read_text())
    window = json.loads((dist / "cn-ip-window.json").read_text())
    comparison = json.loads((dist / "cn-ip-validation.json").read_text())
    if (comparison.get("primary_ruleset") != "cn-ip" or comparison.get("independent") is not True
            or comparison.get("status") not in {"match", "differs"}):
        raise ValidationError("Invalid CN IP comparison report")
    comparison_sources = comparison.get("sources", {})
    for role, source_ids in (("primary", ["cn_ip_primary"]),
                             ("reference", ["cn_ipv4_reference"])):
        if comparison_sources.get(role) != {key: metadata["sources"][key] for key in source_ids}:
            raise ValidationError("CN IP comparison source digests differ from build metadata")
    primary_metadata = metadata["sources"]["cn_ip_primary"]
    snapshots = window.get("snapshots", [])
    breaker = window.get("breaker", {})
    try:
        published_values = [
            line.split(",", 2)[1]
            for line in (dist / "stash/rules/cn-ip.list").read_text(encoding="utf-8").splitlines()
            if line.startswith(("IP-CIDR,", "IP-CIDR6,"))
        ]
        published_rules = tuple(
            parse_cidr_text("\n".join(published_values), "published_cn_ip")
        )
    except (OSError, DomainListError, IndexError) as exc:
        raise ValidationError(f"Invalid published CN IP output: {exc}") from exc
    published_digest = hashlib.sha256(
        canonical_cidr_text(published_rules).encode("utf-8")
    ).hexdigest()
    window_output = window.get("output", {})
    breaker_state_valid = (
        (breaker.get("exceeded") is False and breaker.get("accepted") is False)
        or (breaker.get("exceeded") is True and breaker.get("accepted") is True)
    )
    if (window.get("source", {}).get("id") != "cn_ip_primary"
            or window.get("window") != {
                "snapshot_days": 7,
                "minimum_presence_days": 5,
                "selection": "latest commit for each distinct UTC date",
            }
            or len(snapshots) != 7
            or len({snapshot.get("date") for snapshot in snapshots}) != 7
            or window_output.get("sha256") != primary_metadata.get("sha256")
            or window_output.get("sha256") != published_digest
            or window_output.get("coverage") != coverage_stats(published_rules)
            or primary_metadata.get("window_report") != "cn-ip-window.json"
            or breaker.get("threshold_percent") != 1.0
            or not breaker_state_valid):
        raise ValidationError("Invalid CN IP stable-window report")
    cn_metadata = next(entry for entry in metadata["rulesets"] if entry["id"] == "cn-ip")
    for version, kind in ((4, "ipcidr"), (6, "ipcidr6")):
        family = comparison.get("families", {}).get(f"ipv{version}", {})
        if not family.get("primary_rule_count") or family["primary_rule_count"] != cn_metadata["kinds"].get(kind):
            raise ValidationError(f"CN IPv{version} rules differ from the comparison report")
        expected_reference = version == 4
        if family.get("reference_available") is not expected_reference:
            raise ValidationError(f"Invalid CN IPv{version} reference availability")
