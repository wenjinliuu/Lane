from pathlib import Path
import re
import shutil

import pytest
import yaml

from proxyrules.config import load_project_config
from proxyrules.render import (
    CONFIG_FILENAMES, STASH_ALL_NODES_GROUP, SUBSCRIPTION_PLACEHOLDER,
)
from proxyrules.validate import ValidationError, _section, validate_generated


ROOT = Path(__file__).resolve().parents[1]
URLS = [f"https://subscription{number}.example.com/nodes" for number in (1, 2, 3)]
NODE_INTERVAL = load_project_config(ROOT)["project"]["updates"]["node_interval"]


def _profile(target):
    return (ROOT / "dist" / target / CONFIG_FILENAMES[target]).read_text(encoding="utf-8")


@pytest.mark.parametrize("target", CONFIG_FILENAMES)
def test_plain_placeholder_and_service_guidance_at_top(target):
    text = _profile(target)
    heading = text.split("\n\n", 1)[0]
    assert "Brokerage：富途/Moomoo 保留域名与 IP 覆盖；老虎、长桥仅保留实测关键域名；嘉信规则并入本组" in heading
    assert "Crypto：仅 Binance、OKX、Bybit、Bitget" in heading
    assert "嘉信独立分流" not in heading
    assert "默认均为 Manual" in heading
    assert "不保证入金或交易结果" in heading
    assert "勿上传私人订阅" not in text
    if target in {"shadowrocket", "qx"}:
        assert SUBSCRIPTION_PLACEHOLDER not in text
        assert "多订阅" not in text
        if target == "qx":
            assert "应用内添加" in text
            assert "[server_remote]" not in text
    else:
        assert SUBSCRIPTION_PLACEHOLDER == "你的订阅地址"
        assert f'"{SUBSCRIPTION_PLACEHOLDER}"' not in text
        assert f"'{SUBSCRIPTION_PLACEHOLDER}'" not in text
        assert "多订阅" in text
        assert "示例链接" not in text
        assert "导入启用前" in heading
        active = [line for line in text.splitlines() if SUBSCRIPTION_PLACEHOLDER in line
                  and not line.lstrip().startswith(("#", ";", "//"))]
        assert len(active) == (2 if target == "egern" else 1)


def test_stash_optional_block_can_be_enabled_and_copied_with_valid_indentation():
    text = _profile("stash")
    original = yaml.safe_load(text)
    assert list(original["proxy-providers"]) == ["Subscription1"]
    match = re.search(r"(?m)^  # Subscription2:\n(?:  # .*\n)+", text)
    assert match is not None
    block = match.group()
    enabled = "".join(line.replace("  # ", "  ", 1) for line in block.splitlines(keepends=True))
    second = enabled.replace(SUBSCRIPTION_PLACEHOLDER, URLS[1])
    third = enabled.replace("Subscription2:", "Subscription3:", 1).replace(SUBSCRIPTION_PLACEHOLDER, URLS[2])
    edited = text.replace(f"url: {SUBSCRIPTION_PLACEHOLDER}", f"url: {URLS[0]}", 1)
    edited = edited.replace(block, second + third)
    parsed = yaml.safe_load(edited)
    providers = parsed["proxy-providers"]
    assert list(providers) == ["Subscription1", "Subscription2", "Subscription3"]
    for name, url in zip(providers, URLS):
        assert providers[name] == {**original["proxy-providers"]["Subscription1"], "url": url}
    assert parsed["proxy-groups"] == original["proxy-groups"]
    assert parsed["proxy-groups"][0]["proxies"][-1] == STASH_ALL_NODES_GROUP
    assert parsed["proxy-groups"][1]["name"] == STASH_ALL_NODES_GROUP
    assert parsed["proxy-groups"][1]["include-all"] is True
    for group in parsed["proxy-groups"][-10:]:
        assert group["include-all"] is True


def test_loon_additional_subscriptions_do_not_require_filter_changes():
    text = _profile("loon")
    assert _section(text, "Remote Proxy") == [f"Subscription1 = {SUBSCRIPTION_PLACEHOLDER}"]
    edited = text.replace(f"Subscription1 = {SUBSCRIPTION_PLACEHOLDER}", f"Subscription1 = {URLS[0]}")
    edited = edited.replace(
        f"# Subscription2 = {SUBSCRIPTION_PLACEHOLDER}",
        f"Subscription2 = {URLS[1]}\nSubscription3 = {URLS[2]}",
    )
    assert _section(edited, "Remote Proxy") == [
        f"Subscription{index} = {url}" for index, url in enumerate(URLS, 1)
    ]
    for section in ("Remote Filter", "Proxy Group"):
        assert _section(edited, section) == _section(text, section)


