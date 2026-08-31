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


def test_region_filters_reject_cities_transit_shorthands_and_single_chars() -> None:
    filters = _filters()["regions"]
    rejected = {
        "Japan": ["沪日中转01", "东京 Premium", "Osaka-01", "日 01"],
        "Hong Kong": ["深港IEPL 03", "港 01"],
        "United States": ["洛杉矶 GIA", "美西 01", "美 01"],
        "Singapore": ["杭新 IPLC", "新 01"],
        "Taiwan": ["台北 家宽", "彰化 中华电信", "新北 IPLC", "台 01", "臺 01"],
    }
    for region, names in rejected.items():
        for name in names:
            assert not re.fullmatch(filters[region], name), name


def test_singapore_accepts_lion_exception_without_claiming_bare_new() -> None:
    filters = _filters()["regions"]
    assert not re.fullmatch(filters["Singapore"], "新北 IPLC")
    assert re.fullmatch(filters["Singapore"], "狮城 BGP")
    assert re.fullmatch(filters["Singapore"], "獅 01")


def test_region_filters_do_not_exclude_multiplier_or_status_words() -> None:
    pattern = _filters()["regions"]["United States"]
    assert re.fullmatch(pattern, "US 10x")
    assert re.fullmatch(pattern, "US 维护")


def test_manual_keeps_every_imported_node() -> None:
    pattern = _filters()["manual"]
    assert re.fullmatch(pattern, "剩余流量 100 GB")
    assert re.fullmatch(pattern, "官网订阅信息")
