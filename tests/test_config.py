from pathlib import Path

from proxyrules.config import load_project_config, validate_config


ROOT = Path(__file__).resolve().parents[1]


def test_manifest_invariants() -> None:
    config = load_project_config(ROOT)
    validate_config(config)
    policies = config["policies"]
    assert policies["service_options"][0] == "Manual"
    assert policies["service_groups"][-1] == "Final"
    assert all(name.isascii() for name in policies["service_groups"])
    assert all(region["name"].isascii() for region in policies["regions"])


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
