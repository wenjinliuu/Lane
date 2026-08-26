from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from .compiler import compile_rulesets
from .config import load_project_config, validate_config
from .render import render_all, write_json_if_changed
from .upstream import (
    UpstreamError,
    fetch_text_source,
    prepare_git_source,
    read_git_revision,
)
from .validate import validate_generated
from .v2fly import DomainListRepository


def _directory_digest(path: Path) -> str:
    digest = hashlib.sha256()
    for file_path in sorted(item for item in path.rglob("*") if item.is_file()):
        digest.update(file_path.relative_to(path).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(file_path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _external_v2fly(path: Path) -> tuple[Path, str]:
    path = path.resolve()
    data_dir = path / "data" if (path / "data").is_dir() else path
    repository_root = path if (path / ".git").exists() else path.parent
    try:
        revision = read_git_revision(repository_root)
    except UpstreamError:
        revision = f"sha256:{_directory_digest(data_dir)}"
    return data_dir, revision


def build_project(
    root: Path,
    *,
    cache_dir: Path | None = None,
    upstream_dir: Path | None = None,
    refresh: bool = False,
    offline: bool = False,
) -> dict[str, Any]:
    root = root.resolve()
    cache_dir = (cache_dir or root / ".cache").resolve()
    config = load_project_config(root)
    validate_config(config)

    sources = config["sources"]["sources"]
    if upstream_dir:
        data_dir, v2fly_revision = _external_v2fly(upstream_dir)
    else:
        data_dir, v2fly_revision = prepare_git_source(
            sources["v2fly"], cache_dir, refresh=refresh, offline=offline
        )

    text_sources: dict[str, str] = {}
    text_metadata: dict[str, Any] = {}
    for source_id, source in sources.items():
        if source.get("kind") != "text":
            continue
        content, digest = fetch_text_source(
            source_id,
            source,
            cache_dir,
            refresh=refresh,
            offline=offline,
        )
        text_sources[source_id] = content
        text_metadata[source_id] = {
            "url": source["url"],
            "sha256": digest,
        }

    repository = DomainListRepository(data_dir)
    rulesets = compile_rulesets(
        root,
        config["rulesets"]["rulesets"],
        repository,
        text_sources,
    )
    render_report = render_all(
        root,
        config["project"],
        config["policies"],
        config["icons"],
        rulesets,
    )

    metadata = {
        "schema": 1,
        "project": config["project"]["project"]["repository"],
        "sources": {
            "v2fly": {
                "repository": sources["v2fly"]["repository"],
                "revision": v2fly_revision,
            },
            **text_metadata,
        },
        "rulesets": [
            {
                "id": ruleset.id,
                "policy": ruleset.policy,
                "rules": len(ruleset.rules),
                "kinds": {
                    kind: sum(1 for rule in ruleset.rules if rule.kind == kind)
                    for kind in sorted({rule.kind for rule in ruleset.rules})
                },
            }
            for ruleset in rulesets
        ],
    }
    write_json_if_changed(root / "dist" / "metadata.json", metadata)
    write_json_if_changed(root / "dist" / "report.json", render_report)
    validate_generated(root, config)
    return {"metadata": metadata, "report": render_report}
