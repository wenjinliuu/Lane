from pathlib import Path

from proxyrules.config import load_project_config, validate_config
from proxyrules.model import Rule
from proxyrules.render import render_rule
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
