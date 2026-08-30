from __future__ import annotations

import json
from pathlib import Path

from proxyrules.compiler import CompiledRuleset, profile_residual_rulesets
from proxyrules.model import Rule


ROOT = Path(__file__).resolve().parents[1]


def test_profile_residual_is_domain_safe_and_leaves_full_rules_unchanged() -> None:
    first = CompiledRuleset(
        "first",
        "First",
        "Manual",
        (
            Rule("full", "api.example.com"),
            Rule("domain", "example.com"),
            Rule("domain", "sub.example.com"),
            Rule("ipcidr", "192.0.2.0/24"),
        ),
        no_resolve=True,
    )
    second = CompiledRuleset(
        "second",
        "Second",
        "DIRECT",
        (
            Rule("full", "www.example.com"),
            Rule("domain", "child.example.com"),
            Rule("keyword", "independent"),
            Rule("ipcidr", "192.0.2.0/24"),
        ),
    )

    profile = profile_residual_rulesets([first, second])

    assert [rule.routing_key for rule in first.rules] == [
        ("full", "api.example.com"),
        ("domain", "example.com"),
        ("domain", "sub.example.com"),
        ("ipcidr", "192.0.2.0/24"),
    ]
    assert [rule.routing_key for rule in profile[0].rules] == [
        ("domain", "example.com"),
        ("ipcidr", "192.0.2.0/24"),
    ]
    assert profile[0].profile_removed_within == 2
    assert [rule.routing_key for rule in profile[1].rules] == [
        ("keyword", "independent"),
        ("ipcidr", "192.0.2.0/24"),
    ]
    assert profile[1].profile_removed_prior == 2


def _active_stash_rules(directory: str, rule_id: str) -> set[str]:
    path = ROOT / "dist/stash" / directory / f"{rule_id}.list"
    return {
        line
        for line in path.read_text().splitlines()
        if line and not line.startswith("#")
    }


def _suffix_chain(value: str, *, proper: bool = False) -> set[str]:
    labels = value.lower().rstrip(".").split(".")
    return {
        ".".join(labels[index:])
        for index in range(1 if proper else 0, len(labels))
    }


def test_every_real_profile_removal_has_a_first_match_cover() -> None:
    metadata = json.loads((ROOT / "dist/metadata.json").read_text())
    active_ids = [entry["id"] for entry in metadata["rulesets"]]
    prior_lines: set[str] = set()
    prior_suffixes: set[str] = set()
    removed_total = 0
    for rule_id in active_ids:
        full = _active_stash_rules("rules-full", rule_id)
        profile = _active_stash_rules("rules-profile", rule_id)
        own_suffixes = {
            line.split(",", 1)[1].lower().rstrip(".")
            for line in full
            if line.startswith("DOMAIN-SUFFIX,")
        }
        for line in full - profile:
            kind, value = line.split(",", 1)
            if kind.startswith("IP-"):
                raise AssertionError(f"IP residualization is unsafe: {rule_id} {line}")
            within = False
            prior = line in prior_lines
            if kind in {"DOMAIN", "DOMAIN-SUFFIX"}:
                candidates = _suffix_chain(
                    value,
                    proper=kind == "DOMAIN-SUFFIX",
                )
                within = bool(candidates & own_suffixes)
                prior = prior or bool(_suffix_chain(value) & prior_suffixes)
            assert within or prior, f"uncovered removal: {rule_id} {line}"
        removed_total += len(full - profile)
        prior_lines.update(full)
        prior_suffixes.update(own_suffixes)

    assert removed_total == metadata["profile_residual"]["total"] == 11060


def test_google_cn_is_complete_full_only_output() -> None:
    metadata = json.loads((ROOT / "dist/metadata.json").read_text())
    entry = metadata["full_only_rulesets"]
    assert entry == [
        {
            "id": "google-cn",
            "policy": "DIRECT",
            "rules": 112,
            "kinds": {"domain": 112},
        }
    ]
    for target, suffix in (
        ("stash", "list"),
        ("loon", "list"),
        ("shadowrocket", "list"),
        ("surge", "list"),
        ("qx", "list"),
        ("egern", "yaml"),
    ):
        assert (ROOT / f"dist/{target}/rules-full/google-cn.{suffix}").is_file()
        assert not (ROOT / f"dist/{target}/rules-profile/google-cn.{suffix}").exists()
