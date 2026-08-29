from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .model import Rule
from .text_sources import parse_text_source, text_source_ids
from .v2fly import DomainListRepository, parse_custom_file


@dataclass(frozen=True)
class CompiledRuleset:
    id: str
    title: str
    policy: str
    rules: tuple[Rule, ...]
    no_resolve: bool = False
    source_notices: tuple[str, ...] = ()


def _deduplicate(rules: list[Rule]) -> tuple[Rule, ...]:
    by_routing_key: dict[tuple[str, str], Rule] = {}
    for rule in rules:
        by_routing_key.setdefault(rule.routing_key, rule)
    return tuple(sorted(by_routing_key.values(), key=lambda rule: rule.sort_key))


def compile_rulesets(
    root: Path,
    entries: list[dict[str, Any]],
    repository: DomainListRepository,
    text_sources: dict[str, str],
    source_specs: dict[str, dict[str, Any]] | None = None,
) -> list[CompiledRuleset]:
    output: list[CompiledRuleset] = []
    for entry in entries:
        rules: list[Rule] = []
        notices: list[str] = []
        for name in entry.get("v2fly", []):
            rules.extend(repository.resolve(name))
        if custom := entry.get("custom"):
            rules.extend(parse_custom_file(root / custom))
        for source_id in text_source_ids(entry):
            if source_id not in text_sources:
                raise ValueError(f"Missing text source {source_id}")
            spec = (source_specs or {}).get(source_id, {})
            if spec.get("role") == "validation-only":
                raise ValueError(f"Validation-only source {source_id} cannot be routed")
            rules.extend(parse_text_source(text_sources[source_id], source_id, spec))
            if license_name := spec.get("license"):
                notices.extend([f"Source: {spec['url']}", f"License: {license_name}"])
        if notices:
            notices.append("Adapted by Lane: extraction, normalization, deduplication and client format conversion.")
        compiled_rules = _deduplicate(rules)
        if entry.get("omit_if_empty") and not compiled_rules:
            continue
        output.append(
            CompiledRuleset(
                id=entry["id"],
                title=entry["title"],
                policy=entry["policy"],
                rules=compiled_rules,
                no_resolve=bool(entry.get("no_resolve")),
                source_notices=tuple(notices),
            )
        )
    return output
