from __future__ import annotations

import hashlib
import ipaddress
from typing import Any, Iterable

from .model import Rule


Interval = tuple[int, int]
DIFFERENCE_SAMPLE_LIMIT = 100


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


def _difference_report(intervals: list[Interval], version: int) -> dict[str, Any]:
    cidrs = _cidrs(intervals, version)
    digest = hashlib.sha256(
        "".join(f"{cidr}\n" for cidr in cidrs).encode("utf-8")
    ).hexdigest()
    return {
        "count": len(cidrs),
        "sha256": digest,
        "truncated": len(cidrs) > DIFFERENCE_SAMPLE_LIMIT,
        "cidrs": cidrs[:DIFFERENCE_SAMPLE_LIMIT],
    }


def compare_cn_coverage(
    primary: Iterable[Rule],
    reference: Iterable[Rule],
    *,
    reference_versions: tuple[int, ...] = (4, 6),
    independent: bool = False,
) -> dict[str, Any]:
    primary, reference = tuple(primary), tuple(reference)
    if any(rule.kind not in {"ipcidr", "ipcidr6"} for rule in (*primary, *reference)):
        raise ValueError("CN IP cross-validation requires only IP rules")
    families = {}
    for version, kind in ((4, "ipcidr"), (6, "ipcidr6")):
        left, right = _coverage(primary, version), _coverage(reference, version)
        if not left:
            raise ValueError(f"CN IP primary source requires IPv{version}")
        if version not in reference_versions:
            families[f"ipv{version}"] = {
                "reference_available": False,
                "equal_coverage": None,
                "primary_rule_count": sum(rule.kind == kind for rule in primary),
                "reference_rule_count": 0,
                "primary_addresses": str(_addresses(left)),
                "reference_addresses": None,
                "common_addresses": None,
                "primary_only_cidrs": None,
                "reference_only_cidrs": None,
            }
            continue
        if not right:
            raise ValueError(f"CN IP cross-validation requires IPv{version} in both sources")
        left_only, right_only = _subtract(left, right), _subtract(right, left)
        left_report = _difference_report(left_only, version)
        right_report = _difference_report(right_only, version)
        families[f"ipv{version}"] = {
            "reference_available": True,
            "equal_coverage": not left_only and not right_only,
            "primary_rule_count": sum(rule.kind == kind for rule in primary),
            "reference_rule_count": sum(rule.kind == kind for rule in reference),
            # Strings preserve exact IPv6 counts in JavaScript/JSON consumers.
            "primary_addresses": str(_addresses(left)),
            "reference_addresses": str(_addresses(right)),
            "common_addresses": str(_addresses(left) - _addresses(left_only)),
            "primary_only_cidr_count": left_report["count"],
            "primary_only_cidrs_sha256": left_report["sha256"],
            "primary_only_cidrs_truncated": left_report["truncated"],
            "primary_only_cidrs": left_report["cidrs"],
            "reference_only_cidr_count": right_report["count"],
            "reference_only_cidrs_sha256": right_report["sha256"],
            "reference_only_cidrs_truncated": right_report["truncated"],
            "reference_only_cidrs": right_report["cidrs"],
        }
    return {
        "schema": 1,
        "status": (
            "match"
            if all(families[f"ipv{version}"]["equal_coverage"] for version in reference_versions)
            else "differs"
        ),
        "comparison": "address coverage, not textual CIDR equality",
        "independent": independent,
        "note": "Reference availability is reported separately for each IP family.",
        "families": families,
    }
