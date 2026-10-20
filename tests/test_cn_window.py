from __future__ import annotations

from datetime import date
import json
import os
from pathlib import Path
import subprocess

import pytest

from proxyrules.build import _previous_cn_window_rules
from proxyrules.cn_window import coverage_change, stable_window_rules, select_family_update
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


def test_august_cn_ip_incident_waits_for_third_of_five_snapshots() -> None:
    """Pin the settled 3-of-5 consensus behavior."""

    base = ["1.12.0.0/14", "2400:3200::/32"]
    two_days = [
        _rules(*(base + (["59.192.0.0/10"] if day in {25, 26} else [])))
        for day in (23, 24, 25, 26, 27)
    ]
    two_day_values = {
        rule.value for rule in stable_window_rules(two_days, 3, "cn")
    }
    assert "59.192.0.0/10" not in two_day_values

    third_snapshot = list(two_days)
    third_snapshot[1] = _rules(*base, "59.192.0.0/10")
    three_day_values = {
        rule.value for rule in stable_window_rules(third_snapshot, 3, "cn")
    }
    assert "59.192.0.0/10" in three_day_values


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
        "window_days": 5,
        "minimum_presence_days": 3,
        "history_depth": 16,
        "breaker_percent": 1,
        "license": "MIT",
    }


def test_history_source_stages_and_automatically_recovers_without_cache(tmp_path: Path) -> None:
    repository = tmp_path / "upstream"
    cache = tmp_path / "cache"
    _history_repository(repository)
    source = _source(repository)
    baseline = tuple(_rules("10.0.1.0/24", "2001:db8:1::/120"))
    prepared = prepare_cidr_history_source(
        "cn_ip_primary", source, cache, refresh=True, offline=False,
        previous_rules=baseline, today=date(2026, 8, 7),
    )
    target = cache / "history/cn_ip_primary.json"
    assert not target.exists()
    assert prepared.report["status"] == "updated"
    assert all(f["status"] == "confirmed"
               for f in prepared.report["recovery"]["families"].values())
    commit_history_source_cache(prepared)
    cached = prepare_cidr_history_source(
        "cn_ip_primary", source, cache, refresh=False, offline=True,
    )
    assert cached.digest == prepared.digest
    assert cached.report == prepared.report


def _append_snapshot(repository: Path, day: int, ipv4: str, ipv6: str) -> None:
    (repository / "china.txt").write_text(f"# day {day}\n{ipv4}\n")
    (repository / "china6.txt").write_text(f"# day {day}\n{ipv6}\n")
    _git(repository, "add", "china.txt", "china6.txt")
    environment = os.environ | {
        "GIT_AUTHOR_DATE": f"2026-08-{day:02d}T04:00:00Z",
        "GIT_COMMITTER_DATE": f"2026-08-{day:02d}T04:00:00Z",
    }
    _git(repository, "commit", "-m", f"day {day}", environment=environment)


def test_invalid_family_retained_while_other_family_updates(tmp_path: Path) -> None:
    repository = tmp_path / "upstream"
    _history_repository(repository)
    baseline = tuple(_rules("10.0.0.0/24", "2001:db8::/120"))
    for day in range(8, 15):
        _append_snapshot(repository, day, "10.0.1.0/24", "not-a-cidr")
    prepared = prepare_cidr_history_source(
        "cn_ip_primary", _source(repository), tmp_path / "cache", True, False,
        previous_rules=baseline, today=date(2026, 8, 14),
    )
    assert {r.value for r in _rules(*prepared.content.splitlines())} == {
        "10.0.1.0/24", "2001:db8::/120",
    }
    families = prepared.report["recovery"]["families"]
    assert families["ipv4"]["status"] == "confirmed"
    assert families["ipv6"]["status"] == "retained"
    assert prepared.report["status"] == "partial"
    # An invalid date is excluded from observations and never poisons cached CIDRs.
    assert all(d < "2026-08-08" for d in families["ipv6"]["observation_dates"])
    commit_history_source_cache(prepared)
    cached = prepare_cidr_history_source(
        "cn_ip_primary", _source(repository), tmp_path / "cache", False, True,
    )
    assert cached.content == prepared.content


def test_network_failure_keeps_published_baseline_on_fresh_runner(tmp_path, monkeypatch):
    def fail(*args, **kwargs):
        raise UpstreamError("network unavailable")
    monkeypatch.setattr("proxyrules.upstream._run", fail)
    baseline = tuple(_rules("10.0.0.0/24", "2001:db8::/120"))
    prepared = prepare_cidr_history_source(
        "cn_ip_primary", _source(tmp_path / "missing"), tmp_path / "cache", True, False,
        previous_rules=baseline,
    )
    assert {r.value for r in _rules(*prepared.content.splitlines())} == {r.value for r in baseline}
    assert all(f["status"] == "retained"
               for f in prepared.report["recovery"]["families"].values())
    with pytest.raises(UpstreamError, match="No valid baseline"):
        prepare_cidr_history_source(
            "cn_ip_primary", _source(tmp_path / "missing"), tmp_path / "empty", True, False,
        )


