from __future__ import annotations

import hashlib
from collections import defaultdict
from decimal import Decimal
from typing import Any, Iterable, Sequence

from .cn_validation import _addresses, _cidrs, _coverage, _subtract
from .model import Rule


def canonical_cidr_text(rules: Iterable[Rule]) -> str:
    ordered = sorted(rules, key=lambda rule: rule.sort_key)
    return "".join(f"{rule.value}\n" for rule in ordered)


def coverage_stats(rules: Iterable[Rule]) -> dict[str, dict[str, str | int]]:
    rules = tuple(rules)
    output: dict[str, dict[str, str | int]] = {}
    for version, kind in ((4, "ipcidr"), (6, "ipcidr6")):
        intervals = _coverage(rules, version)
        output[f"ipv{version}"] = {
            "rule_count": sum(rule.kind == kind for rule in rules),
            "addresses": str(_addresses(intervals)),
        }
    return output


def stable_window_rules(
    snapshots: Sequence[Iterable[Rule]],
    minimum_days: int,
    source: str,
    versions: tuple[int, ...] = (4, 6),
) -> tuple[Rule, ...]:
    """Return address space present in at least ``minimum_days`` snapshots.

    Coverage is counted as integer address intervals, not textual CIDR rows, so
    an upstream split from one /24 into two /25s does not look like a change.
    """

    if not snapshots or not 1 <= minimum_days <= len(snapshots):
        raise ValueError("Invalid CN-IP window size or minimum presence")
    snapshots = tuple(tuple(snapshot) for snapshot in snapshots)
    output: list[Rule] = []
    for version, kind in ((4, "ipcidr"), (6, "ipcidr6")):
        if version not in versions:
            continue
        events: dict[int, int] = defaultdict(int)
        for snapshot in snapshots:
            intervals = _coverage(snapshot, version)
            if not intervals:
                raise ValueError(f"Every CN-IP snapshot must contain IPv{version}")
            for start, end in intervals:
                events[start] += 1
                events[end + 1] -= 1

        points = sorted(events)
        stable: list[tuple[int, int]] = []
        present = 0
        for index, point in enumerate(points[:-1]):
            present += events[point]
            next_point = points[index + 1]
            if present < minimum_days or point >= next_point:
                continue
            start, end = point, next_point - 1
            if stable and stable[-1][1] + 1 == start:
                stable[-1] = stable[-1][0], end
            else:
                stable.append((start, end))

        for cidr in _cidrs(stable, version):
            output.append(Rule(kind, cidr, source=source))

    if not output:
        raise ValueError("CN-IP stable window produced no routes")
    return tuple(sorted(output, key=lambda rule: rule.sort_key))


