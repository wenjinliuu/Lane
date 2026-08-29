from __future__ import annotations

import ipaddress
from pathlib import Path
import re

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]


def _matches(kind: str, rule_value: str, input_type: str, value: str) -> bool:
    if input_type == "domain":
        domain = value.lower().rstrip(".")
        candidate = rule_value.lower()
        if kind == "DOMAIN":
            return domain == candidate
        if kind == "DOMAIN-SUFFIX":
            return domain == candidate or domain.endswith("." + candidate)
        if kind == "DOMAIN-KEYWORD":
            return candidate in domain
        if kind == "DOMAIN-REGEX":
            return re.search(rule_value, domain) is not None
        return False

    if input_type == "ip" and kind in {"IP-CIDR", "IP-CIDR6"}:
        return ipaddress.ip_address(value) in ipaddress.ip_network(rule_value)
    return False


def _first_match(input_type: str, value: str) -> dict[str, str]:
    profile = yaml.safe_load((ROOT / "dist/stash/Lane_stash.yaml").read_text())
    for route in profile["rules"]:
        if not route.startswith("RULE-SET,"):
            continue
        _, ruleset, policy = route.split(",")
        rule_path = ROOT / "dist" / "stash" / "rules" / f"{ruleset}.list"
        for line in rule_path.read_text().splitlines():
            if not line or line.startswith("#"):
                continue
            kind, remainder = line.split(",", 1)
            # IP rules may carry no-resolve. Regex quantifiers may contain commas,
            # so only IP values can safely be cut again.
            rule_value = remainder.split(",", 1)[0] if kind.startswith("IP-") else remainder
            if _matches(kind, rule_value, input_type, value):
                return {"ruleset": ruleset, "policy": policy}
    return {"ruleset": "final", "policy": "Final"}


def _cases() -> list[dict[str, object]]:
    document = yaml.safe_load((ROOT / "tests/route_cases.yaml").read_text())
    assert document["schema"] == 1
    assert document["cases"]
    return document["cases"]


@pytest.mark.parametrize("case", _cases(), ids=lambda case: case["id"])
def test_route_case(case: dict[str, object]) -> None:
    route_input = case["input"]
    assert isinstance(route_input, dict)
    expected = case["expected"]
    assert isinstance(expected, dict)
    assert _first_match(route_input["type"], route_input["value"]) == expected
