from __future__ import annotations

import ipaddress
import re
from typing import Any

from .model import Rule
from .v2fly import DomainListError, parse_cidr_text


def text_source_ids(entry: dict[str, Any]) -> list[str]:
    if "text_source" in entry and "text_sources" in entry:
        raise ValueError("Use text_source or text_sources, not both")
    if "text_source" in entry:
        return [entry["text_source"]]
    return list(entry.get("text_sources", []))


def parse_dnsmasq_domains(text: str, source: str) -> list[Rule]:
    """Extract suffixes only; never import upstream DNS servers or DNS actions."""
    rules: list[Rule] = []
    label = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\Z")
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        # A trailing comment may follow whitespace. '#' inside a DNS target is
        # a port separator, so do not strip it as a comment.
        line = re.split(r"\s+#", line, maxsplit=1)[0].strip()
        match = re.fullmatch(r"server=/([^\s]+)/([^/\s]+)", line)
        if not match:
            raise DomainListError(f"{source}:{number}: unsupported dnsmasq directive")
        for name in match[1].split("/"):
            # dnsmasq treats /.example.com/ like /example.com/. Wildcard and
            # unqualified-domain syntax is deliberately rejected, not widened.
            domain = name.removeprefix(".").removesuffix(".").lower()
            labels = domain.split(".")
            if (len(domain) > 253 or len(labels) < 2
                    or any(not label.fullmatch(part) for part in labels)):
                raise DomainListError(f"{source}:{number}: invalid domain {name!r}")
            rules.append(Rule("domain", domain, source=source))
    return rules


def parse_text_source(text: str, source_id: str, spec: dict[str, Any]) -> list[Rule]:
    source_format = spec.get("format", "cidr")
    if source_format == "dnsmasq":
        rules = parse_dnsmasq_domains(text, source_id)
    elif source_format == "cidr":
        rules = parse_cidr_text(text, source_id)
        for rule in rules:
            network = ipaddress.ip_network(rule.value)
            if network.prefixlen == 0:
                raise DomainListError(f"{source_id}: default routes are not allowed")
            if spec.get("ip_version") not in (None, network.version):
                raise DomainListError(f"{source_id}: unexpected IPv{network.version} prefix")
        expected_versions = spec.get("ip_versions")
        if expected_versions is not None:
            versions = {ipaddress.ip_network(rule.value).version for rule in rules}
            if versions != set(expected_versions):
                raise DomainListError(f"{source_id}: expected IP families {expected_versions}")
    else:
        raise DomainListError(f"{source_id}: unsupported format {source_format!r}")
    if not rules:
        raise DomainListError(f"{source_id}: empty rule source")
    return rules