def select_family_update(
    previous: tuple[Rule, ...] | None,
    snapshots: Sequence[tuple[Rule, ...]],
    *,
    version: int,
    source: str,
    window_days: int = 5,
    minimum_days: int = 3,
    confirmation_days: int = 7,
    threshold_percent: float = 1,
    reference: tuple[Rule, ...] | None = None,
) -> tuple[tuple[Rule, ...], dict[str, Any]]:
    """Publish ordinary consensus, or only individually confirmed large changes.

    Snapshots must be newest first, validated, and from distinct UTC dates.
    Interval operations deliberately ignore CIDR spelling and file hashes.
    """
    if len(snapshots) < window_days:
        raise ValueError("Not enough valid daily snapshots for normal consensus")
    candidate = stable_window_rules(
        snapshots[:window_days], minimum_days, source, versions=(version,)
    )
    new = _coverage(candidate, version)
    old = _coverage(previous, version) if previous is not None else None
    changed_percent = (
        float(Decimal((_addresses(_subtract(new, old))
                       + _addresses(_subtract(old, new))) * 100)
              / Decimal(_addresses(old))) if old else None
    )
    exceeded = changed_percent is not None and changed_percent > threshold_percent
    selected = candidate
    if exceeded:
        selected = previous
        if len(snapshots) >= confirmation_days:
            # Retain old addresses seen on any observation day. Add addresses
            # seen on every day. Thus unrelated small churn cannot reset a
            # long-lived change, and unconfirmed deletions remain protected.
            all_days = _coverage(stable_window_rules(
                snapshots[:confirmation_days], confirmation_days, source,
                versions=(version,),
            ), version)
            any_day = _coverage(stable_window_rules(
                snapshots[:confirmation_days], 1, source, versions=(version,),
            ), version)
            removed = _subtract(old, any_day)
            retained = _subtract(old, removed)
            kind = "ipcidr" if version == 4 else "ipcidr6"
            merged = _coverage(
                [Rule(kind, cidr, source=source)
                 for cidr in _cidrs(retained, version) + _cidrs(all_days, version)],
                version,
            )
            selected = tuple(Rule(kind, cidr, source=source)
                             for cidr in _cidrs(merged, version))
            if not selected:
                raise ValueError("Confirmation must not empty an IP family")
    output = _coverage(selected, version)
    reference_check: dict[str, Any] = {"available": reference is not None, "role": "advisory-only"}
    if reference is not None:
        reference_space = _coverage(reference, version)
        added = _subtract(new, old) if old else new
        removed = _subtract(old, new) if old else []
        reference_check.update({
            "candidate_added_addresses": str(_addresses(added)),
            "added_addresses_supported": str(_addresses(added) - _addresses(_subtract(added, reference_space))),
            "candidate_removed_addresses": str(_addresses(removed)),
            "removed_addresses_supported": str(_addresses(_subtract(removed, reference_space))),
        })
    pending_added = _subtract(new, output)
    pending_removed = _subtract(output, new)
    return tuple(selected), {
        "status": ("observing" if pending_added or pending_removed else
                   "confirmed" if exceeded else "normal"),
        "threshold_exceeded": exceeded,
        "reference_check": reference_check,
        "candidate_changed_percent": changed_percent,
        "candidate_sha256": hashlib.sha256(
            canonical_cidr_text(candidate).encode()).hexdigest(),
        "published_added_addresses": str(_addresses(_subtract(output, old))) if old else "0",
        "published_removed_addresses": str(_addresses(_subtract(old, output))) if old else "0",
        "pending_added_addresses": str(_addresses(pending_added)),
        "pending_removed_addresses": str(_addresses(pending_removed)),
    }


def coverage_change(
    previous: Iterable[Rule] | None,
    current: Iterable[Rule],
    threshold_percent: int | float | str,
) -> dict[str, Any]:
    """Compare old/new address coverage and apply a per-family breaker.

    The percentage uses the symmetric address-space difference divided by the
    previous coverage. This catches replacements with an unchanged total size
    while ignoring equivalent CIDR splitting and aggregation.
    """

    current = tuple(current)
    previous_rules = tuple(previous) if previous is not None else None
    threshold = Decimal(str(threshold_percent))
    if threshold <= 0:
        raise ValueError("CN-IP breaker threshold must be positive")

    families: dict[str, Any] = {}
    exceeded = False
    for version in (4, 6):
        new = _coverage(current, version)
        if not new:
            raise ValueError(f"Current CN-IP window is missing IPv{version}")
        if previous_rules is None:
            families[f"ipv{version}"] = {
                "baseline_available": False,
                "current_addresses": str(_addresses(new)),
                "changed_addresses": None,
                "changed_percent": None,
                "exceeded": False,
            }
            continue

        old = _coverage(previous_rules, version)
        if not old:
            raise ValueError(f"Previous CN-IP window is missing IPv{version}")
        added = _subtract(new, old)
        removed = _subtract(old, new)
        previous_addresses = _addresses(old)
        current_addresses = _addresses(new)
        added_addresses = _addresses(added)
        removed_addresses = _addresses(removed)
        changed_addresses = added_addresses + removed_addresses
        changed_percent = Decimal(changed_addresses * 100) / Decimal(previous_addresses)
        family_exceeded = changed_percent > threshold
        exceeded = exceeded or family_exceeded
        families[f"ipv{version}"] = {
            "baseline_available": True,
            "previous_addresses": str(previous_addresses),
            "current_addresses": str(current_addresses),
            "added_addresses": str(added_addresses),
            "removed_addresses": str(removed_addresses),
            "changed_addresses": str(changed_addresses),
            "changed_percent": float(round(changed_percent, 6)),
            "exceeded": family_exceeded,
        }

    return {
        "comparison": "symmetric address-space difference, not textual CIDR equality",
        "threshold_percent": float(threshold),
        "exceeded": exceeded,
        "families": families,
    }
