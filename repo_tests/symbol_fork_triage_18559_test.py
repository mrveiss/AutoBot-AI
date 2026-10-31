# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every cluster #18559 froze into the symbol-fork baseline carries a verdict (#18559, #17312).

Widening ``FORK_ROOTS`` took the baseline from 8 to 124 names with no reason beside them. The
sidecar ``symbol_fork_triage_18559.json`` records, per added cluster, whether it is a ``real``
fork (with the issue that owns the fix), an intentional ``variant`` (per-deploy-target or
per-platform copy) or a ``homonym`` (same name, different concept). The sidecar shrinks with
the baseline: an entry whose cluster left the baseline is stale and fails here.
"""

from __future__ import annotations

import json
import subprocess  # nosec B404  # git plumbing in a throwaway repo, fixed argv, no shell
from pathlib import Path

import pytest
from repo_tests._paths import repo_root

from autobot_shared.isolated_git import isolated_git_env
from autobot_shared.symbol_forks import fork_find_clusters, fork_tracked_python_files

#: The baseline as it stood before #18559 widened the roots; every other name needs a verdict.
PRE_18559_CLUSTERS = frozenset({"Base", "Organization", "Permission", "Role", "SLMClient", "User"})
_VERDICTS = {"real": "issue", "variant": "why", "homonym": "why"}


def _baseline() -> set[str]:
    path = repo_root() / "repo_tests" / "symbol_fork_baseline.json"
    return set(json.loads(path.read_text(encoding="utf-8"))["clusters"])


def _triage() -> dict[str, dict]:
    path = repo_root() / "repo_tests" / "symbol_fork_triage_18559.json"
    return json.loads(path.read_text(encoding="utf-8"))["clusters"]


def test_every_cluster_added_by_18559_has_a_triage_entry() -> None:
    untriaged = sorted(_baseline() - PRE_18559_CLUSTERS - set(_triage()))
    assert not untriaged, f"baseline clusters with no verdict in symbol_fork_triage_18559.json: {untriaged}"


def test_no_triage_entry_names_a_cluster_that_left_the_baseline() -> None:
    stale = sorted(set(_triage()) - _baseline())
    assert not stale, f"triage entries for clusters no longer in the baseline (delete them): {stale}"


def _stale_exemptions(exempt: frozenset[str], baseline: set[str]) -> list[str]:
    """Exempt names whose cluster left the baseline: the exemption may only shrink with it."""
    return sorted(exempt - baseline)


def test_every_pre_18559_exemption_is_still_in_the_baseline() -> None:
    stale = _stale_exemptions(PRE_18559_CLUSTERS, _baseline())
    assert not stale, f"PRE_18559_CLUSTERS names clusters no longer in the baseline (remove them): {stale}"


def test_contrast_a_stale_exemption_is_reported() -> None:
    assert _stale_exemptions(PRE_18559_CLUSTERS | {"GoneCluster"}, _baseline()) == ["GoneCluster"]


def test_a_triage_entry_never_covers_a_pre_18559_cluster() -> None:
    assert not sorted(set(_triage()) & PRE_18559_CLUSTERS)


@pytest.mark.parametrize("name", sorted(_triage()))
def test_each_verdict_is_well_formed(name: str) -> None:
    entry = _triage()[name]
    assert entry.get("verdict") in _VERDICTS, f"{name}: verdict must be one of {sorted(_VERDICTS)}"
    needed = _VERDICTS[entry["verdict"]]
    value = entry.get(needed)
    assert value, f"{name}: a {entry['verdict']} verdict needs {needed!r}"
    if needed == "issue":
        assert isinstance(value, int) and value > 0, f"{name}: 'issue' must be an issue number"
    else:
        assert isinstance(value, str) and len(value) > 10, f"{name}: 'why' must say why"


def _git(cwd: Path, *argv: str) -> None:
    subprocess.run(  # nosec B603 B607  # fixed argv, no shell
        ["git", *argv], cwd=cwd, env=isolated_git_env(), check=True, capture_output=True, timeout=60
    )


def _clusters_for(tmp_path: Path, sync_second: bool):
    """Two modules defining ``fetch_value``; the second is ``async def`` when ``sync_second`` is False."""
    first = "def fetch_value():\n    return 1\n"
    second = first if sync_second else "async def fetch_value():\n    return 1\n"
    for rel, text in (("scripts/a.py", first), ("scripts/b.py", second)):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(text, encoding="utf-8")
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "add", "-A")
    return fork_find_clusters(fork_tracked_python_files(tmp_path), tmp_path).clusters


def test_an_async_def_fork_is_caught(tmp_path: Path) -> None:
    """``get_redis_config`` has an async def in ``api/redis.py``; that one is a route handler, not a gap."""
    cluster = _clusters_for(tmp_path, sync_second=False)["fetch_value"]
    assert {d.path for d in cluster.definitions} == {"scripts/a.py", "scripts/b.py"}


def test_contrast_a_name_bound_in_one_file_is_not_a_cluster(tmp_path: Path) -> None:
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "a.py").write_text("async def fetch_value():\n    return 1\n", encoding="utf-8")
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "add", "-A")
    assert "fetch_value" not in fork_find_clusters(fork_tracked_python_files(tmp_path), tmp_path).clusters
