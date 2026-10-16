# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One tracked copy of each static data file (#18556).

``error_messages.yaml`` lived in three places (backend static dir, an Ansible role mirror, an
infrastructure copy), ``prometheus.yml`` and ``permission_rules.yaml`` each had a byte-identical
second copy kept in step by a drift script. Now one copy of each is tracked and Ansible copies it
straight from the backend / monitoring tree.

Two rules, both over the tracked file list (git decides what exists, not the filesystem):

* ``error_messages.yaml`` has exactly ONE tracked path, whatever its content (the removed
  infrastructure copy differed from the canonical one only by a license header).
* No two tracked ``prometheus.yml`` / ``permission_rules.yaml`` files are byte-identical. Same-named
  files with different content (the Grafana datasource, the Ansible task file, the Docker-only
  permission ruleset of #17852) are distinct files, not copies.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Callable, Iterable

from repo_tests._paths import repo_root
from repo_tests._reach import declare

from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

_SINGLE_PATH = {"error_messages.yaml": "autobot-backend/static/error_messages.yaml"}
_NO_IDENTICAL_COPIES = ("prometheus.yml", "permission_rules.yaml")
_WATCHED = frozenset(_SINGLE_PATH) | frozenset(_NO_IDENTICAL_COPIES)
#: Roots that hold a watched file today: the reach claim (every one must be populated).
_ROOTS = ("autobot-backend", "autobot-slm-backend", "autobot-infrastructure", "autobot-monitoring")
#: Swept too: docker/ holds none today, but a copy reappearing there must still be caught.
_SWEEP = _ROOTS + ("docker",)


def _name(rel: str) -> str:
    return rel.rsplit("/", 1)[-1]


def _violations(paths: Iterable[str], read: Callable[[str], bytes]) -> list[str]:
    """Every way ``paths`` carries a second copy of a watched data file."""
    by_name: dict[str, list[str]] = defaultdict(list)
    for rel in paths:
        if _name(rel) in _WATCHED:
            by_name[_name(rel)].append(rel)
    found: list[str] = []
    for name, canonical in _SINGLE_PATH.items():
        if by_name[name] != [canonical]:
            found.append(f"{name}: tracked at {sorted(by_name[name])}, expected only [{canonical!r}]")
    for name in _NO_IDENTICAL_COPIES:
        seen: dict[bytes, str] = {}
        for rel in sorted(by_name[name]):
            body = read(rel)
            if body in seen:
                found.append(f"{name}: {rel} is byte-identical to {seen[body]}")
            seen.setdefault(body, rel)
    return found


def _population(root: Path) -> list[str]:
    try:
        tracked = tracked_paths(root, *_SWEEP)
    except EmptyEnumeration:
        return []
    return [rel for rel in tracked if _name(rel) in _WATCHED]


REACH = declare(
    "one-static-data-copy-scan",
    discover=_population,
    # Mid-window, from REACH.window().
    floor=6,
    what="tracked files named like a watched static data file",
    roots=_ROOTS,
    growth=4,
)


def _read(rel: str) -> bytes:
    return (repo_root() / rel).read_bytes()


def test_each_static_data_file_has_one_tracked_copy() -> None:
    paths = REACH.examined(repo_root())
    assert not _violations(paths, _read), f"#18556: {_violations(paths, _read)}"


def test_the_canonical_copies_are_tracked() -> None:
    paths = set(_population(repo_root()))
    assert set(_SINGLE_PATH.values()) <= paths
    assert "autobot-monitoring/prometheus.yml" in paths
    assert "autobot-backend/config/permission_rules.yaml" in paths


_FILES = {"a/prometheus.yml": b"x", "b/prometheus.yml": b"y", "autobot-backend/static/error_messages.yaml": b"e"}


def test_contrast_a_clean_tree_passes() -> None:
    assert _violations(_FILES, lambda rel: _FILES[rel]) == []


def test_contrast_a_readded_identical_copy_fails() -> None:
    files = {**_FILES, "c/prometheus.yml": b"x"}
    assert any("byte-identical" in v for v in _violations(files, lambda rel: files[rel]))


def test_contrast_a_readded_error_messages_copy_fails_even_with_different_content() -> None:
    files = {**_FILES, "autobot-infrastructure/shared/config/error_messages.yaml": b"header-less"}
    assert any("error_messages.yaml" in v for v in _violations(files, lambda rel: files[rel]))
