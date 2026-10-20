from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
import hashlib
import json
import os
import subprocess
import tempfile
import urllib.request
import warnings
from pathlib import Path
from typing import Any

from .cn_validation import _addresses, _coverage
from .cn_window import (
    canonical_cidr_text,
    coverage_stats,
    select_family_update,
)
from .model import Rule
from .text_sources import parse_text_source


class UpstreamError(RuntimeError):
    pass


@dataclass(frozen=True)
class PreparedHistorySource:
    content: str
    digest: str
    metadata: dict[str, Any]
    report: dict[str, Any]
    cache_target: Path | None = None
    cache_content: bytes | None = None


def _run(command: list[str], cwd: Path | None = None) -> str:
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=120,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        detail = getattr(exc, "stderr", "") or str(exc)
        raise UpstreamError(f"Command failed: {' '.join(command)}\n{detail.strip()}") from exc
    return result.stdout.strip()


def _atomic_write_bytes(path: Path, content: bytes) -> None:
    """Replace one cache artifact atomically after its contents are validated."""

    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def commit_history_source_cache(prepared: PreparedHistorySource) -> None:
    """Commit a fully validated candidate to the last-known-good cache."""

    if prepared.cache_target is None and prepared.cache_content is None:
        return
    if prepared.cache_target is None or prepared.cache_content is None:
        raise UpstreamError("Incomplete staged history cache artifact")
    _atomic_write_bytes(prepared.cache_target, prepared.cache_content)


def prepare_git_source(
    source: dict[str, Any],
    cache_dir: Path,
    refresh: bool,
    offline: bool = False,
) -> tuple[Path, str]:
    target = cache_dir / "v2fly"
    repository = source["repository"]
    ref = source.get("ref", "master")
    if not target.exists() and offline:
        raise UpstreamError("No cached v2fly source is available in offline mode")
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        _run(
            [
                "git",
                "clone",
                "--depth",
                "1",
                "--branch",
                ref,
                repository,
                str(target),
            ]
        )
    elif refresh and not offline:
        _run(["git", "fetch", "--depth", "1", "origin", ref], cwd=target)
        _run(["git", "merge", "--ff-only", "FETCH_HEAD"], cwd=target)
    revision = _run(["git", "rev-parse", "HEAD"], cwd=target)
    return target / source.get("data_path", "data"), revision


def read_git_revision(repository_root: Path) -> str:
    return _run(["git", "rev-parse", "HEAD"], cwd=repository_root)


