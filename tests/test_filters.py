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
    assert not re.fullmatch(filters["United States"], "美西 01")
    assert not re.fullmatch(filters["Taiwan"], "台灣 01")


def test_region_filters_do_not_exclude_multiplier_or_status_words() -> None:
    pattern = _filters()["regions"]["United States"]
    assert re.fullmatch(pattern, "US 10x")
    assert re.fullmatch(pattern, "US 维护")


def test_manual_keeps_every_imported_node() -> None:
    pattern = _filters()["manual"]
    assert re.fullmatch(pattern, "剩余流量 100 GB")
    assert re.fullmatch(pattern, "官网订阅信息")