def test_stale_or_truncated_snapshot_retains_family(tmp_path):
    repository = tmp_path / "upstream"
    _history_repository(repository)
    baseline = tuple(_rules("10.0.0.0/24", "2001:db8::/120"))
    source = _source(repository)
    stale = prepare_cidr_history_source(
        "cn_ip_primary", source, tmp_path / "stale", True, False,
        previous_rules=baseline, today=date(2026, 8, 20),
    )
    assert all(f["status"] == "retained"
               for f in stale.report["recovery"]["families"].values())
    _append_snapshot(repository, 8, "10.0.0.0/28", "2001:db8::/120")
    truncated = prepare_cidr_history_source(
        "cn_ip_primary", source, tmp_path / "truncated", True, False,
        previous_rules=baseline, today=date(2026, 8, 8),
    )
    assert truncated.report["recovery"]["families"]["ipv4"]["status"] == "retained"
    assert truncated.report["recovery"]["families"]["ipv6"]["status"] == "normal"


def _v4(*cidrs):
    return tuple(parse_text_source("\n".join(cidrs), "test", {"format": "cidr", "ip_version": 4}))


def test_large_change_waits_until_seventh_observation_and_updates_baseline():
    previous = _v4("10.0.0.0/24")
    candidate = _v4("10.0.1.0/24")
    for days in (5, 6):
        selected, report = select_family_update(previous, [candidate] * days, version=4, source="cn")
        assert selected == previous
        assert report["status"] == "observing"
    selected, report = select_family_update(previous, [candidate] * 7, version=4, source="cn")
    assert {r.value for r in selected} == {"10.0.1.0/24"}
    assert report["status"] == "confirmed"
    again, report = select_family_update(selected, [candidate] * 7, version=4, source="cn")
    assert again == selected
    assert report["status"] == "normal"


def test_confirmed_ranges_publish_even_when_files_keep_changing():
    previous = _v4("10.0.0.0/24", "10.0.2.0/24")
    # .2 is consistently removed; .1 consistently added; .3 oscillates;
    # .0 remains present but the upstream spelling changes each day.
    snapshots = [
        _v4(*(["10.0.0.0/24"] if day % 2 else ["10.0.0.0/25", "10.0.0.128/25"]),
            "10.0.1.0/24", *(["10.0.3.0/24"] if day < 3 else []))
        for day in range(7)
    ]
    selected, report = select_family_update(previous, snapshots, version=4, source="cn")
    assert {r.value for r in selected} == {"10.0.0.0/23"}
    assert report["status"] == "observing"
    assert report["published_added_addresses"] == "256"
    assert report["published_removed_addresses"] == "256"
    assert report["pending_added_addresses"] == "256"


def test_single_day_absence_prevents_deletion_and_small_change_is_normal():
    previous = _v4("10.0.0.0/24", "10.0.2.0/24")
    changed = _v4("10.0.0.0/24")
    selected, report = select_family_update(previous, [changed] * 6 + [previous], version=4, source="cn")
    assert {r.value for r in selected} == {r.value for r in previous}
    assert report["pending_removed_addresses"] == "256"
    small = _v4("10.0.0.0/24", "10.0.2.0/24", "10.0.3.1/32")
    selected, report = select_family_update(previous, [small] * 5, version=4, source="cn")
    assert {r.value for r in selected} == {r.value for r in small}
    assert report["status"] == "normal"


def test_multiple_commits_on_one_day_never_count_as_multiple_observations(tmp_path):
    repository = tmp_path / "upstream"
    _history_repository(repository)
    # Only one distinct day of a new change, despite many commits.
    for index in range(10):
        _append_snapshot(repository, 8, f"10.0.1.0/24\n# run {index}", "2001:db8::/120")
    prepared = prepare_cidr_history_source(
        "cn_ip_primary", _source(repository), tmp_path / "cache", True, False,
        previous_rules=tuple(_rules("10.0.0.0/24", "2001:db8::/120")),
        today=date(2026, 8, 8),
    )
    assert "10.0.1.0/24" not in prepared.content
    assert len(prepared.report["recovery"]["families"]["ipv4"]["observation_dates"]) == 7


def test_reference_disagreement_is_reported_without_blocking_stable_changes():
    previous = _v4("10.0.0.0/24")
    candidate = _v4("10.0.1.0/24")
    selected, report = select_family_update(
        previous, [candidate] * 7, version=4, source="cn", reference=previous,
    )
    assert {rule.value for rule in selected} == {"10.0.1.0/24"}
    assert report["reference_check"]["added_addresses_supported"] == "0"
    assert report["status"] == "confirmed"


def test_interval_confirmation_matches_address_sets_with_random_churn():
    import ipaddress
    import random
    generator = random.Random(20261020)
    for _ in range(50):
        # Keep one shared address so no family becomes empty.
        old = {0} | {i for i in range(1, 32) if generator.randrange(2)}
        days = [{0} | {i for i in range(1, 32) if generator.randrange(2)} for _ in range(7)]
        rules = lambda values: _v4(*(f"10.0.0.{i}/32" for i in sorted(values)))
        selected, _ = select_family_update(
            rules(old), [rules(day) for day in days], version=4, source="cn",
        )
        actual = {int(address) % 256 for rule in selected
                  for address in ipaddress.ip_network(rule.value)}
        assert actual == (old & set.union(*days)) | set.intersection(*days)
