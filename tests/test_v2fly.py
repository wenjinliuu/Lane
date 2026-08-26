from pathlib import Path

import pytest

from proxyrules.v2fly import DomainListError, DomainListRepository, parse_text


def test_include_attributes_and_affiliation(tmp_path: Path) -> None:
    (tmp_path / "child").write_text(
        "domain:public.example @public\n"
        "full:private.example @private\n"
        "domain:shared.example &affiliate\n",
        encoding="utf-8",
    )
    (tmp_path / "parent").write_text(
        "include:child @public\nfull:parent.example\n", encoding="utf-8"
    )

    repository = DomainListRepository(tmp_path)
    assert {(rule.kind, rule.value) for rule in repository.resolve("parent")} == {
        ("domain", "public.example"),
        ("full", "parent.example"),
    }
    assert [rule.value for rule in repository.resolve("affiliate")] == [
        "shared.example"
    ]


def test_include_cycle_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "a").write_text("include:b\n", encoding="utf-8")
    (tmp_path / "b").write_text("include:a\n", encoding="utf-8")
    repository = DomainListRepository(tmp_path)
    with pytest.raises(DomainListError, match="Circular include"):
        repository.resolve("a")


def test_plain_domain_and_cidr_parsing() -> None:
    parsed, _ = parse_text(
        "example.com\n1.2.3.4/24\n2001:db8::/32\n", "fixture"
    )
    assert [(rule.kind, rule.value) for rule in parsed.rules] == [
        ("domain", "example.com"),
        ("ipcidr", "1.2.3.0/24"),
        ("ipcidr6", "2001:db8::/32"),
    ]
