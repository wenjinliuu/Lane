from pathlib import Path
import shutil

import pytest
import yaml

from proxyrules.build import build_project
from proxyrules.text_sources import parse_text_source
from proxyrules.upstream import UpstreamError


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("reference_down", [False, True])
def test_other_rules_publish_when_cn_download_fails(tmp_path, monkeypatch, reference_down):
    """Exercise build/render/validate with retained CN-IP on a fresh runner."""
    for name in ("config", "rules", "assets", "dist"):
        shutil.copytree(ROOT / name, tmp_path / name)
    upstream = tmp_path / "upstream"
    data = upstream / "data"
    data.mkdir(parents=True)
    entries = yaml.safe_load((tmp_path / "config/rulesets.yaml").read_text())["rulesets"]
    for index, name in enumerate(sorted({name for entry in entries for name in entry.get("v2fly", [])})):
        (data / name).write_text(f"service{index}.example\nmainland{index}.example @cn\n")

    def fetch(source_id, spec, *args, **kwargs):
        if source_id == "cn_ipv4_reference" and reference_down:
            raise UpstreamError("reference download unavailable")
        content = ("server=/apple.com.cn/114.114.114.114\n" if source_id == "apple_cn" else
                   "91.108.56.0/22\n2001:b28::/32\n" if source_id == "telegram_cidr" else
                   "1.12.0.0/14\n")
        import hashlib
        parse_text_source(content, source_id, spec)
        return content, hashlib.sha256(content.encode()).hexdigest()

    original = __import__("proxyrules.upstream", fromlist=["_run"])._run
    def run(command, **kwargs):
        if "clone" in command:
            raise UpstreamError("CN-IP download unavailable")
        return original(command, **kwargs)
    monkeypatch.setattr("proxyrules.upstream._run", run)
    monkeypatch.setattr("proxyrules.build.fetch_text_source", fetch)
    old_cn = (tmp_path / "dist/stash/rules/cn-ip.list").read_text()
    with pytest.warns(UserWarning):
        result = build_project(tmp_path, upstream_dir=upstream, refresh=True)
    assert (tmp_path / "dist/stash/rules/cn-ip.list").read_text() == old_cn
    assert "service" in (tmp_path / "dist/stash/rules/ai.list").read_text()
    assert result["metadata"]["sources"]["cn_ip_primary"]["update_status"] == "partial"
    assert result["metadata"]["cross_validation"]["cn-ip"]["status"] == (
        "unavailable" if reference_down else "differs")
