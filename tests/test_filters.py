import re
from pathlib import Path

from proxyrules.config import load_project_config
from proxyrules.filters import build_filters


ROOT = Path(__file__).resolve().parents[1]


def _filters():
    return build_filters(load_project_config(ROOT)["policies"])


def test_us_filter_matches_bounded_code_but_not_russia() -> None:
    pattern = _filters()["regions"]["United States"]["select"]
    assert re.fullmatch(pattern, "Premium US01")
    assert re.fullmatch(pattern, "🇺🇸 Los Angeles")
    assert not re.fullmatch(pattern, "RUSSIA 01")


def test_taiwan_filter_does_not_use_china_flag() -> None:
    pattern = _filters()["regions"]["Taiwan"]["select"]
    assert re.fullmatch(pattern, "🇹🇼 TW02")
    assert not re.fullmatch(pattern, "🇨🇳 China 01")


def test_auto_excludes_high_multiplier_but_fallback_keeps_it() -> None:
    filters = _filters()
    assert not re.fullmatch(filters["auto"], "Hong Kong 2x")
    assert re.fullmatch(filters["fallback"], "Hong Kong 2x")
