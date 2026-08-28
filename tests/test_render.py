from pathlib import Path

import yaml

from proxyrules.config import load_project_config, validate_config
from proxyrules.model import Rule
from proxyrules.render import CONFIG_FILENAMES, PROFILE_HEADER, SUBSCRIPTION_PLACEHOLDER, _with_stable_update_time, render_rule
from proxyrules.validate import validate_generated


ROOT = Path(__file__).resolve().parents[1]


def test_rule_rendering_capabilities() -> None:
    regex = Rule("regexp", r"^example\\.com$")
    assert render_rule(regex, "stash") == r"DOMAIN-REGEX,^example\\.com$"
    assert render_rule(regex, "loon") is None
    assert render_rule(regex, "shadowrocket") is None
    cidr = Rule("ipcidr", "149.154.160.0/20")
    assert render_rule(cidr, "loon", no_resolve=True).endswith(",no-resolve")


def test_checked_in_outputs_are_valid_and_have_no_reject() -> None:
    config = load_project_config(ROOT)
    validate_config(config)
    validate_generated(ROOT, config)
    generated = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (ROOT / "dist").rglob("*")
        if path.is_file() and path.suffix in {".yaml", ".conf", ".list"}
    )
    assert "REJECT" not in generated.upper()

    main_configs = [ROOT / "dist" / target / filename
                    for target, filename in CONFIG_FILENAMES.items()]
    for path in main_configs:
        text = path.read_text(encoding="utf-8")
        assert text.startswith(
            PROFILE_HEADER +
            "# Last updated: "
        )
    main_text = "\n".join(
        path.read_text(encoding="utf-8") for path in main_configs
    )
    assert all(word not in main_text for word in ("剩余", "到期", "官网", "客服"))

    stash_text = main_configs[0].read_text(encoding="utf-8")
    loon_text = main_configs[1].read_text(encoding="utf-8")
    shadow_text = main_configs[2].read_text(encoding="utf-8")
    stash = yaml.safe_load(stash_text)
    assert stash["proxy-providers"]["Subscription1"]["url"] == SUBSCRIPTION_PLACEHOLDER
    assert "Stash / Clash" in stash_text
    assert "Loon 格式" in loon_text
    assert "添加节点订阅" not in shadow_text
    assert "US Auto" in stash_text and "US Manual" in stash_text
    assert "Fallback" not in main_text
    assert "South Korea" not in main_text

    service_names = config["policies"]["service_groups"]
    region_names = [
        name
        for region in config["policies"]["regions"]
        for name in (region["auto_name"], region["manual_name"])
    ]
    expected_group_names = ["Manual", *service_names, *region_names]
    assert [group["name"] for group in stash["proxy-groups"]] == expected_group_names

    loon_group_block = loon_text.split("[Proxy Group]\n", 1)[1].split(
        "\n[Remote Rule]", 1
    )[0]
    assert [
        line.split(" = ", 1)[0]
        for line in loon_group_block.splitlines()
        if " = " in line
    ] == expected_group_names

    shadow_group_block = shadow_text.split("[Proxy Group]\n", 1)[1].split(
        "\n[Rule]", 1
    )[0]
    assert [
        line.split(" = ", 1)[0]
        for line in shadow_group_block.splitlines()
        if " = " in line
    ] == expected_group_names

    expected_icons = {
        "Google": "Google_Search.png",
        "TW Auto": "China.png",
        "TW Manual": "China.png",
        "Gaming": "Steam.png",
        "Social": "X.png",
        "Streaming": "ForeignMedia.png",
        "Crypto": "Cryptocurrency_3.png",
        "Brokerage": "Magic.png",
        "Schwab": "SSID_1.png",
    }
    for group in stash["proxy-groups"]:
        if filename := expected_icons.get(group["name"]):
            assert group["icon"].endswith(f"/{filename}")


def test_update_time_is_preserved_when_content_is_unchanged(tmp_path: Path) -> None:
    path = tmp_path / "config.conf"
    body = PROFILE_HEADER + "value=one\n"
    first = _with_stable_update_time(path, body)
    path.write_text(first, encoding="utf-8")

    assert "# Last updated: " in first
    assert _with_stable_update_time(path, body) == first

    changed = _with_stable_update_time(path, body.replace("one", "two"))
    assert "value=two" in changed
    assert changed != first
