from __future__ import annotations

import hashlib
import json
import warnings
from pathlib import Path
from typing import Any

from .cn_window import canonical_cidr_text
from .compiler import CompiledRuleset, audit_rule_redundancy, compile_rulesets
from .cn_validation import compare_cn_coverage
from .config import load_project_config, validate_config
from .model import Rule
from .render import render_all, write_json_if_changed
from .text_sources import parse_text_source, text_source_ids
from .upstream import (
    PreparedHistorySource,
    UpstreamError,
    commit_history_source_cache,
    fetch_text_source,
    prepare_cidr_history_source,
    prepare_git_source,
    read_git_revision,
)
from .validate import validate_generated
from .v2fly import DomainListRepository, parse_cidr_text


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


def _previous_cn_window_rules(root: Path) -> tuple[Rule, ...] | None:
    """Read the checked-in last-known-good output used by fresh CI runners."""

    report_path = root / "dist" / "cn-ip-window.json"
    rules_path = next(
        (
            path
            for path in (
                root / "dist" / "stash" / "rules" / "cn-ip.list",
                root / "dist" / "stash" / "rules-full" / "cn-ip.list",
                root / "dist" / "stash" / "rules-profile" / "cn-ip.list",
            )
            if path.is_file()
        ),
        None,
    )
    if rules_path is None:
        return None
    try:
        values = []
        for line in rules_path.read_text(encoding="utf-8").splitlines():
            if line.startswith(("IP-CIDR,", "IP-CIDR6,")):
                values.append(line.split(",", 2)[1])
        rules = tuple(parse_cidr_text("\n".join(values), "previous_cn_ip"))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise UpstreamError(f"Invalid previous CN-IP window output: {exc}") from exc
    if report_path.is_file():
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
            if not isinstance(report, dict):
                raise TypeError("window report must be a mapping")
        except (OSError, json.JSONDecodeError, TypeError) as exc:
            raise UpstreamError(f"Invalid previous CN-IP window report: {exc}") from exc
        digest = hashlib.sha256(canonical_cidr_text(rules).encode("utf-8")).hexdigest()
        if (report.get("source", {}).get("id") != "cn_ip_primary"
                or report.get("output", {}).get("sha256") != digest):
            raise UpstreamError(
                "Previous CN-IP window report does not match its generated rules"
            )
    return rules


