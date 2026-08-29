from __future__ import annotations

from dataclasses import dataclass, replace
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
    profile_removed_within: int = 0
    profile_removed_prior: int = 0


def _deduplicate(rules: list[Rule]) -> tuple[Rule, ...]:
    by_routing_key: dict[tuple[str, str], Rule] = {}
    for rule in rules:
        by_routing_key.setdefault(rule.routing_key, rule)
    return tuple(sorted(by_routing_key.values(), key=lambda rule: rule.sort_key))


def _semantic_key(rule: Rule) -> tuple[str, str]:
    value = rule.value.lower().rstrip(".") if rule.kind in {"full", "domain"} else rule.value
    return rule.kind, value


def _domain_suffixes(value: str, *, proper: bool = False) -> tuple[str, ...]:
    labels = value.lower().rstrip(".").split(".")
    start = 1 if proper else 0
    return tuple(".".join(labels[index:]) for index in range(start, len(labels)))


def _covered_by_suffix(rule: Rule, suffixes: set[str], *, same_ruleset: bool) -> bool:
    if rule.kind == "full":
        candidates = _domain_suffixes(rule.value)
    elif rule.kind == "domain":
        # A suffix rule must not remove itself. Exact duplicates were already
        # removed by _deduplicate; only a proper parent is relevant here.
        candidates = _domain_suffixes(rule.value, proper=same_ruleset)
    else:
        return False
    return any(candidate in suffixes for candidate in candidates)


def profile_residual_rulesets(
    rulesets: list[CompiledRuleset],
) -> list[CompiledRuleset]:
    """Build profile-only residuals without changing first-match routing.

    Full rulesets deliberately retain their complete independently reusable
    content. Profile rules first drop exact-domain/suffix entries covered by a
    parent suffix in the same ruleset, then drop entries already fully covered
    by an earlier ruleset. Keyword, regular-expression and IP containment are
    not inferred: proving those relationships across six client engines would
    be unsafe, especially when ``no_resolve`` differs between IP rulesets.
    """

    output: list[CompiledRuleset] = []
    prior_exact: set[tuple[str, str]] = set()
    prior_suffixes: set[str] = set()
    for ruleset in rulesets:
        own_suffixes = {
            rule.value.lower().rstrip(".")
            for rule in ruleset.rules
            if rule.kind == "domain"
        }
        semantic = tuple(
            rule
            for rule in ruleset.rules
            if not _covered_by_suffix(rule, own_suffixes, same_ruleset=True)
        )
        residual = tuple(
            rule
            for rule in semantic
            if ((rule.kind in {"ipcidr", "ipcidr6"}
                 or _semantic_key(rule) not in prior_exact)
                and not _covered_by_suffix(rule, prior_suffixes, same_ruleset=False))
        )
        output.append(
            replace(
                ruleset,
                rules=residual,
                profile_removed_within=len(ruleset.rules) - len(semantic),
                profile_removed_prior=len(semantic) - len(residual),
            )
        )
        # Use the semantically cleaned complete earlier ruleset as coverage.
        # Rules removed from it are themselves covered by another rule here.
        prior_exact.update(_semantic_key(rule) for rule in semantic)
        prior_suffixes.update(
            rule.value.lower().rstrip(".")
            for rule in semantic
            if rule.kind == "domain"
        )
    return output


def compile_rulesets(
    root: Path,
    entries: list[dict[str, Any]],
    repository: DomainListRepository,
    text_sources: dict[str, str],
    source_specs: dict[str, dict[str, Any]] | None = None,
    *,
    allow_full_only_sources: bool = False,
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
            if spec.get("role") == "full-only" and not allow_full_only_sources:
                raise ValueError(f"Full-only source {source_id} cannot be used by a profile")
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
