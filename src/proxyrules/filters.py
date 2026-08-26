from __future__ import annotations

import re
from typing import Any


def _alternation(values: list[str]) -> str:
    return "|".join(re.escape(value) for value in values)


def exclusion_filter(values: list[str], extra_pattern: str | None = None) -> str:
    parts: list[str] = []
    if values:
        parts.append(_alternation(values))
    if extra_pattern:
        parts.append(extra_pattern)
    if not parts:
        return ".+"
    return rf"(?i)^(?!.*(?:{'|'.join(parts)})).+$"


def region_filter(region_pattern: str, excluded: list[str], extra_pattern: str | None = None) -> str:
    parts: list[str] = []
    if excluded:
        parts.append(_alternation(excluded))
    if extra_pattern:
        parts.append(extra_pattern)
    negative = rf"(?!.*(?:{'|'.join(parts)}))" if parts else ""
    return rf"(?i)^{negative}.*(?:{region_pattern}).*$"


def build_filters(policies: dict[str, Any]) -> dict[str, Any]:
    settings = policies["node_filters"]
    manual_exclude = list(settings.get("manual_exclude", []))
    auto_exclude = manual_exclude + list(settings.get("auto_exclude", []))
    fallback_exclude = manual_exclude + list(settings.get("fallback_exclude", []))
    high_multiplier = settings.get("high_multiplier_pattern")

    regions: dict[str, dict[str, str]] = {}
    for region in policies["regions"]:
        regions[region["name"]] = {
            "select": region_filter(region["pattern"], manual_exclude),
            "auto": region_filter(region["pattern"], auto_exclude, high_multiplier),
        }

    return {
        "manual": exclusion_filter(manual_exclude),
        "auto": exclusion_filter(auto_exclude, high_multiplier),
        "fallback": exclusion_filter(fallback_exclude),
        "regions": regions,
    }

