from collections import Counter
from pathlib import Path

from proxyrules.config import load_project_config, validate_config
from proxyrules.v2fly import parse_custom_file


ROOT = Path(__file__).resolve().parents[1]


def test_manifest_invariants() -> None:
    config = load_project_config(ROOT)
    validate_config(config)
    policies = config["policies"]
    assert policies["service_options"][0] == "Manual"
    assert policies["service_groups"][-1] == "Final"
    assert [item["name"] for item in policies["base_groups"]] == ["Manual"]
    assert [item["code"] for item in policies["regions"]] == [
        "US",
        "JP",
        "HK",
        "TW",
        "SG",
    ]
    assert all(name.isascii() for name in policies["service_groups"])
    assert all(region["name"].isascii() for region in policies["regions"])
    assert all(region["manual_name"].endswith(" Manual") for region in policies["regions"])
    assert not {"Auto", "Fallback", "Global", "South Korea"}.intersection(
        policies["service_options"]
    )


def test_crypto_is_exactly_four_selected_exchanges() -> None:
    config = load_project_config(ROOT)
    crypto = next(
        entry for entry in config["rulesets"]["rulesets"] if entry["id"] == "crypto"
    )
    assert crypto["v2fly"] == ["binance", "okx", "bybit"]
    custom = (ROOT / crypto["custom"]).read_text(encoding="utf-8")
    assert "domain:bitget.com" in custom


def test_no_adblock_or_download_policy() -> None:
    config = load_project_config(ROOT)
    ids = {entry["id"].lower() for entry in config["rulesets"]["rulesets"]}
    assert not ids.intersection(
        {"ads", "adblock", "advertising", "reject", "download", "game-download"}
    )


def test_broker_rules_are_split_between_brokerage_and_schwab() -> None:
    config = load_project_config(ROOT)
    rulesets = {entry["id"]: entry for entry in config["rulesets"]["rulesets"]}

    brokerage = rulesets["brokerage"]
    assert brokerage["policy"] == "Brokerage"
    assert brokerage["no_resolve"] is True
    brokerage_path = ROOT / brokerage["custom"]
    brokerage_custom = brokerage_path.read_text(encoding="utf-8")
    assert "domain:skytigris.cn" in brokerage_custom
    assert "full:geotest.lbkrs.com" in brokerage_custom
    assert "domain:moomoo.com" in brokerage_custom
    assert "ipcidr:1.14.242.0/23" in brokerage_custom
    brokerage_rules = parse_custom_file(brokerage_path)
    assert len(brokerage_rules) == 118
    assert Counter(rule.kind for rule in brokerage_rules) == {
        "domain": 44,
        "full": 11,
        "ipcidr": 63,
    }

    schwab = rulesets["schwab"]
    assert schwab["policy"] == "Schwab"
    schwab_custom = (ROOT / schwab["custom"]).read_text(encoding="utf-8")
    assert "domain:schwab.com" in schwab_custom
    assert "DIRECT" not in schwab_custom
    assert len(parse_custom_file(ROOT / schwab["custom"])) == 5
