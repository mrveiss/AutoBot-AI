# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One tracked home per static data file (#18556).

``error_messages.yaml`` lived in three places, ``prometheus.yml`` and ``permission_rules.yaml``
each had a second copy kept in step by a drift script, and the Grafana datasource and Prometheus
config each had a drifted infrastructure fork that only a broken installer script read. The
earlier guard rejected only *byte-identical* copies, so every drifted fork passed it.

This guard asks a different question: for each guarded file NAME, which tracked paths may carry
it? ``_ALLOWED`` answers with an explicit list. Any other tracked file with that basename fails,
whatever its bytes, so a re-added copy cannot hide by drifting by one line. The enumeration is the
whole repository (git decides what exists), not a list of roots that a copy could slip outside of.

An allow-list entry that is no longer tracked fails too, so the list shrinks when the work it
points at lands instead of rotting into a licence for a file that is gone.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Iterable

import pytest
from repo_tests._paths import repo_root
from repo_tests._reach import declare

from autobot_shared.paths import scrubbed_git_env
from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

#: guarded basename -> the ONLY tracked paths allowed to carry it.
_ALLOWED: dict[str, frozenset[str]] = {
    "error_messages.yaml": frozenset({"autobot-backend/static/error_messages.yaml"}),
    # Three unrelated files share this basename; none is a copy of another:
    #  * the Docker scrape config, mounted whole by docker-compose;
    #  * the Docker Grafana datasource, mounted by docker-compose;
    #  * the Ansible monitoring role's Prometheus TASK file (the fleet config is the template
    #    prometheus.yml.j2, a different basename). The role is the only fleet install path.
    # The infrastructure forks of the scrape config and the datasource were folded into the role
    # and removed; re-adding either is the failure this guard exists for.
    "prometheus.yml": frozenset(
        {
            "autobot-monitoring/prometheus.yml",
            "autobot-monitoring/grafana/provisioning/datasources/prometheus.yml",
            "autobot-slm-backend/ansible/roles/monitoring/tasks/prometheus.yml",
        }
    ),
    # The 492-line infrastructure ruleset is NOT a copy of the 5-line backend file: Docker
    # overwrites the backend file with it. Which one is canonical is the policy decision owned by
    # #17852; until it lands both stay, and the list shrinks there.
    "permission_rules.yaml": frozenset(
        {
            "autobot-backend/config/permission_rules.yaml",
            "autobot-infrastructure/shared/config/permission_rules.yaml",
        }
    ),
    # #18884: the Docker image ships the backend registry; the infrastructure copy (a different,
    # loader-incompatible file that overwrote it) is removed.
    "llm_models.yaml": frozenset({"autobot-backend/config/llm_models.yaml"}),
}
#: Roots that hold an allowed file today: the reach claim (every one must be populated).
_ROOTS = ("autobot-backend", "autobot-slm-backend", "autobot-infrastructure", "autobot-monitoring")
#: Whole-repo pathspecs: a copy outside every root above must still be seen.
_PATHSPECS = tuple(f"*{name}" for name in _ALLOWED)


def _name(rel: str) -> str:
    return rel.rsplit("/", 1)[-1]


def _violations(paths: Iterable[str]) -> list[str]:
    """Every way ``paths`` departs from ``_ALLOWED``, in either direction.

    An empty ``paths`` is NOT clean: every allowed path is then reported missing, so a scan that
    examined nothing cannot read as a pass.
    """
    present = {rel for rel in paths if _name(rel) in _ALLOWED}
    found = [
        f"{rel}: not an allowed path for {_name(rel)} (allowed: {sorted(_ALLOWED[_name(rel)])})"
        for rel in sorted(present)
        if rel not in _ALLOWED[_name(rel)]
    ]
    for name, allowed in _ALLOWED.items():
        found += [f"{rel}: allow-listed for {name} but no longer tracked" for rel in sorted(allowed - present)]
    return found


def _population(root: Path) -> list[str]:
    try:
        tracked = tracked_paths(root, *_PATHSPECS)
    except EmptyEnumeration:
        return []
    return [rel for rel in tracked if _name(rel) in _ALLOWED]


