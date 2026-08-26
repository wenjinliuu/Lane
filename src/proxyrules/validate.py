from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .v2fly import parse_custom_file


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
        if active and stripped and not stripped.startswith("#"):
            lines.append(stripped)
    return lines


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
        dist / "stash" / "stash.yaml",
        dist / "loon" / "loon.conf",
        dist / "shadowrocket" / "shadowrocket.conf",
        dist / "metadata.json",
        dist / "report.json",
    ]
    missing = [str(path.relative_to(root)) for path in required if not path.is_file()]
    if missing:
        raise ValidationError(f"Missing generated files: {', '.join(missing)}")

    stash = yaml.safe_load((dist / "stash" / "stash.yaml").read_text(encoding="utf-8"))
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
    if list(stash.get("rule-providers", {})) != expected_rule_ids:
        raise ValidationError("Stash rule-provider order differs from the manifest")
    if stash.get("rules", [])[-2:] != ["GEOIP,CN,DIRECT", "MATCH,Final"]:
        raise ValidationError("Stash final routing rules are invalid")

    loon_text = (dist / "loon" / "loon.conf").read_text(encoding="utf-8")
    shadow_text = (dist / "shadowrocket" / "shadowrocket.conf").read_text(
        encoding="utf-8"
    )
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
