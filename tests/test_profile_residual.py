from __future__ import annotations

import json
from pathlib import Path

from proxyrules.compiler import (
    CompiledRuleset,
    audit_rule_redundancy,
    compile_rulesets,
)
from proxyrules.config import load_project_config
from proxyrules.model import Rule
from proxyrules.render import RULES_DIR, TARGETS


ROOT = Path(__file__).resolve().parents[1]


def test_redundancy_audit_is_report_only() -> None:
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
    before = (first.rules, second.rules)

    audit = audit_rule_redundancy([first, second])

    assert (first.rules, second.rules) == before
    assert audit["first"].within_parent_suffix == 2
    assert audit["first"].total == 2
    assert audit["second"].previous_exact == 0
    assert audit["second"].previous_parent_suffix == 2
    assert audit["second"].total == 2


def test_compiler_removes_only_exact_duplicates(tmp_path: Path) -> None:
    custom = tmp_path / "sample.list"
    custom.write_text(
        "domain:example.com\n"
        "domain:example.com\n"
        "full:api.example.com\n"
        "domain:sub.example.com\n",
        encoding="utf-8",
    )
    rulesets = compile_rulesets(
        tmp_path,
        [{
            "id": "sample",
            "title": "Sample",
            "policy": "DIRECT",
            "custom": "sample.list",
        }],
        None,
        {},
    )

    assert rulesets[0].exact_duplicates_removed == 1
    assert {rule.routing_key for rule in rulesets[0].rules} == {
        ("domain", "example.com"),
        ("full", "api.example.com"),
        ("domain", "sub.example.com"),
    }


def test_generated_artifacts_use_one_complete_rule_tier() -> None:
    metadata = json.loads((ROOT / "dist/metadata.json").read_text())
    assert metadata["schema"] == 3
    assert metadata["artifacts"] == {
        "rules": "rules",
        "default_profiles_use": "rules",
        "deduplication": "exact-only",
    }
    optimization = metadata["rule_optimization"]
    assert optimization["exact_duplicate_removal"] == {
        "enabled": True,
        "removed": sum(entry["exact_duplicates_removed"] for entry in metadata["rulesets"]),
    }
    assert optimization["parent_suffix_removal"] is False
    assert optimization["cross_ruleset_residual_removal"] is False
    audit = metadata["redundancy_audit"]
    assert audit["mode"] == "report-only"
    assert audit["within_parent_suffix_candidates"] == sum(
        entry["redundancy_audit"]["within_parent_suffix_candidates"]
        for entry in metadata["rulesets"]
    )
    assert audit["total_candidates"] == sum(
        entry["redundancy_audit"]["total_candidates"]
        for entry in metadata["rulesets"]
    )

    for target in TARGETS:
        directory = ROOT / "dist" / target / RULES_DIR
        assert directory.is_dir()
        assert not (ROOT / "dist" / target / "rules-full").exists()
        assert not (ROOT / "dist" / target / "rules-profile").exists()


def test_google_cn_is_neither_fetched_nor_published() -> None:
    config = load_project_config(ROOT)
    metadata = json.loads((ROOT / "dist/metadata.json").read_text())
    assert "google_cn" not in config["sources"]["sources"]
    assert "full_only_rulesets" not in config["rulesets"]
    assert "google_cn" not in metadata["sources"]
    assert all(entry["id"] != "google-cn" for entry in metadata["rulesets"])
    for target in TARGETS:
        suffix = "yaml" if target == "egern" else "list"
        assert not (ROOT / "dist" / target / RULES_DIR / f"google-cn.{suffix}").exists()
