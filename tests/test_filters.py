import re
from pathlib import Path

from proxyrules.config import load_project_config
from proxyrules.filters import build_filters


ROOT = Path(__file__).resolve().parents[1]


def _filters():
    return build_filters(load_project_config(ROOT)["policies"])


def test_us_filter_matches_bounded_code_but_not_russia() -> None:
    pattern = _filters()["regions"]["United States"]
    assert re.fullmatch(pattern, "Premium US01")
    assert re.fullmatch(pattern, "🇺🇸 Los Angeles")
    assert re.fullmatch(pattern, "United States 02")
    assert not re.fullmatch(pattern, "RUSSIA 01")


def test_region_filters_use_only_the_settled_positive_terms() -> None:
    filters = _filters()["regions"]
    assert re.fullmatch(filters["Japan"], "日本 01")
    assert re.fullmatch(filters["Hong Kong"], "Hong Kong 02")
    assert re.fullmatch(filters["Taiwan"], "TW03")
    assert re.fullmatch(filters["Singapore"], "新加坡 04")
    assert not re.fullmatch(filters["United States"], "LAX 01")


def test_region_filters_match_city_names_and_transit_shorthands() -> None:
    """Subscriptions name nodes by city and by transit shorthand far more often
    than by country. Recognising only flags, country names and two-letter codes
    left every region group empty for such subscriptions."""

    filters = _filters()["regions"]
    expected = {
        "沪日中转01": "Japan",
        "广日 04": "Japan",
        "东京 Premium": "Japan",
        "Osaka-01": "Japan",
        "深港IEPL 03": "Hong Kong",
        "京港专线": "Hong Kong",
        "洛杉矶 GIA": "United States",
        "美西 01": "United States",
        "狮城 BGP": "Singapore",
        "杭新 IPLC": "Singapore",
        "台北 家宽": "Taiwan",
        "彰化 中华电信": "Taiwan",
        "台灣 01": "Taiwan",
        "新北 IPLC": "Taiwan",
    }
    for name, region in expected.items():
        assert re.fullmatch(filters[region], name), name


def test_singapore_does_not_claim_taiwanese_new_taipei() -> None:
    """新 alone would match 新北, so Singapore lists each transit shorthand."""

    filters = _filters()["regions"]
    assert not re.fullmatch(filters["Singapore"], "新北 IPLC")
    assert re.fullmatch(filters["Taiwan"], "新北 IPLC")


def test_region_filters_do_not_exclude_multiplier_or_status_words() -> None:
    pattern = _filters()["regions"]["United States"]
    assert re.fullmatch(pattern, "US 10x")
    assert re.fullmatch(pattern, "US 维护")


def test_manual_keeps_every_imported_node() -> None:
    pattern = _filters()["manual"]
    assert re.fullmatch(pattern, "剩余流量 100 GB")
    assert re.fullmatch(pattern, "官网订阅信息")