def fetch_text_source(
    source_id: str,
    source: dict[str, Any],
    cache_dir: Path,
    refresh: bool,
    offline: bool,
) -> tuple[str, str]:
    target = cache_dir / "text" / f"{source_id}.txt"
    if (refresh or not target.exists()) and not offline:
        request = urllib.request.Request(
            source["url"], headers={"User-Agent": "Lane/0.2"}
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                content = response.read()
        except OSError as exc:
            if not target.exists():
                raise UpstreamError(f"Unable to fetch {source_id}: {exc}") from exc
            warnings.warn(f"Unable to refresh {source_id}; using its cached source", stacklevel=2)
        else:
            # Invalid/empty downloads must never overwrite a last-known-good cache.
            try:
                parse_text_source(content.decode("utf-8"), source_id, source)
            except (UnicodeError, ValueError) as exc:
                raise UpstreamError(f"Invalid source {source_id}: {exc}") from exc
            if not target.exists() or target.read_bytes() != content:
                _atomic_write_bytes(target, content)
    if not target.exists():
        raise UpstreamError(f"No cached copy for {source_id}")
    content = target.read_text(encoding="utf-8")
    parse_text_source(content, source_id, source)
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    return content, digest


def _load_history_cache(
    target: Path,
    source_id: str,
    source: dict[str, Any],
) -> PreparedHistorySource:
    try:
        artifact = json.loads(target.read_text(encoding="utf-8"))
        if not isinstance(artifact, dict):
            raise TypeError("cache artifact must be a mapping")
        content = artifact["content"]
        digest = artifact["sha256"]
        metadata = artifact["metadata"]
        report = artifact["report"]
        if not isinstance(metadata, dict) or not isinstance(report, dict):
            raise TypeError("cache metadata and report must be mappings")
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise UpstreamError(f"Invalid cached history source {source_id}: {exc}") from exc
    if artifact.get("schema") != 1 or artifact.get("source_id") != source_id:
        raise UpstreamError(f"Invalid cached history source identity for {source_id}")
    if (metadata.get("repository") != source.get("repository")
            or metadata.get("ref") != source.get("ref", "master")
            or metadata.get("window_days") != source.get("window_days", 5)
            or metadata.get("minimum_presence_days") != source.get("minimum_presence_days", 3)
            or metadata.get("breaker_percent") != float(source.get("breaker_percent", 1))
            or metadata.get("confirmation_days") != source.get("confirmation_days", 7)
            or metadata.get("maximum_snapshot_age_days") != source.get("maximum_snapshot_age_days", 3)
            or metadata.get("minimum_coverage_ratio") != source.get("minimum_coverage_ratio", 0.5)):
        raise UpstreamError(f"Cached history parameters differ for {source_id}")
    if (not isinstance(content, str)
            or hashlib.sha256(content.encode("utf-8")).hexdigest() != digest):
        raise UpstreamError(f"Invalid cached history source digest for {source_id}")
    try:
        parse_text_source(content, source_id, source)
    except ValueError as exc:
        raise UpstreamError(f"Invalid cached history source {source_id}: {exc}") from exc
    report_output = report.get("output")
    if not isinstance(report_output, dict) or report_output.get("sha256") != digest:
        raise UpstreamError(f"History report digest differs from cached {source_id}")
    return PreparedHistorySource(content, digest, metadata, report)


def _daily_revisions(
    repository: Path,
    files: list[str],
    window_days: int,
) -> list[dict[str, str]]:
    log = _run(
        ["git", "log", "--format=%H%x09%cI", "--", *files],
        cwd=repository,
    )
    revisions: list[dict[str, str]] = []
    seen_days: set[str] = set()
    for line in log.splitlines():
        try:
            revision, committed_at = line.split("\t", 1)
            instant = datetime.fromisoformat(committed_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise UpstreamError(f"Invalid git history row: {line!r}") from exc
        day = instant.astimezone(timezone.utc).date().isoformat()
        if day in seen_days:
            continue
        seen_days.add(day)
        revisions.append(
            {"date": day, "revision": revision, "committed_at": committed_at}
        )
        if len(revisions) == window_days:
            return revisions
    return revisions


def prepare_cidr_history_source(
    source_id: str,
    source: dict[str, Any],
    cache_dir: Path,
    refresh: bool,
    offline: bool,
    previous_rules: tuple[Rule, ...] | None = None,
    previous_metadata: dict[str, Any] | None = None,
    today: date | None = None,
    reference_rules: tuple[Rule, ...] | None = None,
) -> PreparedHistorySource:
    """Rebuild observations from Git; isolate unhealthy IP families from publishing.

    Only a validated final build commits the staged cache. Fresh CI runners use
    checked-in dist as the baseline, never an ephemeral observation counter.
    """
    target = cache_dir / "history" / f"{source_id}.json"
    if offline or (target.exists() and not refresh):
        if not target.exists():
            raise UpstreamError(f"No cached history source for {source_id} in offline mode")
        return _load_history_cache(target, source_id, source)

    today = today or datetime.now(timezone.utc).date()
    window_days = int(source.get("window_days", 5))
    minimum_days = int(source.get("minimum_presence_days", 3))
    confirmation_days = int(source.get("confirmation_days", 7))
    history_depth = int(source.get("history_depth", 32))
    threshold = float(source.get("breaker_percent", 1))
    max_age = int(source.get("maximum_snapshot_age_days", 3))
    minimum_ratio = float(source.get("minimum_coverage_ratio", 0.5))
    if not (1 <= minimum_days <= window_days <= confirmation_days <= history_depth
            and threshold > 0 and max_age > 0 and 0 < minimum_ratio < 1):
        raise UpstreamError("Invalid CN-IP observation parameters")
    files = source.get("files", {})
    if files != {"ipv4": "china.txt", "ipv6": "china6.txt"}:
        raise UpstreamError(f"Unexpected CN-IP history files for {source_id}")

    previous_metadata = previous_metadata or {}
    snapshots: dict[int, list[tuple[Rule, ...]]] = {4: [], 6: []}
    dates: dict[int, list[str]] = {4: [], 6: []}
    errors: dict[int, list[dict[str, str]]] = {4: [], 6: []}
    snapshot_metadata: list[dict[str, Any]] = []
    revisions: list[dict[str, str]] = []
    source_error = None
    staging_root = cache_dir / "staging"
    staging_root.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.TemporaryDirectory(dir=staging_root, prefix=f"{source_id}-") as temporary:
            repository = Path(temporary) / "repository"
            _run(["git", "clone", "--branch", source.get("ref", "master"),
                  "--single-branch", "--depth", str(history_depth),
                  source["repository"], str(repository)])
            revisions = _daily_revisions(repository, list(files.values()), history_depth)
            for item in revisions:
                metadata: dict[str, Any] = {**item, "files": {}}
                for version in (4, 6):
                    family = f"ipv{version}"
                    try:
                        content = _run(["git", "show", f"{item['revision']}:{files[family]}"],
                                       cwd=repository)
                        parsed = tuple(parse_text_source(
                            content, f"{source_id}@{item['date']}:{family}",
                            {"format": "cidr", "ip_version": version},
                        ))
                        addresses = _addresses(_coverage(parsed, version))
                        old_addresses = (_addresses(_coverage(previous_rules, version))
                                         if previous_rules else 0)
                        # Syntactically valid truncated downloads are still unsafe.
                        if old_addresses and addresses < old_addresses * minimum_ratio:
                            raise ValueError("coverage below completeness floor")
                        age = (today - date.fromisoformat(item["date"])).days
                        if age < 0:
                            raise ValueError("snapshot is dated in the future")
                    except (UpstreamError, ValueError) as exc:
                        reason = str(exc)
                        errors[version].append({"date": item["date"], "reason": reason})
                        metadata["files"][family] = {"path": files[family], "error": reason}
                        continue
                    if len(snapshots[version]) < confirmation_days:
                        snapshots[version].append(parsed)
                        dates[version].append(item["date"])
                    metadata["files"][family] = {
                        "path": files[family],
                        "sha256": hashlib.sha256(content.encode()).hexdigest(),
                        "rules": len(parsed), "addresses": str(addresses),
                    }
                snapshot_metadata.append(metadata)
                # Invalid dates never count; search farther back for valid evidence.
                if all(len(snapshots[v]) >= confirmation_days for v in (4, 6)):
                    break
    except (UpstreamError, OSError) as exc:
        source_error = str(exc)

    output: list[Rule] = []
    families: dict[str, Any] = {}
    for version, kind in ((4, "ipcidr"), (6, "ipcidr6")):
        previous = (tuple(rule for rule in previous_rules if rule.kind == kind)
                    if previous_rules is not None else None)
        reason = source_error
        if not reason and not revisions:
            reason = "No dated upstream snapshots"
        if not reason and errors[version] and errors[version][0]["date"] == revisions[0]["date"]:
            reason = "Latest snapshot is invalid: " + errors[version][0]["reason"]
        if not reason and dates[version] and (
                today - date.fromisoformat(dates[version][0])).days > max_age:
            reason = "Latest valid snapshot is stale"
        if not reason:
            try:
                selected, decision = select_family_update(
                    previous, snapshots[version], version=version, source=source_id,
                    window_days=window_days, minimum_days=minimum_days,
                    confirmation_days=confirmation_days, threshold_percent=threshold,
                    reference=reference_rules if version == 4 else None,
                )
            except ValueError as exc:
                reason = str(exc)
        if reason:
            if not previous:
                raise UpstreamError(f"No valid baseline for IPv{version}: {reason}")
            selected = previous
            decision = {"status": "retained", "reason": reason,
                        "threshold_exceeded": False}
            warnings.warn(f"CN IPv{version} retained; {reason}", stacklevel=2)
        if not selected:
            raise UpstreamError(f"No output for CN IPv{version}")
        decision.update({
            "observation_dates": dates[version],
            "invalid_snapshots": errors[version],
            "baseline_sha256": (hashlib.sha256(canonical_cidr_text(previous).encode()).hexdigest()
                                if previous else None),
            "baseline_revision": previous_metadata.get("revision"),
            "output_sha256": hashlib.sha256(canonical_cidr_text(selected).encode()).hexdigest(),
        })
        families[f"ipv{version}"] = decision
        output.extend(selected)

    content = canonical_cidr_text(output)
    parse_text_source(content, source_id, source)
    digest = hashlib.sha256(content.encode()).hexdigest()
    partial = any(item["status"] in {"observing", "retained"} for item in families.values())
    report = {
        "schema": 2,
        "status": "partial" if partial else "updated",
        "source": {"id": source_id, "repository": source["repository"],
                   "ref": source.get("ref", "master"), "files": files,
                   "license": source.get("license")},
        "window": {"snapshot_days": window_days, "minimum_presence_days": minimum_days,
                   "selection": "latest commit for each distinct UTC date"},
        "recovery": {"confirmation_days": confirmation_days,
                     "threshold_percent": threshold,
                     "maximum_snapshot_age_days": max_age,
                     "minimum_coverage_ratio": minimum_ratio,
                     "families": families},
        "snapshots": snapshot_metadata,
        "output": {"sha256": digest, "coverage": coverage_stats(output)},
    }
    metadata = {
        "repository": source["repository"], "ref": source.get("ref", "master"),
        "revision": revisions[0]["revision"] if revisions else previous_metadata.get("revision"),
        "sha256": digest, "license": source.get("license"),
        "window_days": window_days, "minimum_presence_days": minimum_days,
        "breaker_percent": threshold, "confirmation_days": confirmation_days,
        "maximum_snapshot_age_days": max_age, "minimum_coverage_ratio": minimum_ratio,
        "snapshot_dates": [item["date"] for item in snapshot_metadata],
        "window_report": "cn-ip-window.json", "update_status": report["status"],
    }
    artifact = {"schema": 1, "source_id": source_id, "content": content,
                "sha256": digest, "metadata": metadata, "report": report}
    return PreparedHistorySource(
        content, digest, metadata, report, cache_target=target,
        cache_content=json.dumps(artifact, ensure_ascii=False, indent=2).encode() + b"\n",
    )
