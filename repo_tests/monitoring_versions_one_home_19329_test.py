# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Prometheus and Grafana versions have ONE home: the monitoring role's defaults (#19329).

Maintainer decision 2026-10-26: the compose values win -- Prometheus 2.53.0, Grafana 11.1.0.
Before, the VM fleet ran 2.48.0 / 10.2.0, compose ran 2.53.0 / 11.1.0, and two Ansible paths
installed Grafana ``latest``. CI already reads ``prometheus_version`` from the home to pin promtool.

Consumers that cannot read an Ansible role default -- the two compose stacks' image tags, the
``slm_manager`` role and the Grafana migration play -- carry ONE pinned copy each. This guard fails
when a copy differs from the home, when a version literal appears anywhere else in the compose,
infrastructure and Ansible trees, or when ``latest`` (or an untagged image) comes back.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

import pytest
from repo_tests._paths import repo_root
from repo_tests._reach import declare

_ROOT = repo_root()
_HOME = "autobot-slm-backend/ansible/roles/monitoring/defaults/main.yml"
_ROOTS = ("docker-compose.yml", "autobot-infrastructure", "autobot-slm-backend/ansible")
_SUFFIXES = (".yml", ".yaml", ".ini", ".sh")
#: Each shape that states a version. An image may carry a registry prefix, quotes, a digest or a
#: trailing comment; its tag is read whole (``${X:-10}`` or ``-ubuntu`` stays in and fails equality).
#: An untagged image, an unpinned ``apt-get install`` and ``latest`` read as ``latest``.
_SITE = re.compile(
    r"\$\{(?P<stool>PROMETHEUS|GRAFANA)_VERSION:[-=](?P<sv>[^}\s]+)\}"
    r"|(?P<etool>PROMETHEUS|GRAFANA)_VERSION\s*=\s*[\"']?(?P<ev>[^\s\"'#]+)"
    r"|(?P<tool>prometheus|grafana)_version\s*[:=]\s*[\"']?(?P<v>[\w.{}\s|]+?)[\"']?\s*(?:#.*)?$"
    r"|image:\s*[\"']?(?:[\w.-]+(?::\d+)?/)*(?:prom/(?P<itool>prometheus)|grafana/(?P<gtool>grafana)(?:-oss)?)"
    r"(?::v?(?P<iv>[^\s@\"'#]+))?(?:@\S+?)?[\"']?\s*(?:#.*)?$"
    r"|apt-get\s+install\b[^\n]*?\s[\"']?(?P<atool>prometheus|grafana)"
    r"(?:=(?P<av>[^\s\"'$][^\s\"']*))?[\"']?(?=\s|$)",
    re.MULTILINE,
)

#: Every file allowed to state a version, and how many statements it holds.
_PINNED = {
    (_HOME, "prometheus"): 1,
    (_HOME, "grafana"): 1,
    ("docker-compose.yml", "prometheus"): 1,
    ("docker-compose.yml", "grafana"): 1,
    ("autobot-infrastructure/shared/config/logging/loki/docker-compose-loki.yml", "grafana"): 1,
    ("autobot-slm-backend/ansible/roles/slm_manager/defaults/main.yml", "grafana"): 1,
    ("autobot-slm-backend/ansible/migrate-grafana-to-vm.yml", "grafana"): 1,
    ("autobot-infrastructure/shared/scripts/install-slm.sh", "prometheus"): 1,
    ("autobot-infrastructure/shared/scripts/install-slm.sh", "grafana"): 1,
}

#: A statement that may differ from the home, and the issue that owns it. install-slm.sh installs the
#: distribution's Prometheus package (no version to pin); whether that installer is still supported
#: is decided on #19262.
_KNOWN_EXCEPTIONS = {("autobot-infrastructure/shared/scripts/install-slm.sh", "prometheus", "latest"): "#19262"}


def _sources(root: Path) -> list[Path]:
    found = []
    for top in _ROOTS:
        base = root / top
        if base.is_file():
            found.append(base)
        elif base.is_dir():
            found += [p for p in sorted(base.rglob("*")) if p.suffix in _SUFFIXES]
    return found


