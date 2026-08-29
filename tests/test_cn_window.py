from __future__ import annotations

import os
from pathlib import Path
import subprocess

import pytest

from proxyrules.build import _previous_cn_window_rules
from proxyrules.cn_window import coverage_change, stable_window_rules
from proxyrules.text_sources import parse_text_source
from proxyrules.upstream import (
    UpstreamError,
    commit_history_source_cache,
    prepare_cidr_history_source,
)


def _rules(*cidrs: str):
    return parse_text_source(
        "\n".join(cidrs),
        "snapshot",
        {"format": "cidr", "ip_versions": [4, 6]},
    )


def test_stable_window_counts_addresses_not_cidr_spelling() -> None:
    whole = _rules("10.0.0.0/24", "2001:db8::/126")
    split = _rules(
        "10.0.0.0/25",
        "10.0.0.128/25",
        "2001:db8::/127",
        "2001:db8::2/127",
    )
    stable = stable_window_rules([whole, split, whole, split, whole, split, whole], 5, "cn")
    assert [(rule.kind, rule.value) for rule in stable] == [
        ("ipcidr", "10.0.0.0/24"),
        ("ipcidr6", "2001:db8::/126"),
    ]


def test_stable_window_keeps_five_days_and_drops_four_days() -> None:
    snapshots = []
    for day in range(7):
        cidrs = ["10.0.0.0/24", "2001:db8::/120"]
        if day < 5:
            cidrs.extend(["10.0.2.0/24", "2001:db8:2::/120"])
        if day < 4:
            cidrs.extend(["10.0.4.0/24", "2001:db8:4::/120"])
        snapshots.append(_rules(*cidrs))
    stable = stable_window_rules(snapshots, 5, "cn")
    values = {rule.value for rule in stable}
    assert {"10.0.0.0/24", "10.0.2.0/24", "2001:db8::/120", "2001:db8:2::/120"} <= values
    assert "10.0.4.0/24" not in values
    assert "2001:db8:4::/120" not in values


def test_august_cn_ip_incident_waits_for_fifth_snapshot() -> None:
    """Pin the 2026-08-25 rise / 2026-08-28 fall threshold behavior."""

    base = ["1.12.0.0/14", "2400:3200::/32"]
    four_days = [
        _rules(*(base + (["59.192.0.0/10"] if day in {25, 26, 27, 29} else [])))
        for day in (22, 23, 25, 26, 27, 28, 29)
    ]
    four_day_values = {
        rule.value for rule in stable_window_rules(four_days, 5, "cn")
    }
    assert "59.192.0.0/10" not in four_day_values

    fifth_snapshot = list(four_days)
    fifth_snapshot[1] = _rules(*base, "59.192.0.0/10")
    five_day_values = {
        rule.value for rule in stable_window_rules(fifth_snapshot, 5, "cn")
    }
    assert "59.192.0.0/10" in five_day_values


def test_breaker_uses_symmetric_address_space_difference() -> None:
    previous = _rules("10.0.0.0/24", "2001:db8::/120")
    equivalent = _rules(
        "10.0.0.0/25",
        "10.0.0.128/25",
        "2001:db8::/121",
        "2001:db8::80/121",
    )
    assert coverage_change(previous, equivalent, 1)["exceeded"] is False
    assert coverage_change(previous, equivalent, 1)["families"]["ipv4"]["changed_percent"] == 0.0

    replacement = _rules("10.0.1.0/24", "2001:db8:1::/120")
    report = coverage_change(previous, replacement, 1)
    assert report["exceeded"] is True
    assert report["families"]["ipv4"]["changed_percent"] == 200.0
    assert report["families"]["ipv6"]["changed_percent"] == 200.0


def test_checked_in_cn_ip_is_initial_migration_baseline(tmp_path: Path) -> None:
    rules_path = tmp_path / "dist/stash/rules/cn-ip.list"
    rules_path.parent.mkdir(parents=True)
    rules_path.write_text(
        "# Last published output predates cn-ip-window.json\n"
        "IP-CIDR,1.12.0.0/14,DIRECT\n"
        "IP-CIDR6,2400:3200::/32,DIRECT\n",
        encoding="utf-8",
    )

    baseline = _previous_cn_window_rules(tmp_path)
    assert baseline is not None
    assert {rule.routing_key for rule in baseline} == {
        ("ipcidr", "1.12.0.0/14"),
        ("ipcidr6", "2400:3200::/32"),
    }