def test_qx_omits_private_subscription_resources_from_public_profile():
    text = _profile("qx")
    assert SUBSCRIPTION_PLACEHOLDER not in text
    assert "[server_remote]" not in text
    assert "[server_local]" not in text
    assert "应用内添加" in text
    assert re.findall(r"(?m)^\[([^\]]+)\]$", text) == [
        "general", "dns", "policy", "filter_remote", "filter_local"
    ]


def test_surge_hidden_subscriptions_are_expanded_through_manual():
    text = _profile("surge")
    groups = _section(text, "Proxy Group")
    commented = next(line for line in text.splitlines() if line.startswith("# Subscription2 = select,"))
    second = commented.removeprefix("# ").replace(SUBSCRIPTION_PLACEHOLDER, URLS[1])
    third = second.replace("Subscription2 =", "Subscription3 =").replace(URLS[1], URLS[2])
    edited = text.replace(groups[0], groups[0].replace(SUBSCRIPTION_PLACEHOLDER, URLS[0]), 1)
    edited = edited.replace(commented, second + "\n" + third)
    edited = edited.replace(
        "Node Pool = select,include-other-group=Subscription1,",
        'Node Pool = select,include-other-group="Subscription1,Subscription2,Subscription3",',
    )
    parsed = {line.split(" = ", 1)[0]: line.split(" = ", 1)[1]
              for line in _section(edited, "Proxy Group")}
    for index, url in enumerate(URLS, 1):
        assert parsed[f"Subscription{index}"] == (
            f"select,policy-path={url},update-interval={NODE_INTERVAL},hidden=true"
        )
    assert parsed["Node Pool"] == (
        'select,include-other-group="Subscription1,Subscription2,Subscription3",'
        'include-all-proxies=true,hidden=true'
    )
    assert "policy-path=" not in parsed["Node Pool"]
    policies = load_project_config(ROOT)["policies"]
    expected_visible = ["Manual", *policies["service_groups"], *[
        name for region in policies["regions"]
        for name in (region["surge_smart_name"], region["manual_name"])
    ]]
    assert [name for name, value in parsed.items() if "hidden=true" not in value] == expected_visible
    for region in policies["regions"]:
        for name in (region["surge_smart_name"], region["manual_name"]):
            assert "include-other-group=Node Pool," in parsed[name]
    assert 'include-other-group="Subscription1,Subscription2"' in text


def test_egern_urls_accept_additional_items_without_changing_region_groups():
    text = _profile("egern")
    original = yaml.safe_load(text)
    assert original["policy_groups"][0]["select"]["urls"] == [SUBSCRIPTION_PLACEHOLDER]
    assert original["policy_groups"][1]["select"]["urls"] == [SUBSCRIPTION_PLACEHOLDER]
    edited = text.replace(
        f"    - {SUBSCRIPTION_PLACEHOLDER}\n", f"    - {URLS[0]}\n", 2
    )
    edited = edited.replace(
        f"    # - {SUBSCRIPTION_PLACEHOLDER}\n",
        f"    - {URLS[1]}\n    - {URLS[2]}\n",
        2,
    )
    parsed = yaml.safe_load(edited)
    assert parsed["policy_groups"][0]["select"]["urls"] == URLS
    assert parsed["policy_groups"][1]["select"]["urls"] == URLS
    assert parsed["policy_groups"][0]["select"]["update_interval"] == NODE_INTERVAL
    assert parsed["policy_groups"][1]["select"]["update_interval"] == NODE_INTERVAL
    assert parsed["policy_groups"][2:] == original["policy_groups"][2:]


@pytest.mark.parametrize("target,old,new,error", [
    ("surge", "hidden=true\n", "hidden=false\n", "hidden source group"),
    ("surge", "Node Pool = select,include-other-group=Subscription1,",
     "Node Pool = select,include-other-group=Subscription2,", "Node Pool must expand"),
    ("egern", f"    - {SUBSCRIPTION_PLACEHOLDER}\n",
     f'    - "{SUBSCRIPTION_PLACEHOLDER}"\n', "must not be quoted"),
    ("loon", f"# Subscription2 = {SUBSCRIPTION_PLACEHOLDER}\n", "", "commented second"),
    ("qx", "\n[filter_remote]\n", "\n[server_remote]\n\n[filter_remote]\n",
     "omit subscription resources"),
])
def test_validator_rejects_subscription_template_regressions(tmp_path, target, old, new, error):
    shutil.copytree(ROOT / "dist", tmp_path / "dist")
    shutil.copytree(ROOT / "rules", tmp_path / "rules")
    shutil.copytree(ROOT / "assets/icons", tmp_path / "assets/icons")
    path = tmp_path / "dist" / target / CONFIG_FILENAMES[target]
    text = path.read_text(encoding="utf-8")
    assert old in text
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    with pytest.raises(ValidationError, match=error):
        validate_generated(tmp_path, load_project_config(ROOT))
