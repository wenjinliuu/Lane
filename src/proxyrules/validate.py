from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

from .cn_window import canonical_cidr_text, coverage_stats
from .filters import build_filters
from .render import (
    CONFIG_FILENAMES,
    QX_EXCLUDED_ROUTES,
    RULES_DIR,
    SHADOWROCKET_MANUAL_POLICY,
    STASH_BEHAVIOR_ORDER,
    STASH_PROVIDER_NAME,
    SUBSCRIPTION_PLACEHOLDER,
    rule_filename,
    shadowrocket_options,
    stash_provider_id,
)
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
    # QX validates every [server_remote] entry as a resource address, so both of its
    # templates stay commented out and an unedited profile still imports.
    expected_active = 0 if target == "qx" else 1
    if len(active) != expected_active:
        raise ValidationError(
            f"{target}: exactly {expected_active} active subscription placeholder(s) required"
        )
    if any(f"{quote}{SUBSCRIPTION_PLACEHOLDER}{quote}" in text for quote in ('"', "'")):
        raise ValidationError(f"{target}: subscription placeholders must not be quoted")
    first_templates = {
        "qx": f"# {SUBSCRIPTION_PLACEHOLDER}, tag=Subscription1,",
    }
    optional_templates = {
        "stash": f"  # Subscription2:\n  #   url: {SUBSCRIPTION_PLACEHOLDER}\n",
        "loon": f"# Subscription2 = {SUBSCRIPTION_PLACEHOLDER}\n",
        "surge": f"# Subscription2 = select,policy-path={SUBSCRIPTION_PLACEHOLDER},",
        "qx": f"# {SUBSCRIPTION_PLACEHOLDER}, tag=Subscription2,",
        "egern": f"    # - {SUBSCRIPTION_PLACEHOLDER}\n",
    }
    if target in first_templates and first_templates[target] not in text:
        raise ValidationError(f"{target}: a commented first subscription template is required")
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


def _active_generated_lines(path: Path) -> list[str]:
    return [
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#")
    ]


def _stash_payloads_from_classical(path: Path) -> dict[str, list[str]]:
    payloads: dict[str, list[str]] = {
        behavior: [] for behavior in STASH_BEHAVIOR_ORDER
    }
    for line in _active_generated_lines(path):
        kind, separator, remainder = line.partition(",")
        if not separator:
            raise ValidationError(f"Malformed canonical Stash rule: {path}: {line}")
        if kind == "DOMAIN":
            payloads["domain"].append(remainder)
        elif kind == "DOMAIN-SUFFIX":
            payloads["domain"].append(f"+.{remainder}")
        elif kind in {"IP-CIDR", "IP-CIDR6"}:
            payloads["ipcidr"].append(remainder.split(",", 1)[0])
        else:
            payloads["classical"].append(line)
    return payloads