def _git(repository: Path, *args: str, environment: dict[str, str] | None = None) -> None:
    subprocess.run(
        ["git", *args],
        cwd=repository,
        env=environment,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def _history_repository(path: Path) -> None:
    path.mkdir()
    _git(path, "init", "-b", "ip-lists")
    _git(path, "config", "user.name", "Lane Test")
    _git(path, "config", "user.email", "lane@example.invalid")
    for day in range(1, 8):
        (path / "china.txt").write_text(
            f"# day {day}\n10.0.0.0/24\n", encoding="utf-8"
        )
        (path / "china6.txt").write_text(
            f"# day {day}\n2001:db8::/120\n", encoding="utf-8"
        )
        _git(path, "add", "china.txt", "china6.txt")
        environment = os.environ | {
            "GIT_AUTHOR_DATE": f"2026-08-{day:02d}T04:00:00Z",
            "GIT_COMMITTER_DATE": f"2026-08-{day:02d}T04:00:00Z",
        }
        _git(path, "commit", "--allow-empty", "-m", f"day {day}", environment=environment)


def _source(repository: Path) -> dict[str, object]:
    return {
        "kind": "git-history-cidr",
        "format": "cidr",
        "ip_versions": [4, 6],
        "repository": str(repository),
        "ref": "ip-lists",
        "url": "https://example.invalid/history",
        "files": {"ipv4": "china.txt", "ipv6": "china6.txt"},
        "window_days": 7,
        "minimum_presence_days": 5,
        "history_depth": 16,
        "breaker_percent": 1,
        "license": "MIT",
    }


def test_history_source_stages_validates_and_preserves_cache(tmp_path: Path) -> None:
    repository = tmp_path / "upstream"
    cache = tmp_path / "cache"
    _history_repository(repository)
    source = _source(repository)

    prepared = prepare_cidr_history_source(
        "cn_ip_primary", source, cache, refresh=True, offline=False
    )
    target = cache / "history" / "cn_ip_primary.json"
    assert not target.exists()
    commit_history_source_cache(prepared)
    assert prepared.report["window"]["minimum_presence_days"] == 5
    assert [item["date"] for item in prepared.report["snapshots"]] == [
        "2026-08-07",
        "2026-08-06",
        "2026-08-05",
        "2026-08-04",
        "2026-08-03",
        "2026-08-02",
        "2026-08-01",
    ]
    last_known_good = target.read_bytes()

    reviewed_baseline = tuple(_rules("10.0.1.0/24", "2001:db8:1::/120"))
    with pytest.raises(UpstreamError, match="breaker exceeded"):
        prepare_cidr_history_source(
            "cn_ip_primary",
            source,
            cache,
            refresh=True,
            offline=False,
            previous_rules=reviewed_baseline,
        )
    assert target.read_bytes() == last_known_good
    accepted = prepare_cidr_history_source(
        "cn_ip_primary",
        source,
        cache,
        refresh=True,
        offline=False,
        previous_rules=reviewed_baseline,
        accept_breaker=True,
    )
    assert accepted.report["breaker"]["exceeded"] is True
    assert accepted.report["breaker"]["accepted"] is True
    commit_history_source_cache(accepted)
    last_known_good = target.read_bytes()

    (repository / "china6.txt").write_text("not-a-cidr\n", encoding="utf-8")
    _git(repository, "add", "china6.txt")
    environment = os.environ | {
        "GIT_AUTHOR_DATE": "2026-08-08T04:00:00Z",
        "GIT_COMMITTER_DATE": "2026-08-08T04:00:00Z",
    }
    _git(repository, "commit", "-m", "invalid day", environment=environment)

    with pytest.raises(UpstreamError, match="Invalid ipv6 snapshot"):
        prepare_cidr_history_source(
            "cn_ip_primary", source, cache, refresh=True, offline=False
        )
    assert target.read_bytes() == last_known_good

    cached = prepare_cidr_history_source(
        "cn_ip_primary", source, cache, refresh=False, offline=True
    )
    assert cached.digest == prepared.digest
