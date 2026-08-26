from __future__ import annotations

from dataclasses import dataclass, field


RULE_KIND_ORDER = {
    "full": 0,
    "domain": 1,
    "keyword": 2,
    "regexp": 3,
    "ipcidr": 4,
    "ipcidr6": 5,
}


@dataclass(frozen=True)
class Rule:
    kind: str
    value: str
    attributes: frozenset[str] = field(default_factory=frozenset)
    source: str = field(default="", compare=False)

    @property
    def routing_key(self) -> tuple[str, str]:
        return self.kind, self.value

    @property
    def sort_key(self) -> tuple[int, str, tuple[str, ...]]:
        return (
            RULE_KIND_ORDER.get(self.kind, 99),
            self.value.lower(),
            tuple(sorted(self.attributes)),
        )


@dataclass(frozen=True)
class Include:
    name: str
    require: frozenset[str] = field(default_factory=frozenset)
    exclude: frozenset[str] = field(default_factory=frozenset)


@dataclass
class ParsedDomainList:
    rules: list[Rule] = field(default_factory=list)
    includes: list[Include] = field(default_factory=list)

