# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""An operational file names only playbooks that exist (#19611).

A runbook naming a playbook that was removed sends an operator under pressure to a command that cannot
work, and nothing notices until someone follows it. Deployed hosts are updated by the builtin updater;
this checks what the docs, agent guides, scripts and templates still name.
"""

from __future__ import annotations

import re
from pathlib import Path

from repo_tests._paths import repo_root
from repo_tests._reach import declare

from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

_ROOTS = ("docs", ".claude", "scripts", "autobot-slm-backend", "autobot-infrastructure")
_SUFFIXES = (".md", ".py", ".sh", ".j2", ".json", ".yml", ".yaml")
_REFERENCE = re.compile(
    r"""playbooks/(?P<path>[A-Za-z0-9_-]+\.ya?ml)|run_playbook\s+"(?P<run>[^"$]+\.ya?ml)"|"ansible_playbook":\s*"(?P<reg>[^"$]+\.ya?ml)\""""
)
#: Historical records and generated output: what they name was true when written.
_EXCLUDED_DIRS = (
    "docs/archives/",
    "docs/audit/",
    "docs/changelog/",
    "docs/design/",
    "docs/fixes/",
    "docs/implementation/",
    "docs/planning/",
    "docs/plans/",
    "docs/prd/",
    "docs/reports/",
    "docs/research/",
    "docs/superpowers/",
)


def _is_test_file(rel: str) -> bool:
    name = rel.rsplit("/", 1)[-1]
    return name.startswith("test_") or "_test." in name or "/tests/" in f"/{rel}"


def _operational_files(root: Path) -> list[str]:
    try:
        tracked = tracked_paths(root, *_ROOTS)
    except EmptyEnumeration:
        return []
    return [
        rel
        for rel in tracked
        if rel.endswith(_SUFFIXES) and not rel.startswith(_EXCLUDED_DIRS) and not _is_test_file(rel)
    ]


def named_playbooks(text: str) -> set[str]:
    """Every playbook file name *text* refers to, without its directory."""
    return {next(g for g in m.groups() if g).rsplit("/", 1)[-1] for m in _REFERENCE.finditer(text)}


def _existing_playbooks(root: Path) -> set[str]:
    return {
        rel.rsplit("/", 1)[-1]
        for rel in tracked_paths(root, "autobot-slm-backend/ansible")
        if rel.endswith((".yml", ".yaml"))
    }


REACH_FILES = declare(
    "playbook-references-exist",
    discover=_operational_files,
    floor=1879,  # mid-window: population 1929, window (1829, 1929)
    what="tracked docs, agent guides, scripts and templates, scanned for playbooks they name",
    roots=_ROOTS,
    growth=100,
)


def test_every_named_playbook_exists() -> None:
    root = repo_root()
    existing = _existing_playbooks(root)
    assert len(existing) >= 50, "the playbook list is nearly empty: this would flag everything"
    missing = []
    for rel in REACH_FILES.examined(root):
        for name in named_playbooks((root / rel).read_text(encoding="utf-8", errors="replace")):
            if name not in existing:
                missing.append(f"{rel}: {name}")
    assert not missing, "these name a playbook that does not exist (#19611):\n  " + "\n  ".join(sorted(missing))


def test_each_reference_form_is_read() -> None:
    assert named_playbooks("run `playbooks/deploy-x.yml`") == {"deploy-x.yml"}
    assert named_playbooks('run_playbook "deploy-y.yml"') == {"deploy-y.yml"}
    assert named_playbooks('"ansible_playbook": "playbooks/deploy-z.yml"') == {"deploy-z.yml"}


def test_a_templated_reference_is_not_read_as_a_name() -> None:
    assert named_playbooks('run_playbook "$name.yml"') == set()
    assert named_playbooks("nothing to see here") == set()


def test_historical_and_test_files_are_excluded_by_the_declared_list() -> None:
    files = _operational_files(repo_root())
    assert any(f.endswith("CODE_UPDATE.md") for f in files)
    assert not any(f.startswith(_EXCLUDED_DIRS) or f.endswith("_test.py") for f in files)
