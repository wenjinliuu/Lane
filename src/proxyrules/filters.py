from __future__ import annotations

from typing import Any


def region_filter(region_pattern: str) -> str:
    """Match a region using positive terms only."""

    return rf"(?i)^.*(?:{region_pattern}).*$"


def build_filters(policies: dict[str, Any]) -> dict[str, Any]:
    return {
        "manual": ".+",
        "regions": {
            region["name"]: region_filter(region["pattern"])
            for region in policies["regions"]
        },
    }
