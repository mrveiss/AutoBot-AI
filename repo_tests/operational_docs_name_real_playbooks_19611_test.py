# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""An operational doc, script or template names only playbooks that exist (#19611, #19239).

``deploy-backend.yml`` and ``deploy-frontend.yml`` never existed, yet a README, ``deploy.sh``,
two role templates, a runbook and agent guides told people to run them; ``deploy.sh rollback``
stopped every service and then failed on a missing ``rollback.yml``. A reference is checked
where an operator or agent would follow it: docs, ``.claude`` guides, shell scripts and role
templates. Plans, archives, audits and mockups describe proposals or history and are out of
scope by a declared list, not by omission.
"""

from __future__ import annotations

import re

from repo_tests._paths import repo_root

from tools.lint._scan_helpers import tracked_paths

_ANSIBLE = "autobot-slm-backend/ansible"
#: Globs declared to the enumeration helper (recorded in _glob_declared_uncovered.py); the
#: markdown is narrowed to the operational trees below in code.
_SCOPE = ("*.md", "*.sh", "*.j2")
_OPERATIONAL_MD = (
    ".claude/",
    "docs/runbooks/",
    "docs/developer/",
    "docs/infrastructure/",
    "docs/deployment/",
    "docs/guides/",
    "docs/operations/",
    f"{_ANSIBLE}/",
    "autobot-slm-backend/docs/",
)
#: (file, playbook) references that are deliberate, each with its reason.
_EXEMPT = {
    (
        "docs/guides/slm-docker-ansible-deployment.md",
        "playbooks/deploy-docker-app.yml",
    ): "the guide's create-your-own example",
}
#: A path-qualified reference, keyed by its path relative to the ansible root: ``playbooks/x.yml``
#: or ``tests/playbooks/x.yml``. ``playbooks/foo.yml`` is NOT satisfied by a ``foo.yml`` elsewhere (#19698).
#: The whole filename is captured: ``playbooks/deploy.yml.bak`` is its own (missing) reference, not
#: ``playbooks/deploy.yml`` cut short at the dot (#19698 review). A sentence's closing ``.`` is not part of it.
_QUALIFIED = re.compile(r"((?:tests/)?playbooks/[\w.-]*?\.ya?ml(?:\.[\w-]+)*)(?![\w-])")
#: A bare name given to ``run_playbook`` (single or double quoted, #19698); the function resolves it
#: under ``playbooks/`` (``$PLAYBOOK_DIR/$playbook`` in deploy.sh).
_RUN_PLAYBOOK = re.compile(r"""\brun_playbook\s+(["'])([\w.-]+\.ya?ml)\1""")
#: A role manifest's ``"ansible_playbook": "<name>"``; bare, it may sit at the ansible root or in ``playbooks/``.
_MANIFEST = re.compile(r"""["']ansible_playbook["']:\s*(["'])(?:playbooks/)?([\w.-]+\.ya?ml)\1""")
#: A role table's ``| **Ansible playbook** | `<name>` |``: bare names hid here while the patterns above
#: passed (`docs/developer/ROLES.md`), resolved the same way as a manifest's.
_TABLE_ROW = re.compile(r"\*\*Ansible playbook\*\*\s*\|\s*`(?:playbooks/)?([\w.-]+\.ya?ml)`")
#: The registry in Python that names a role's playbook; ``_SCOPE`` holds no Python.
_ROLE_REGISTRY = "autobot-slm-backend/services/role_registry.py"
#: References found across the tree, not files read: a pattern that stopped matching finds none and passes.
_MIN_REFERENCES = 250  # 281 measured on 2026-10-31


def _known_playbooks() -> set[str]:
    """Every playbook as a path relative to the ansible root."""
    root = repo_root() / _ANSIBLE
    return {
        p.relative_to(root).as_posix()
        for pat in ("playbooks/*.y*ml", "tests/playbooks/*.y*ml", "*.y*ml")
        for p in root.glob(pat)
    }


def _in_scope(path: str) -> bool:
    if path.endswith(".md"):
        return path.startswith(_OPERATIONAL_MD)
    return path.endswith(".sh") or (path.endswith(".j2") and path.startswith(_ANSIBLE))


def _missing(text: str, known: set[str]) -> set[str]:
    """References in *text* whose path (relative to the ansible root) names no playbook."""
    out = {m.group(1) for m in _QUALIFIED.finditer(text) if m.group(1) not in known}
    out |= {f"playbooks/{m.group(2)}" for m in _RUN_PLAYBOOK.finditer(text) if f"playbooks/{m.group(2)}" not in known}
    bare = [m.group(2) for m in _MANIFEST.finditer(text)] + _TABLE_ROW.findall(text)
    out |= {f"playbooks/{name}" for name in bare if name not in known and f"playbooks/{name}" not in known}
    return out


def _reference_count(text: str) -> int:
    patterns = (_QUALIFIED, _RUN_PLAYBOOK, _MANIFEST, _TABLE_ROW)
    return sum(len(pattern.findall(text)) for pattern in patterns)


def test_every_operational_reference_names_a_real_playbook() -> None:
    known, offenders = _known_playbooks(), []
    paths = [p for p in tracked_paths(repo_root(), *_SCOPE) if _in_scope(p)]
    assert len(paths) > 200, f"only {len(paths)} operational files enumerated"
    references = 0
    for path in [*paths, _ROLE_REGISTRY]:
        text = (repo_root() / path).read_text(encoding="utf-8", errors="replace")
        references += _reference_count(text)
        offenders += [f"{path}: {n}" for n in sorted(_missing(text, known)) if (path, n) not in _EXEMPT]
    assert references >= _MIN_REFERENCES, f"only {references} playbook references found: the patterns stopped matching"
    assert not offenders, "these name a playbook that does not exist:\n  " + "\n  ".join(offenders)


def test_every_exemption_is_still_live() -> None:
    known = _known_playbooks()
    for (path, name), why in _EXEMPT.items():
        text = (repo_root() / path).read_text(encoding="utf-8")
        assert name in _missing(text, known), f"{path} no longer names {name} ({why}); drop the exemption"


def test_contrast_the_detector() -> None:
    known = {"playbooks/deploy_role.yml", "playbooks/deploy-aiml.yml", "setup-x.yml"}
    assert _missing("ansible-playbook playbooks/deploy-backend.yml", known) == {"playbooks/deploy-backend.yml"}
    assert _missing('run_playbook "rollback.yml" "Deployment rollback"', known) == {"playbooks/rollback.yml"}
    assert _missing('"ansible_playbook": "deploy-frontend.yml",', known) == {"playbooks/deploy-frontend.yml"}
    assert not _missing('run_playbook "deploy_role.yml" "x" "-e role_name=backend"', known)
    assert not _missing('"ansible_playbook": "setup-x.yml",', known)
    assert not _missing("ansible-playbook playbooks/<your-firewall-playbook>.yml", known)


def test_contrast_single_quoted_run_playbook_is_read() -> None:
    known = {"playbooks/deploy_role.yml"}
    assert _missing("run_playbook 'rollback.yml' 'Deployment rollback'", known) == {"playbooks/rollback.yml"}
    assert not _missing("run_playbook 'deploy_role.yml' 'x'", known)
    assert _missing("\"ansible_playbook\": 'gone.yml'", known) == {"playbooks/gone.yml"}


def test_contrast_the_path_is_the_key_not_the_filename() -> None:
    known = {"foo.yml", "tests/playbooks/bar.yml"}  # foo.yml exists at the ansible root only
    assert _missing("ansible-playbook playbooks/foo.yml", known) == {"playbooks/foo.yml"}
    assert _missing("ansible-playbook playbooks/bar.yml", known) == {"playbooks/bar.yml"}
    assert not _missing("ansible-playbook tests/playbooks/bar.yml", known)
    assert _missing('run_playbook "foo.yml" "x"', known) == {"playbooks/foo.yml"}


def test_contrast_the_whole_filename_is_the_reference() -> None:
    known = {"playbooks/deploy.yml"}
    assert _missing("restore playbooks/deploy.yml.bak first", known) == {"playbooks/deploy.yml.bak"}
    assert not _missing("Run playbooks/deploy.yml.", known)
    assert not _missing("see playbooks/deploy.yml, then", known)


def test_contrast_a_role_table_row_is_read_by_its_bare_name() -> None:
    known = {"playbooks/deploy_role.yml", "setup-x.yml"}
    row = "| **Ansible playbook** | `{}` |"
    assert _missing(row.format("deploy-backend.yml"), known) == {"playbooks/deploy-backend.yml"}
    assert _missing(row.format("deploy-backend.yml") + " (deployed alongside)", known) == {
        "playbooks/deploy-backend.yml"
    }
    assert not _missing(row.format("playbooks/deploy_role.yml"), known)
    assert not _missing(row.format("setup-x.yml"), known)


def test_contrast_a_reference_is_counted_and_prose_is_not() -> None:
    assert _reference_count("run playbooks/a.yml, then run_playbook 'b.yml'") == 2
    assert _reference_count("nothing here names one") == 0