REACH = declare(
    "one-static-data-copy-scan",
    discover=_population,
    # Window against 8 files is [6, 8]; pinned mid-window.
    floor=7,
    what="tracked files named like a guarded static data file",
    roots=_ROOTS,
    growth=2,
)


def test_each_guarded_data_file_is_only_at_an_allowed_path() -> None:
    found = _violations(REACH.examined(repo_root()))
    assert not found, f"#18556: {found}"


def test_the_allow_list_names_only_guarded_basenames() -> None:
    for name, allowed in _ALLOWED.items():
        assert allowed, name
        assert {_name(rel) for rel in allowed} == {name}


_CLEAN = [rel for allowed in _ALLOWED.values() for rel in sorted(allowed)]


def test_contrast_the_allowed_set_passes() -> None:
    assert _violations(_CLEAN) == []


def test_contrast_an_empty_scan_is_not_clean() -> None:
    assert len(_violations([])) == len(_CLEAN)


@pytest.mark.parametrize("name", sorted(_ALLOWED))
def test_contrast_a_readded_copy_at_any_other_path_fails(name: str) -> None:
    found = _violations([*_CLEAN, f"somewhere/else/{name}"])
    assert [v for v in found if v.startswith(f"somewhere/else/{name}: not an allowed path")]


@pytest.mark.parametrize(
    "removed_fork",
    [
        "autobot-infrastructure/shared/config/prometheus/prometheus.yml",
        "autobot-infrastructure/shared/docker/monitoring/prometheus.yml",
        "autobot-infrastructure/shared/config/grafana/provisioning/datasources/prometheus.yml",
        "autobot-infrastructure/shared/config/error_messages.yaml",
        "autobot-infrastructure/shared/config/llm_models.yaml",
    ],
)
def test_contrast_each_removed_fork_fails_if_it_returns(removed_fork: str) -> None:
    assert any(v.startswith(f"{removed_fork}:") for v in _violations([*_CLEAN, removed_fork]))


def test_contrast_an_allow_listed_path_that_vanished_fails() -> None:
    gone = "autobot-infrastructure/shared/config/permission_rules.yaml"
    assert any(v.startswith(f"{gone}: allow-listed") for v in _violations([p for p in _CLEAN if p != gone]))


def _git_env() -> dict[str, str]:
    """Hermetic: no global or system config, so a global ignore rule cannot untrack a file here."""
    return {**scrubbed_git_env(), "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull}


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, env=_git_env())


def _tracked_tree(root: Path, files: dict[str, bytes]) -> None:
    subprocess.run(["git", "init", "-q", str(root)], check=True, env=_git_env())
    for rel, body in files.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(body)
    _git(root, "add", "-A")


def test_contrast_a_drifted_readded_copy_in_a_real_git_tree_fails(tmp_path: Path) -> None:
    """End to end through the real enumerator: the re-added copy differs from the canonical one."""
    canonical = {rel: f"canonical {rel}\n".encode() for rel in _CLEAN}
    clean, dirty = tmp_path / "clean", tmp_path / "dirty"
    _tracked_tree(clean, canonical)
    fork = "autobot-infrastructure/shared/config/prometheus/prometheus.yml"
    _tracked_tree(dirty, {**canonical, fork: b"environment: production  # drifted\n"})
    assert _violations(_population(clean)) == []
    found = _violations(_population(dirty))
    assert [v for v in found if v.startswith(f"{fork}: not an allowed path")]


def test_a_global_ignore_rule_cannot_untrack_a_file_in_the_throwaway_tree(tmp_path: Path, monkeypatch) -> None:
    """The helpers ignore the ambient git config: a global `core.excludesFile` naming a guarded file
    would otherwise leave it untracked, and the end-to-end test above would pass for the wrong reason."""
    ignore, config = tmp_path / "ignore", tmp_path / "gitconfig"
    ignore.write_text("prometheus.yml\n", encoding="utf-8")
    config.write_text(f"[core]\n\texcludesFile = {ignore}\n", encoding="utf-8")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(config))
    fork = "autobot-infrastructure/shared/config/prometheus/prometheus.yml"
    _tracked_tree(tmp_path / "repo", {fork: b"x\n"})
    assert fork in _population(tmp_path / "repo")