def _validate_stash_specialized_files(
    dist: Path,
    directory: str,
    rule_ids: list[str],
) -> list[tuple[str, str, str]]:
    rules_dir = dist / "stash" / directory
    expected_names: set[str] = set()
    parts: list[tuple[str, str, str]] = []
    for rule_id in rule_ids:
        canonical = rules_dir / f"{rule_id}.list"
        if not canonical.is_file():
            raise ValidationError(f"Missing canonical Stash rule file: {canonical}")
        expected_names.add(canonical.name)
        payloads = _stash_payloads_from_classical(canonical)
        for behavior in STASH_BEHAVIOR_ORDER:
            expected_payload = payloads[behavior]
            if not expected_payload:
                continue
            provider_id = stash_provider_id(rule_id, behavior)
            specialized = rules_dir / f"{provider_id}.list"
            expected_names.add(specialized.name)
            if not specialized.is_file():
                raise ValidationError(
                    f"Missing specialized Stash rule file: {specialized}"
                )
            if _active_generated_lines(specialized) != expected_payload:
                raise ValidationError(
                    f"Stash {provider_id} payload differs from canonical semantics"
                )
            parts.append((rule_id, behavior, provider_id))

    actual_names = {
        path.name for path in rules_dir.iterdir()
        if path.is_file() and path.suffix == ".list"
    }
    if actual_names != expected_names:
        raise ValidationError(
            f"Stash {directory} contains missing or stale generated rule files"
        )
    return parts


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
    stash_parts = _validate_stash_specialized_files(
        dist, RULES_DIR, expected_rule_ids
    )
    expected_stash_provider_ids = [part[2] for part in stash_parts]
    if list(stash.get("rule-providers", {})) != expected_stash_provider_ids:
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
    # Shadowrocket routes Manual to its built-in PROXY policy, so it defines no
    # Manual group of its own.
    shadow_expected_groups = expected_groups - {"Manual"}
    if loon_groups != expected_groups or shadow_groups != shadow_expected_groups:
        raise ValidationError("Loon or Shadowrocket strategy groups differ from the manifest")
    if "Manual" in shadow_groups or SHADOWROCKET_MANUAL_POLICY not in shadow_text:
        raise ValidationError("Shadowrocket must follow the built-in PROXY policy")

    for service in config["policies"]["service_groups"]:
        if f"{service} = select,Manual," not in loon_text:
            raise ValidationError(f"{service} must default to Manual")
        if f"{service} = select,{SHADOWROCKET_MANUAL_POLICY}," not in shadow_text:
            raise ValidationError(f"{service} must default to PROXY on Shadowrocket")

    policies = config["policies"]
    expected_order = ["Manual", *policies["service_groups"], *[
        name for region in policies["regions"]
        for name in (region["auto_name"], region["manual_name"])
    ]]
    icon_config = config["icons"]
    icon_base = icon_config["base"].rstrip("/")
    icon_urls = {
        name: f"{icon_base}/{relative}"
        for name, relative in icon_config["icons"].items()
    }
    for name, relative in icon_config["icons"].items():
        path = root / "assets/icons" / relative
        try:
            data = path.read_bytes()
        except OSError as exc:
            raise ValidationError(f"Missing self-hosted icon for {name}: {path}") from exc
        if (data[:8] != b"\x89PNG\r\n\x1a\n"
                or len(data) < 24
                or int.from_bytes(data[16:20], "big") != 144
                or int.from_bytes(data[20:24], "big") != 144):
            raise ValidationError(f"Policy icon must be a 144x144 PNG: {path}")
    for target in ("stash", "loon", "qx", "egern"):
        for name, url in icon_urls.items():
            if url not in texts[target]:
                raise ValidationError(f"{target}: missing self-hosted icon for {name}")
    for name, url in icon_urls.items():
        # Surge names its region autos "XX Auto Smart" and reuses the Auto icon,
        # so only the client-neutral icon URLs have to appear.
        if url not in texts["surge"]:
            raise ValidationError(f"surge: missing self-hosted icon for {name}")
    if icon_base in texts["shadowrocket"]:
        raise ValidationError(
            "shadowrocket: icons must remain omitted; it has no policy-group icon parameter"
        )
    if any("raw.githubusercontent.com/Koolson/Qure" in text for text in texts.values()):
        raise ValidationError("Generated profiles must not depend on the external Qure URL")

    filters = build_filters(policies)
    options = list(policies["service_options"])
    auto_names = [region["auto_name"] for region in policies["regions"]]
    stash_by_name = {group["name"]: group for group in stash["proxy-groups"]}
    if list(stash_by_name) != expected_order:
        raise ValidationError("Stash groups must be base, services, then regions")
    for name in expected_order:
        if stash_by_name[name].get("icon") != icon_urls[name]:
            raise ValidationError(f"Stash {name} uses the wrong self-hosted icon")
    if (list(stash.get("proxy-providers", {})) != ["Subscription1"]
            or stash["proxy-providers"]["Subscription1"]["url"] != SUBSCRIPTION_PLACEHOLDER):
        raise ValidationError("Stash must contain the public subscription placeholder")
    if (stash_by_name["Manual"].get("use") != [STASH_PROVIDER_NAME]
            or stash_by_name["Manual"].get("include-all")
            or stash_by_name["Manual"].get("proxies") != auto_names):
        raise ValidationError("Stash Manual must expose regional Auto groups and nodes")
    for service in policies["service_groups"]:
        if stash_by_name[service].get("proxies") != options:
            raise ValidationError(f"Stash {service} options differ from the manifest")

    loon_groups_by_name = {
        line.split("=", 1)[0].strip(): line.split("=", 1)[1].strip()
        for line in _section(loon_text, "Proxy Group")
    }
    if list(loon_groups_by_name) != expected_order:
        raise ValidationError("loon: invalid group order or missing groups")
    if not loon_groups_by_name["Manual"].startswith(
        f"select,{','.join(auto_names)},Manual Nodes,"
    ):
        raise ValidationError("loon: Manual must expose regional Auto groups and nodes")
    for service in policies["service_groups"]:
        if not loon_groups_by_name[service].startswith(f"select,{','.join(options)}"):
            raise ValidationError(f"loon: {service} must default to Manual")

    shadow_groups_by_name = {
        line.split("=", 1)[0].strip(): line.split("=", 1)[1].strip()
        for line in _section(shadow_text, "Proxy Group")
    }
    shadow_order = [name for name in expected_order if name != "Manual"]
    if list(shadow_groups_by_name) != shadow_order:
        raise ValidationError("shadowrocket: invalid group order or missing groups")
    shadow_options = shadowrocket_options(policies)
    for service in policies["service_groups"]:
        expected = (
            f"select,{','.join(shadow_options)},"
            f"policy-select-name={SHADOWROCKET_MANUAL_POLICY}"
        )
        if shadow_groups_by_name[service] != expected:
            raise ValidationError(f"shadowrocket: {service} options differ from the manifest")
    for region in policies["regions"]:
        # url-test is Shadowrocket's own automatic type; nothing else turns it on.
        if not shadow_groups_by_name[region["auto_name"]].startswith("url-test,"):
            raise ValidationError(
                f"shadowrocket: {region['auto_name']} must stay a url-test group"
            )
    if _section(loon_text, "Remote Proxy") != [f"Subscription1 = {SUBSCRIPTION_PLACEHOLDER}"]:
        raise ValidationError("Loon subscription template must be enabled")
    surge_groups = {
        line.split("=", 1)[0].strip(): line.split("=", 1)[1].strip()
        for line in _section(texts["surge"], "Proxy Group")
    }
    smart_names = [region["surge_smart_name"] for region in policies["regions"]]
    surge_order = ["Subscription1", "Node Pool", "Manual", *policies["service_groups"], *[
        name for region in policies["regions"]
        for name in (region["surge_smart_name"], region["manual_name"])
    ]]
    if list(surge_groups) != surge_order:
        raise ValidationError("surge: invalid hidden pool, service or region group order")
    node_interval = config["project"]["updates"]["node_interval"]
    if surge_groups["Subscription1"] != (
        f"select,policy-path={SUBSCRIPTION_PLACEHOLDER},update-interval={node_interval},hidden=true"
    ):
        raise ValidationError("Surge must load subscriptions through a hidden source group")
    if surge_groups["Node Pool"] != (
        "select,include-other-group=Subscription1,include-all-proxies=true,hidden=true"
    ):
        raise ValidationError("Surge Node Pool must expand raw proxies and remain hidden")
    # Surge reads icon-url on every visible policy group; hidden groups carry none.
    def surge_icon(name: str) -> str:
        return f",icon-url={icon_urls[name]}"

    if surge_groups["Manual"] != (
        f"select,{','.join(smart_names)},include-other-group=Node Pool"
        f"{surge_icon('Manual')}"
    ):
        raise ValidationError("Surge Manual must expose Smart groups and raw nodes")
    surge_options = ["Manual", "DIRECT"]
    for region in policies["regions"]:
        surge_options.extend([region["surge_smart_name"], region["manual_name"]])
    for service in policies["service_groups"]:
        expected = f"select,{','.join(surge_options)}{surge_icon(service)}"
        if surge_groups[service] != expected:
            raise ValidationError(f"Surge {service} options differ from the Smart manifest")
    for region in policies["regions"]:
        for name, group_type in ((region["auto_name"], "url-test"), (region["manual_name"], "select")):
            group = stash_by_name[name]
            if (group["type"] != group_type or not group.get("include-all")
                    or group.get("filter") != filters["regions"][region["name"]]):
                raise ValidationError(f"Invalid Stash region group: {name}")
        suffix = (
            f'include-other-group=Node Pool,policy-regex-filter="'
            f'{filters["regions"][region["name"]]}"'
        )
        # The Smart group reuses the region Auto icon so icons.yaml stays client neutral.
        if surge_groups[region["surge_smart_name"]] != (
            f"smart,{suffix}{surge_icon(region['auto_name'])}"
        ):
            raise ValidationError(f"Surge {region['surge_smart_name']} must be a Smart group")
        if surge_groups[region["manual_name"]] != (
            f"select,{suffix}{surge_icon(region['manual_name'])}"
        ):
            raise ValidationError(f"Surge {region['manual_name']} must expand Node Pool")

    egern = yaml.safe_load(texts["egern"])
    egern_groups = {next(iter(group.values()))["name"]: group for group in egern["policy_groups"]}
    if list(egern_groups) != ["Node Pool", *expected_order]:
        raise ValidationError("Egern group order differs from the manifest")
    egern_pool = egern_groups["Node Pool"]["select"]
    egern_manual = egern_groups["Manual"]["select"]
    if (egern_pool.get("urls") != [SUBSCRIPTION_PLACEHOLDER]
            or egern_pool.get("hidden") is not True):
        raise ValidationError("Egern Node Pool must load the hidden subscription source")
    if (egern_manual.get("urls") != [SUBSCRIPTION_PLACEHOLDER]
            or egern_manual.get("policies") != auto_names):
        raise ValidationError("Egern Manual must expose regional Auto groups and nodes")
    for service in policies["service_groups"]:
        if egern_groups[service]["select"]["policies"] != options:
            raise ValidationError(f"Egern {service} options differ from the manifest")
    for region in policies["regions"]:
        for name, kind in ((region["auto_name"], "auto_test"), (region["manual_name"], "select")):
            group = egern_groups[name][kind]
            if (group.get("policies") != ["Node Pool"] or not group.get("flatten")
                    or group.get("filter") != filters["regions"][region["name"]]):
                raise ValidationError(f"Egern {name} must flatten and filter Node Pool")
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
    qx_manual_kind, qx_manual_value = qx_groups["Manual"]
    qx_manual_prefix = f"Manual, {', '.join(auto_names)}, server-tag-regex=.+"
    if qx_manual_kind != "static" or not qx_manual_value.startswith(qx_manual_prefix):
        raise ValidationError("QX Manual must expose regional Auto groups and nodes")
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
    # QX documents excluded_routes with IPv4 ranges only, so the IPv6 multicast entry
    # the other clients carry must not leak into this profile.
    qx_routes = f"excluded_routes = {', '.join(QX_EXCLUDED_ROUTES)}"
    if qx_routes not in texts["qx"].splitlines():
        raise ValidationError("QX excluded_routes must list the IPv4 ranges only")
    # Both QX templates stay commented: QX rejects a profile whose [server_remote]
    # entries are not valid resource addresses, and the placeholder is not one.
    if _section(texts["qx"], "server_remote"):
        raise ValidationError("QX subscription templates must stay commented out")
    for tag in ("Subscription1", "Subscription2"):
        template = (
            f"# {SUBSCRIPTION_PLACEHOLDER}, tag={tag}, "
            f"update-interval={node_interval}, enabled=true"
        )
        if template not in texts["qx"]:
            raise ValidationError(f"QX {tag} template is missing")
    if texts["qx"].index("\n[server_remote]\n") < texts["qx"].index("\n[policy]\n"):
        raise ValidationError("QX subscription section must remain after policy groups")
    if _section(texts["qx"], "filter_local")[-2:] != ["geoip,cn,direct", "final,Final"]:
        raise ValidationError("QX final routing rules are invalid")

    raw_base = config["project"]["project"]["raw_base"].rstrip("/")
    rule_interval = config["project"]["updates"]["rule_interval"]
    entries_by_id = {entry["id"]: entry for entry in rulesets}
    expected_stash_providers: dict[str, dict[str, Any]] = {}
    expected_stash_routes: list[str] = []
    for rule_id, behavior, provider_id in stash_parts:
        expected_stash_providers[provider_id] = {
            "type": "http",
            "behavior": behavior,
            "format": "text",
            "url": (
                f"{raw_base}/dist/stash/{RULES_DIR}/{provider_id}.list"
            ),
            "path": f"./rulesets/{provider_id}.list",
            "interval": rule_interval,
        }
        entry = entries_by_id[rule_id]
        no_resolve = (
            ",no-resolve"
            if behavior == "ipcidr" and entry.get("no_resolve") is True
            else ""
        )
        expected_stash_routes.append(
            f"RULE-SET,{provider_id},{entry['policy']}{no_resolve}"
        )
    if stash.get("rule-providers") != expected_stash_providers:
        raise ValidationError("Stash rule-provider settings differ from generated payloads")
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
        if target == "stash":
            expected_urls = [
                expected_stash_providers[provider_id]["url"]
                for provider_id in expected_stash_provider_ids
            ]
        else:
            expected_urls = [
                f"{raw_base}/dist/{target}/{RULES_DIR}/"
                f"{rule_filename(target, rule_id)}"
                for rule_id in expected_rule_ids
            ]
        if actual_urls != expected_urls:
            raise ValidationError(f"{target}: remote rule URLs or order differ from the manifest")
        expected_policy_list = [expected_policies[rule_id] for rule_id in expected_rule_ids]
        if target == "stash":
            if stash["rules"] != expected_stash_routes + [
                "GEOIP,CN,DIRECT", "MATCH,Final"
            ]:
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
            path = dist / target / RULES_DIR / rule_filename(target, rule_id)
            if not path.is_file():
                raise ValidationError(f"Missing referenced rule file: {path}")
            if target == "egern" and not isinstance(yaml.safe_load(path.read_text()), dict):
                raise ValidationError(f"Invalid Egern rule set: {path}")
        for legacy_name in ("rules-full", "rules-profile"):
            if (dist / target / legacy_name).exists():
                raise ValidationError(
                    f"{target}: legacy {legacy_name} directory must be removed"
                )

    udp_fallback = {
        "loon": "udp-fallback-mode = REJECT",
        "shadowrocket": "udp-policy-not-supported-behaviour = REJECT",
        "surge": "udp-policy-not-supported-behaviour = REJECT",
        "qx": "fallback_udp_policy = reject",
    }
    for target, setting in udp_fallback.items():
        if texts[target].count(setting) != 1:
            raise ValidationError(f"{target}: invalid UDP unsupported-policy fallback")
    loon_general = _section(texts["loon"], "General")
    if ("ip-mode = ipv4-only" not in loon_general
            or any(line.startswith("ipv6 =") for line in loon_general)):
        raise ValidationError("Loon must use the current IPv4-only syntax")
    forbidden_udp_controls = (
        "block-quic", "udp_drop_list", "disable-udp-ports"
    )
    if any(
        value in text.lower()
        for text in texts.values()
        for value in forbidden_udp_controls
    ):
        raise ValidationError("Global QUIC blocking is outside Lane's UDP fallback scope")
    allowed_reject_lines = {setting.upper() for setting in udp_fallback.values()}
    for path in dist.rglob("*"):
        if not path.is_file() or path.suffix not in {".yaml", ".conf", ".list"}:
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if (stripped and not stripped.startswith(("#", ";", "//"))
                    and "REJECT" in stripped.upper()
                    and stripped.upper() not in allowed_reject_lines):
                raise ValidationError(
                    f"Generated routing contains an unexpected REJECT policy: {path}"
                )

    forbidden_ids = {"ads", "adblock", "advertising", "reject", "game-download", "download"}
    if forbidden_ids.intersection(expected_rule_ids):
        raise ValidationError("Ad blocking and special download routing are out of scope")

    metadata = json.loads((dist / "metadata.json").read_text())
    report = json.loads((dist / "report.json").read_text())
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
            for line in (
                dist / "stash" / RULES_DIR / "cn-ip.list"
            ).read_text(encoding="utf-8").splitlines()
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
        (breaker.get("exceeded") is False
         and breaker.get("accepted") is False
         and breaker.get("approval_sha256") is None)
        or (breaker.get("exceeded") is True
            and breaker.get("accepted") is True
            and breaker.get("approval_sha256") == window_output.get("sha256"))
    )
    metadata_ids = [entry.get("id") for entry in metadata.get("rulesets", [])]
    exact_removed_total = sum(
        entry.get("exact_duplicates_removed", -1)
        for entry in metadata.get("rulesets", [])
    )
    candidate_total = sum(
        entry.get("redundancy_audit", {}).get("total_candidates", -1)
        for entry in metadata.get("rulesets", [])
    )
    optimization = metadata.get("rule_optimization", {})
    redundancy = metadata.get("redundancy_audit", {})
    if (metadata.get("schema") != 3
            or metadata.get("artifacts") != {
                "rules": RULES_DIR,
                "default_profiles_use": RULES_DIR,
                "deduplication": "exact-only",
            }
            or metadata_ids != expected_rule_ids
            or "full_only_rulesets" in metadata
            or "google_cn" in metadata.get("sources", {})
            or optimization != {
                "exact_duplicate_removal": {
                    "enabled": True,
                    "removed": exact_removed_total,
                },
                "parent_suffix_removal": False,
                "cross_ruleset_residual_removal": False,
            }
            or redundancy.get("mode") != "report-only"
            or redundancy.get("total_candidates") != candidate_total
            or report.get("schema") != 3
            or set(report.get("unsupported_rules", {})) != set(CONFIG_FILENAMES)):
        raise ValidationError("Invalid single-tier rule artifact metadata")
    metadata_by_id = {entry["id"]: entry for entry in metadata["rulesets"]}
    for rule_id in expected_rule_ids:
        entry = metadata_by_id[rule_id]
        rule_count = sum(
            1 for line in (
                dist / "stash" / RULES_DIR / f"{rule_id}.list"
            ).read_text().splitlines() if line and not line.startswith("#")
        )
        audit = entry.get("redundancy_audit", {})
        audit_sum = sum(
            audit.get(key, -1)
            for key in (
                "within_parent_suffix_candidates",
                "previous_ruleset_exact_candidates",
                "previous_ruleset_parent_suffix_candidates",
            )
        )
        if (entry.get("rules") != rule_count
                or entry.get("exact_duplicates_removed", -1) < 0
                or audit.get("total_candidates") != audit_sum):
            raise ValidationError(f"Invalid single-tier counts for {rule_id}")
    if (window.get("source", {}).get("id") != "cn_ip_primary"
            or window.get("window") != {
                "snapshot_days": 5,
                "minimum_presence_days": 3,
                "selection": "latest commit for each distinct UTC date",
            }
            or len(snapshots) != 5
            or len({snapshot.get("date") for snapshot in snapshots}) != 5
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
