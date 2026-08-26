from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .model import Rule
from .v2fly import DomainListRepository, parse_cidr_text, parse_custom_file


@dataclass(frozen=True)
class CompiledRuleset:
    id: str
    title: str
    policy: str
    rules: tuple[Rule, ...]
    no_resolve: bool = False


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
) -> list[CompiledRuleset]:
    output: list[CompiledRuleset] = []
    for entry in entries:
        rules: list[Rule] = []
        for name in entry.get("v2fly", []):
            rules.extend(repository.resolve(name))
        if custom := entry.get("custom"):
            rules.extend(parse_custom_file(root / custom))
        if source_id := entry.get("text_source"):
            if source_id not in text_sources:
                raise ValueError(f"Missing text source {source_id}")
            rules.extend(parse_cidr_text(text_sources[source_id], source_id))
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
            )
        )
    return output
