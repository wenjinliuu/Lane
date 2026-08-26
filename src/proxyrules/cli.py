from __future__ import annotations

import argparse
import json
from pathlib import Path

from .build import build_project
from .config import load_project_config, validate_config
from .validate import validate_generated


def _default_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="proxyrules",
        description="Generate Stash, Loon, and Shadowrocket routing configurations.",
    )
    parser.add_argument("--root", type=Path, default=_default_root())
    commands = parser.add_subparsers(dest="command", required=True)

    build = commands.add_parser("build", help="Fetch sources and generate dist/")
    build.add_argument("--cache-dir", type=Path)
    build.add_argument("--upstream-dir", type=Path)
    build.add_argument("--refresh", action="store_true")
    build.add_argument("--offline", action="store_true")

    commands.add_parser("check", help="Validate the manifest and generated files")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    root = args.root.resolve()
    if args.command == "build":
        result = build_project(
            root,
            cache_dir=args.cache_dir,
            upstream_dir=args.upstream_dir,
            refresh=args.refresh,
            offline=args.offline,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    config = load_project_config(root)
    validate_config(config)
    validate_generated(root, config)
    print("ProxyRules configuration and generated outputs are valid.")
    return 0
