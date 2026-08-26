from __future__ import annotations

import ipaddress
from collections import defaultdict
from pathlib import Path

from .model import Include, ParsedDomainList, Rule


class DomainListError(ValueError):
    pass


def _strip_comment(line: str) -> str:
    return line.split("#", 1)[0].strip()


def _attributes(tokens: list[str]) -> tuple[frozenset[str], frozenset[str]]:
    attrs: set[str] = set()
    affiliations: set[str] = set()
    for token in tokens:
        if token.startswith("@") and len(token) > 1:
            attrs.add(token[1:])
        elif token.startswith("&") and len(token) > 1:
            affiliations.add(token[1:])
    return frozenset(attrs), frozenset(affiliations)


def _parse_include(spec: str, tokens: list[str]) -> Include:
    name = spec.removeprefix("include:").strip()
    if not name:
        raise DomainListError("Empty include name")
    required: set[str] = set()
    excluded: set[str] = set()
    for token in tokens:
        if not token.startswith("@"):
            continue
        value = token[1:]
        if value.startswith("-"):
            excluded.add(value[1:])
        elif value:
            required.add(value)
    return Include(name, frozenset(required), frozenset(excluded))


def _parse_rule(spec: str, attrs: frozenset[str], source: str) -> Rule:
    prefixes = {
        "domain:": "domain",
        "full:": "full",
        "keyword:": "keyword",
        "regexp:": "regexp",
        "ipcidr:": "ipcidr",
        "ipcidr6:": "ipcidr6",
    }
    for prefix, kind in prefixes.items():
        if spec.startswith(prefix):
            value = spec[len(prefix) :].strip()
            if not value:
                raise DomainListError(f"Empty {kind} rule in {source}")
            return Rule(kind, value, attrs, source)

    try:
        network = ipaddress.ip_network(spec, strict=False)
    except ValueError:
        return Rule("domain", spec, attrs, source)
    kind = "ipcidr6" if network.version == 6 else "ipcidr"
    return Rule(kind, str(network), attrs, source)


def parse_text(text: str, source: str) -> tuple[ParsedDomainList, dict[str, list[Rule]]]:
    parsed = ParsedDomainList()
    affiliated: dict[str, list[Rule]] = defaultdict(list)
    for line_number, raw in enumerate(text.splitlines(), start=1):
        line = _strip_comment(raw)
        if not line:
            continue
        tokens = line.split()
        spec = tokens[0]
        try:
            if spec.startswith("include:"):
                parsed.includes.append(_parse_include(spec, tokens[1:]))
                continue
            attrs, affiliations = _attributes(tokens[1:])
            rule = _parse_rule(spec, attrs, source)
        except DomainListError as exc:
            raise DomainListError(f"{source}:{line_number}: {exc}") from exc
        parsed.rules.append(rule)
        for target in affiliations:
            affiliated[target].append(rule)
    return parsed, affiliated


class DomainListRepository:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self._lists: dict[str, ParsedDomainList] = {}
        self._resolved: dict[str, tuple[Rule, ...]] = {}
        self._load()

    def _load(self) -> None:
        if not self.data_dir.is_dir():
            raise DomainListError(f"Missing v2fly data directory: {self.data_dir}")
        affiliations: dict[str, list[Rule]] = defaultdict(list)
        for path in sorted(self.data_dir.iterdir()):
            if not path.is_file():
                continue
            parsed, targets = parse_text(path.read_text(encoding="utf-8"), path.name)
            self._lists[path.name] = parsed
            for name, rules in targets.items():
                affiliations[name].extend(rules)
        for name, rules in affiliations.items():
            self._lists.setdefault(name, ParsedDomainList()).rules.extend(rules)

    @property
    def names(self) -> set[str]:
        return set(self._lists)

    def resolve(self, name: str) -> tuple[Rule, ...]:
        return self._resolve(name, ())

    def _resolve(self, name: str, stack: tuple[str, ...]) -> tuple[Rule, ...]:
        if name in self._resolved:
            return self._resolved[name]
        if name not in self._lists:
            raise DomainListError(f"Unknown v2fly list: {name}")
        if name in stack:
            chain = " -> ".join((*stack, name))
            raise DomainListError(f"Circular include: {chain}")

        parsed = self._lists[name]
        output = list(parsed.rules)
        for include in parsed.includes:
            children = self._resolve(include.name, (*stack, name))
            for rule in children:
                if include.require and not include.require.issubset(rule.attributes):
                    continue
                if include.exclude.intersection(rule.attributes):
                    continue
                output.append(rule)

        unique = sorted(set(output), key=lambda rule: rule.sort_key)
        result = tuple(unique)
        self._resolved[name] = result
        return result


def parse_custom_file(path: Path) -> list[Rule]:
    if not path.exists():
        raise DomainListError(f"Missing custom rule file: {path}")
    parsed, affiliations = parse_text(path.read_text(encoding="utf-8"), str(path))
    if parsed.includes or affiliations:
        raise DomainListError(f"Custom rule files cannot use include or affiliation: {path}")
    return parsed.rules


def parse_cidr_text(text: str, source: str) -> list[Rule]:
    output: list[Rule] = []
    for line_number, raw in enumerate(text.splitlines(), start=1):
        value = _strip_comment(raw)
        if not value:
            continue
        try:
            network = ipaddress.ip_network(value, strict=False)
        except ValueError as exc:
            raise DomainListError(f"{source}:{line_number}: invalid CIDR {value}") from exc
        kind = "ipcidr6" if network.version == 6 else "ipcidr"
        output.append(Rule(kind, str(network), source=source))
    return output

