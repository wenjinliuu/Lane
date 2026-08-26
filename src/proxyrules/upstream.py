from __future__ import annotations

import hashlib
import subprocess
import urllib.request
from pathlib import Path
from typing import Any


class UpstreamError(RuntimeError):
    pass


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
            source["url"], headers={"User-Agent": "ProxyRules/0.1"}
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                content = response.read()
        except OSError as exc:
            if not target.exists():
                raise UpstreamError(f"Unable to fetch {source_id}: {exc}") from exc
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists() or target.read_bytes() != content:
                target.write_bytes(content)
    if not target.exists():
        raise UpstreamError(f"No cached copy for {source_id}")
    content = target.read_text(encoding="utf-8")
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    return content, digest