REACH = declare(
    "monitoring-version-literals",
    discover=_sources,
    floor=523,  # mid-window: population 548, window (498, 548)
    growth=50,  # ~9%: ordinary growth between repins must not turn an unrelated PR red
    what="compose, infrastructure and Ansible yml/yaml/ini/sh files",
    roots=_ROOTS,
)


def sites(text: str) -> list[tuple[str, str]]:
    """(tool, version) for each version statement in *text*; an untagged image reads as ``latest``."""
    found = []
    for m in _SITE.finditer(text):
        g = m.groupdict()
        tool = next(g[k] for k in ("stool", "etool", "tool", "itool", "gtool", "atool") if g[k]).lower()
        found.append((tool, (g["sv"] or g["ev"] or g["v"] or g["iv"] or g["av"] or "latest").strip()))
    return found


def home() -> dict[str, str]:
    return dict(sites((_ROOT / _HOME).read_text(encoding="utf-8")))


def test_the_home_holds_the_decided_versions() -> None:
    assert home() == {"prometheus": "2.53.0", "grafana": "11.1.0"}, "maintainer decision 2026-10-26 (#19329)"


def test_every_statement_is_a_pinned_copy_equal_to_the_home() -> None:
    files = REACH.examined(_ROOT)
    found = {p.relative_to(_ROOT).as_posix(): sites(p.read_text(encoding="utf-8")) for p in files}
    REACH.completed(files)
    stated = {rel: s for rel, s in found.items() if s}
    counted = dict(Counter((rel, t) for rel, s in stated.items() for t, _ in s))
    assert counted == _PINNED, f"a (file, tool) statement outside the pinned set (#19329): {counted}"
    want = home()
    differ = [
        f"{rel}: {t} {v}"
        for rel, s in stated.items()
        for t, v in s
        if v != want[t] and (rel, t, v) not in _KNOWN_EXCEPTIONS
    ]
    assert not differ, f"differs from {_HOME} {home()} (#19329): {differ}"


@pytest.mark.parametrize(
    "text,expected",
    [
        ('prometheus_version: "2.48.0"\n', [("prometheus", "2.48.0")]),
        ("grafana_version: latest\n", [("grafana", "latest")]),
        ("grafana_version=latest\n", [("grafana", "latest")]),
        ("    image: prom/prometheus:v2.53.0\n", [("prometheus", "2.53.0")]),
        ("    image: grafana/grafana\n", [("grafana", "latest")]),
        ('grafana_version: "11.1.0"  # pinned copy\n', [("grafana", "11.1.0")]),
        ("    image: grafana/grafana:10.2.0@sha256:abc\n", [("grafana", "10.2.0")]),
        ("    image: docker.io/grafana/grafana:10.2.0\n", [("grafana", "10.2.0")]),
        ('    image: "grafana/grafana:10.2.0"\n', [("grafana", "10.2.0")]),
        ("    image: grafana/grafana:10.2.0-ubuntu\n", [("grafana", "10.2.0-ubuntu")]),
        ("    image: prom/prometheus:v2.48.0 # pinned\n", [("prometheus", "2.48.0")]),
        ("    image: grafana/grafana:${G:-10}\n", [("grafana", "${G:-10}")]),
        ("    image: grafana/grafana-oss:10.2.0\n", [("grafana", "10.2.0")]),
        ("GRAFANA_VERSION=10.2.0\n", [("grafana", "10.2.0")]),
        ('apt-get install -y "grafana=${GRAFANA_VERSION:=10.2.0}"\n', [("grafana", "10.2.0")]),
        ("apt-get install -y grafana=10.2.0\n", [("grafana", "10.2.0")]),
        ("    apt-get install -y -qq grafana\n", [("grafana", "latest")]),
        ("    apt-get install -y -qq prometheus\n", [("prometheus", "latest")]),
    ],
)
def test_each_statement_shape_is_read(text: str, expected: list[tuple[str, str]]) -> None:
    assert sites(text) == expected


def test_references_are_not_statements() -> None:
    assert not sites('    name: "grafana={{ grafana_version }}"\n    release_version: "{{ prometheus_version }}"\n')
