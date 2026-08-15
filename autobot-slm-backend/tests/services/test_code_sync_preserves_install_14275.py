# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Code-sync is an update procedure: it may cost downtime, never the install (#14275).

`target_path` for several roles is the directory the ansible role also owns —
ai-stack's holds the venv, an ansible-generated `src/` of module symlinks and the
deployed app files. A delete-style sync whose source cannot supply those removes
them, and the service does not come back without a re-provision.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_ORCHESTRATOR = _REPO_ROOT / "autobot-slm-backend" / "services" / "sync_orchestrator.py"
_REGISTRY = _REPO_ROOT / "autobot-slm-backend" / "services" / "role_registry.py"

_RELATIVE_INCLUDE = re.compile(r"^\s*-(c|r)\s+(\.\./)+", re.MULTILINE)


def _rsync_argv() -> list[str]:
    """The literal argv list `_rsync_source_path` builds."""
    tree = ast.parse(_ORCHESTRATOR.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
        if "rsync_cmd" not in targets or not isinstance(node.value, ast.List):
            continue
        return [e.value for e in node.value.elts if isinstance(e, ast.Constant)]
    pytest.fail("rsync_cmd argv not found — this test cannot see what it checks")


def test_the_rsync_argv_was_found():
    """An empty argv would make every assertion below vacuous."""
    assert "rsync" in _rsync_argv()


def test_the_code_sync_rsync_does_not_delete():
    """The install directory holds things the sync source cannot supply.

    Deleting them turns an update into a re-provision. The ansible syncs keep
    `--delete` because their sources DO carry the full tree (#14231); this one
    does not.
    """
    assert "--delete" not in _rsync_argv()


def _rsync_argv_node() -> ast.List:
    tree = ast.parse(_ORCHESTRATOR.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.List):
            if any(isinstance(t, ast.Name) and t.id == "rsync_cmd" for t in node.targets):
                return node.value
    pytest.fail("rsync_cmd argv not found")


def test_host_state_is_excluded_in_the_argv_not_merely_imported():
    """Assert on the command that is BUILT, not on the file's text.

    The first version of this checked that the module mentioned
    HOST_STATE_EXCLUDES anywhere — which stayed true when the excludes were
    deleted from the argv, because the import line still named them. A test that
    reads the wrong observable is the defect it is meant to catch.
    """
    starred = [e for e in _rsync_argv_node().elts if isinstance(e, ast.Starred)]
    assert starred, "no expanded excludes in the rsync argv"

    expanded = " ".join(ast.unparse(e) for e in starred)
    assert "HOST_STATE_EXCLUDES" in expanded
    assert "rsync_artifact_excludes" in expanded


def test_a_missing_source_path_fails_rather_than_reporting_success():
    """It returned `True, "skipped"`. A role whose source_paths named a
    directory absent from the checkout reported a clean sync having copied
    nothing — an update that silently did not happen."""
    source = _ORCHESTRATOR.read_text(encoding="utf-8")
    marker = source.index("Source path not found in cache")
    window = source[marker : marker + 400]

    assert 'return True, "skipped"' not in window
    assert "return False" in window


# ---------------------------------------------------------------------------
# The registry must name sources that exist and deliver what the command expects
# ---------------------------------------------------------------------------


def _registry_entries() -> list[dict]:
    tree = ast.parse(_REGISTRY.read_text(encoding="utf-8"))
    entries = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        keys = {k.value for k in node.keys if isinstance(k, ast.Constant)}
        if {"name", "source_paths"} <= keys:
            entry = {}
            for key, value in zip(node.keys, node.values):
                if not isinstance(key, ast.Constant):
                    continue
                if isinstance(value, ast.Constant):
                    entry[key.value] = value.value
                elif isinstance(value, ast.List):
                    entry[key.value] = [e.value for e in value.elts if isinstance(e, ast.Constant)]
                else:
                    entry[key.value] = ast.unparse(value)
            entries.append(entry)
    return entries


def test_the_registry_scan_found_roles():
    assert len(_registry_entries()) >= 8


def test_every_source_path_exists_in_the_checkout():
    """A source_paths entry that is not in the repo cannot deliver anything.

    ai-stack pointed at `autobot-ai-stack/`, which holds a placeholder README —
    so the sync copied one file and reported success while the real sources sat
    untouched under autobot-infrastructure/shared/docker/ai-stack/.
    """
    missing = [
        f"{entry.get('name')}: {path}"
        for entry in _registry_entries()
        for path in entry.get("source_paths") or []
        if not (_REPO_ROOT / path.rstrip("/")).is_dir()
    ]

    assert missing == [], f"source_paths not present in the checkout: {missing}"


def test_a_source_path_carries_more_than_a_readme():
    """The placeholder-directory trap: present, so no existence check catches it,
    and empty of everything the role actually needs."""
    thin = []
    for entry in _registry_entries():
        for path in entry.get("source_paths") or []:
            directory = _REPO_ROOT / path.rstrip("/")
            if not directory.is_dir():
                continue
            payload = [p for p in directory.rglob("*") if p.is_file() and p.name != "README.md"]
            if not payload:
                thin.append(f"{entry.get('name')}: {path} holds nothing but a README")

    assert thin == [], "\n".join(thin)


def test_a_post_sync_pip_install_goes_through_the_rewrite():
    """A requirements file with a relative `-c`/`-r` cannot be installed raw from
    the deployed directory — pip aborts on the unresolvable include (#14272)."""
    offenders = []
    for entry in _registry_entries():
        command = entry.get("post_sync_cmd") or ""
        if "pip install -r" not in command or "build-filtered-requirements.sh" in command:
            continue
        # A bare install is fine when the file has no relative include — most
        # requirements files do not. Resolve the actual file through the entry's
        # source_paths, which is the directory whose contents land there, and
        # check that file rather than assuming.
        match = re.search(r"pip install -r ([\w./-]+)", command)
        if not match:
            continue
        name = match.group(1).rsplit("/", 1)[-1]
        for path in entry.get("source_paths") or []:
            candidate = _REPO_ROOT / path.rstrip("/") / name
            if candidate.is_file() and _RELATIVE_INCLUDE.search(candidate.read_text(encoding="utf-8")):
                offenders.append(
                    f"{entry.get('name')}: installs {name} raw, but it carries a relative include"
                )

    assert offenders == [], "\n".join(offenders)


def test_the_rewrite_rule_is_not_vacuous():
    """At least one registry entry must reach the rewrite, or the rule above
    passes because nothing was examined."""
    using = [
        entry.get("name")
        for entry in _registry_entries()
        if "build-filtered-requirements.sh" in (entry.get("post_sync_cmd") or "")
    ]

    assert len(using) >= 4, f"only {using} route through the rewrite"