def build_project(
    root: Path,
    *,
    cache_dir: Path | None = None,
    upstream_dir: Path | None = None,
    refresh: bool = False,
    offline: bool = False,
    accept_cn_ip_sha256: str | None = None,
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
    history_reports: dict[str, dict[str, Any]] = {}
    prepared_history_sources: list[PreparedHistorySource] = []
    previous_cn_rules = _previous_cn_window_rules(root)
    for source_id, source in sources.items():
        if source.get("kind") == "text":
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
            if "license" in source:
                text_metadata[source_id]["license"] = source["license"]
        elif source.get("kind") == "git-history-cidr":
            prepared = prepare_cidr_history_source(
                source_id,
                source,
                cache_dir,
                refresh=refresh,
                offline=offline,
                previous_rules=(
                    previous_cn_rules if source_id == "cn_ip_primary" else None
                ),
                accept_breaker_sha256=accept_cn_ip_sha256,
            )
            text_sources[source_id] = prepared.content
            text_metadata[source_id] = prepared.metadata
            history_reports[source_id] = prepared.report
            prepared_history_sources.append(prepared)

    repository = DomainListRepository(data_dir)
    rulesets = compile_rulesets(
        root,
        config["rulesets"]["rulesets"],
        repository,
        text_sources,
        sources,
    )
    redundancy_audit = audit_rule_redundancy(rulesets)
    check = config["sources"]["cross_validation"]["cn_ip"]
    reference_ids = check["reference_sources"]
    primary = next(
        ruleset for ruleset in rulesets if ruleset.id == check["ruleset"]
    )
    reference = [rule for key in reference_ids
                 for rule in parse_text_source(text_sources[key], key, sources[key])]
    reference_versions = tuple(
        sorted({sources[source_id]["ip_version"] for source_id in reference_ids})
    )
    cn_validation = compare_cn_coverage(
        primary.rules,
        reference,
        reference_versions=reference_versions,
        independent=bool(check["independent"]),
    )
    primary_entry = next(
        entry
        for entry in config["rulesets"]["rulesets"]
        if entry["id"] == primary.id
    )
    cn_validation["primary_ruleset"] = primary.id
    cn_validation["sources"] = {
        "primary": {key: text_metadata[key] for key in text_source_ids(primary_entry)},
        "reference": {key: text_metadata[key] for key in reference_ids},
    }
    cn_validation["licenses"] = {
        "primary": sorted(
            {sources[key]["license"] for key in text_source_ids(primary_entry)}
        ),
        "reference": sorted({sources[key]["license"] for key in reference_ids}),
    }
    # The comparison report contains derived samples from the CC-BY-SA reference.
    cn_validation["license"] = "CC-BY-SA-4.0"
    cn_validation["note"] = (
        "misakaio/chnroutes2 is an independent BGP-derived IPv4 reference. "
        "It does not publish an IPv6 text list, so IPv6 is window-validated but "
        "has no independent reference in this report. Reference data is never "
        "merged into the routing output."
    )
    if cn_validation["status"] == "differs":
        warnings.warn(
            "CN IP differs from the independent misakaio IPv4 reference. "
            "The gaoyifan stable window remains primary; see dist/cn-ip-validation.json",
            stacklevel=2,
        )
    render_report = render_all(
        root,
        config["project"],
        config["policies"],
        config["icons"],
        rulesets,
    )

    def kinds(ruleset: CompiledRuleset) -> dict[str, int]:
        return {
            kind: sum(1 for rule in ruleset.rules if rule.kind == kind)
            for kind in sorted({rule.kind for rule in ruleset.rules})
        }

    metadata = {
        "schema": 3,
        "project": config["project"]["project"]["repository"],
        "artifacts": {
            "rules": "rules",
            "default_profiles_use": "rules",
            "deduplication": "exact-only",
        },
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
                "kinds": kinds(ruleset),
                "exact_duplicates_removed": ruleset.exact_duplicates_removed,
                "redundancy_audit": {
                    "within_parent_suffix_candidates": (
                        redundancy_audit[ruleset.id].within_parent_suffix
                    ),
                    "previous_ruleset_exact_candidates": (
                        redundancy_audit[ruleset.id].previous_exact
                    ),
                    "previous_ruleset_parent_suffix_candidates": (
                        redundancy_audit[ruleset.id].previous_parent_suffix
                    ),
                    "total_candidates": redundancy_audit[ruleset.id].total,
                },
            }
            for ruleset in rulesets
        ],
        "rule_optimization": {
            "exact_duplicate_removal": {
                "enabled": True,
                "removed": sum(
                    ruleset.exact_duplicates_removed for ruleset in rulesets
                ),
            },
            "parent_suffix_removal": False,
            "cross_ruleset_residual_removal": False,
        },
        "redundancy_audit": {
            "mode": "report-only",
            "within_parent_suffix_candidates": sum(
                audit.within_parent_suffix for audit in redundancy_audit.values()
            ),
            "previous_ruleset_exact_candidates": sum(
                audit.previous_exact for audit in redundancy_audit.values()
            ),
            "previous_ruleset_parent_suffix_candidates": sum(
                audit.previous_parent_suffix for audit in redundancy_audit.values()
            ),
            "total_candidates": sum(
                audit.total for audit in redundancy_audit.values()
            ),
            "note": (
                "Candidates are retained in every published ruleset; this audit "
                "does not change routing payloads."
            ),
        },
        "cross_validation": {
            "cn-ip": {"report": "cn-ip-validation.json", "status": cn_validation["status"],
                      "independent": bool(check["independent"])},
        },
    }
    if "cn_ip_primary" not in history_reports:
        raise UpstreamError("Missing CN-IP history report")
    write_json_if_changed(root / "dist" / "cn-ip-window.json", history_reports["cn_ip_primary"])
    write_json_if_changed(root / "dist" / "cn-ip-validation.json", cn_validation)
    write_json_if_changed(root / "dist" / "metadata.json", metadata)
    write_json_if_changed(root / "dist" / "report.json", render_report)
    validate_generated(root, config)
    for prepared in prepared_history_sources:
        commit_history_source_cache(prepared)
    return {"metadata": metadata, "report": render_report}
