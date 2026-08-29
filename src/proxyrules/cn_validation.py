from __future__ import annotations

import ipaddress
from typing import Any, Iterable

from .model import Rule


Interval = tuple[int, int]


def _coverage(rules: Iterable[Rule], version: int) -> list[Interval]:
    intervals = sorted(
        (int(net.network_address), int(net.broadcast_address))
        for rule in rules
        if (net := ipaddress.ip_network(rule.value)).version == version
    )
    merged: list[Interval] = []
    for start, end in intervals:
        if merged and start <= merged[-1][1] + 1:
            merged[-1] = merged[-1][0], max(end, merged[-1][1])
        else:
            merged.append((start, end))
    return merged


def _subtract(left: list[Interval], right: list[Interval]) -> list[Interval]:
    """Subtract sorted disjoint intervals without enumerating IPv6 addresses."""
    output: list[Interval] = []
    index = 0
    for start, end in left:
        while index < len(right) and right[index][1] < start:
            index += 1
        cursor = start
        other = index
        while other < len(right) and right[other][0] <= end:
            right_start, right_end = right[other]
            if right_start > cursor:
                output.append((cursor, right_start - 1))
            cursor = max(cursor, right_end + 1)
            if cursor > end:
                break
            other += 1
        if cursor <= end:
            output.append((cursor, end))
    return output


def _addresses(intervals: list[Interval]) -> int:
    return sum(end - start + 1 for start, end in intervals)


def _cidrs(intervals: list[Interval], version: int) -> list[str]:
    address_type = ipaddress.IPv4Address if version == 4 else ipaddress.IPv6Address
    return [str(net) for start, end in intervals
            for net in ipaddress.summarize_address_range(address_type(start), address_type(end))]


def compare_cn_coverage(primary: Iterable[Rule], reference: Iterable[Rule]) -> dict[str, Any]:
    primary, reference = tuple(primary), tuple(reference)
    if any(rule.kind not in {"ipcidr", "ipcidr6"} for rule in (*primary, *reference)):
        raise ValueError("CN IP cross-validation requires only IP rules")
    families = {}
    for version, kind in ((4, "ipcidr"), (6, "ipcidr6")):
        left, right = _coverage(primary, version), _coverage(reference, version)
        if not left or not right:
            raise ValueError(f"CN IP cross-validation requires IPv{version} in both sources")
        left_only, right_only = _subtract(left, right), _subtract(right, left)
        families[f"ipv{version}"] = {
            "equal_coverage": not left_only and not right_only,
            "primary_rule_count": sum(rule.kind == kind for rule in primary),
            "reference_rule_count": sum(rule.kind == kind for rule in reference),
            # Strings preserve exact IPv6 counts in JavaScript/JSON consumers.
            "primary_addresses": str(_addresses(left)),
            "reference_addresses": str(_addresses(right)),
            "common_addresses": str(_addresses(left) - _addresses(left_only)),
            "primary_only_cidrs": _cidrs(left_only, version),
            "reference_only_cidrs": _cidrs(right_only, version),
        }
    return {
        "schema": 1,
        "license": "CC-BY-SA-4.0",
        "status": "match" if all(f["equal_coverage"] for f in families.values()) else "differs",
        "comparison": "address coverage, not textual CIDR equality",
        "independent": False,
        "note": (
            "Loyalsoldier CN data also derives from gaoyifan/china-operator-ip. "
            "Differences may reflect publication timing or processing; no union, "
            "intersection or automatic source replacement is applied to routing."
        ),
        "families": families,
    }
