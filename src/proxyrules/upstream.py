from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
import subprocess
import tempfile
import urllib.request
import warnings
from pathlib import Path
from typing import Any

from .cn_window import (
    canonical_cidr_text,
    coverage_change,
    coverage_stats,
    stable_window_rules,
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
        )
    except (OSError, subprocess.CalledProcessError) as exc:
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
            or metadata.get("window_days") != source.get("window_days", 7)
            or metadata.get("minimum_presence_days") != source.get("minimum_presence_days", 5)
            or metadata.get("breaker_percent") != float(source.get("breaker_percent", 1))):
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
    raise UpstreamError(
        f"Git history contains only {len(revisions)} distinct snapshot days; "
        f"{window_days} are required"
    )


def prepare_cidr_history_source(
    source_id: str,
    source: dict[str, Any],
    cache_dir: Path,
    refresh: bool,
    offline: bool,
    previous_rules: tuple[Rule, ...] | None = None,
    accept_breaker_sha256: str | None = None,
) -> PreparedHistorySource:
    """Build a stable CIDR source from validated daily git snapshots.

    The repository is cloned into a temporary staging directory. Only after all
    snapshots, both address families, the stable window, and the breaker pass is
    a single cache artifact atomically replaced. A failed candidate therefore
    cannot poison the last-known-good cache.
    """

    target = cache_dir / "history" / f"{source_id}.json"
    if accept_breaker_sha256 is not None:
        accept_breaker_sha256 = accept_breaker_sha256.lower()
        if (len(accept_breaker_sha256) != 64
                or any(character not in "0123456789abcdef"
                       for character in accept_breaker_sha256)):
            raise UpstreamError("CN-IP approval must be an exact SHA256 digest")
    if offline:
        if not target.exists():
            raise UpstreamError(f"No cached history source for {source_id} in offline mode")
        return _load_history_cache(target, source_id, source)
    if target.exists() and not refresh:
        return _load_history_cache(target, source_id, source)

    repository_url = source["repository"]
    ref = source.get("ref", "master")
    window_days = int(source.get("window_days", 7))
    minimum_days = int(source.get("minimum_presence_days", 5))
    history_depth = int(source.get("history_depth", max(32, window_days * 4)))
    threshold = source.get("breaker_percent", 1)
    files = source.get("files", {})
    if files != {"ipv4": "china.txt", "ipv6": "china6.txt"}:
        raise UpstreamError(f"Unexpected CN-IP history files for {source_id}")
    if history_depth < window_days:
        raise UpstreamError("CN-IP history depth must cover the full window")

    staging_root = cache_dir / "staging"
    staging_root.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.TemporaryDirectory(
            dir=staging_root, prefix=f"{source_id}-"
        ) as temporary_name:
            repository = Path(temporary_name) / "repository"
            try:
                _run(
                    [
                        "git",
                        "clone",
                        "--branch",
                        ref,
                        "--single-branch",
                        "--depth",
                        str(history_depth),
                        repository_url,
                        str(repository),
                    ]
                )
            except UpstreamError:
                if not target.exists():
                    raise
                warnings.warn(
                    f"Unable to refresh {source_id}; using its cached stable window",
                    stacklevel=2,
                )
                return _load_history_cache(target, source_id, source)

            revisions = _daily_revisions(
                repository,
                [files["ipv4"], files["ipv6"]],
                window_days,
            )
            snapshots: list[tuple[Rule, ...]] = []
            snapshot_metadata: list[dict[str, Any]] = []
            for item in revisions:
                snapshot_rules: list[Rule] = []
                file_metadata: dict[str, Any] = {}
                for family, version in (("ipv4", 4), ("ipv6", 6)):
                    path = files[family]
                    content = _run(
                        ["git", "show", f"{item['revision']}:{path}"],
                        cwd=repository,
                    )
                    try:
                        parsed = parse_text_source(
                            content,
                            f"{source_id}@{item['date']}:{family}",
                            {"format": "cidr", "ip_version": version},
                        )
                    except ValueError as exc:
                        raise UpstreamError(
                            f"Invalid {family} snapshot for {source_id} on {item['date']}: {exc}"
                        ) from exc
                    snapshot_rules.extend(parsed)
                    file_metadata[family] = {
                        "path": path,
                        "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
                        "rules": len(parsed),
                    }
                snapshot = tuple(snapshot_rules)
                snapshots.append(snapshot)
                snapshot_metadata.append(
                    {
                        **item,
                        "files": file_metadata,
                        "coverage": coverage_stats(snapshot),
                    }
                )

            try:
                stable = stable_window_rules(snapshots, minimum_days, source_id)
                content = canonical_cidr_text(stable)
                parse_text_source(content, source_id, source)
                change = coverage_change(previous_rules, stable, threshold)
            except ValueError as exc:
                raise UpstreamError(f"Invalid stable window for {source_id}: {exc}") from exc
            digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
            accepted = bool(
                change["exceeded"] and accept_breaker_sha256 == digest
            )
            change["accepted"] = accepted
            change["approval_sha256"] = digest if accepted else None
            report = {
                "schema": 1,
                "source": {
                    "id": source_id,
                    "repository": repository_url,
                    "ref": ref,
                    "files": files,
                    "license": source.get("license"),
                },
                "window": {
                    "snapshot_days": window_days,
                    "minimum_presence_days": minimum_days,
                    "selection": "latest commit for each distinct UTC date",
                },
                "breaker": change,
                "snapshots": snapshot_metadata,
                "output": {
                    "sha256": digest,
                    "coverage": coverage_stats(stable),
                },
            }
            if change["exceeded"] and not accepted:
                failed = ", ".join(
                    f"{family}={details['changed_percent']}%"
                    for family, details in change["families"].items()
                    if details["exceeded"]
                )
                diagnostic = {
                    "schema": 1,
                    "status": "blocked",
                    "reason": "cn-ip-breaker",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "published_sha256": (
                        hashlib.sha256(
                            canonical_cidr_text(previous_rules).encode("utf-8")
                        ).hexdigest()
                        if previous_rules is not None else None
                    ),
                    "candidate_sha256": digest,
                    "approval_sha256": accept_breaker_sha256,
                    "source": {
                        "id": source_id,
                        "repository": repository_url,
                        "ref": ref,
                        "newest_revision": revisions[0]["revision"],
                        "oldest_revision": revisions[-1]["revision"],
                    },
                    "breaker": change,
                    "candidate_report": report,
                }
                diagnostics = cache_dir / "diagnostics"
                _atomic_write_bytes(
                    diagnostics / "lane-update-report.json",
                    json.dumps(diagnostic, ensure_ascii=False, indent=2).encode("utf-8") + b"\n",
                )
                _atomic_write_bytes(
                    diagnostics / f"cn-ip-candidate-{digest}.json",
                    json.dumps(
                        {"report": report, "content": content},
                        ensure_ascii=False,
                        indent=2,
                    ).encode("utf-8") + b"\n",
                )
                raise UpstreamError(
                    f"CN-IP breaker exceeded {change['threshold_percent']}% ({failed}); "
                    f"candidate SHA256 is {digest}; last-known-good output was preserved"
                )
            metadata = {
                "repository": repository_url,
                "ref": ref,
                "revision": revisions[0]["revision"],
                "sha256": digest,
                "license": source.get("license"),
                "window_days": window_days,
                "minimum_presence_days": minimum_days,
                "breaker_percent": float(change["threshold_percent"]),
                "snapshot_dates": [item["date"] for item in revisions],
                "window_report": "cn-ip-window.json",
            }
            artifact = {
                "schema": 1,
                "source_id": source_id,
                "content": content,
                "sha256": digest,
                "metadata": metadata,
                "report": report,
            }
            encoded = (
                json.dumps(artifact, ensure_ascii=False, indent=2).encode("utf-8")
                + b"\n"
            )
            return PreparedHistorySource(
                content,
                digest,
                metadata,
                report,
                cache_target=target,
                cache_content=encoded,
            )
    except OSError as exc:
        raise UpstreamError(f"Unable to stage {source_id}: {exc}") from exc
