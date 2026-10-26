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
    ("docs/guides/slm-docker-ansible-deployment.md", "deploy-docker-app.yml"): "the guide's create-your-own example",
}
_REFS = (
    re.compile(r"playbooks/([\w.-]+\.ya?ml)\b"),
    re.compile(r"\brun_playbook\s+\"([\w.-]+\.ya?ml)\""),
    re.compile(r"\"ansible_playbook\":\s*\"(?:playbooks/)?([\w.-]+\.ya?ml)\""),
)


def _known_playbooks() -> set[str]:
    root = repo_root() / _ANSIBLE
    names = {p.name for d in ("playbooks", "tests/playbooks") for p in (root / d).glob("*.y*ml")}
    return names | {p.name for p in root.glob("*.y*ml")}


def _in_scope(path: str) -> bool:
    if path.endswith(".md"):
        return path.startswith(_OPERATIONAL_MD)
    return path.endswith(".sh") or (path.endswith(".j2") and path.startswith(_ANSIBLE))


def _missing(text: str, known: set[str]) -> set[str]:
    return {m.group(1) for rx in _REFS for m in rx.finditer(text) if m.group(1) not in known}


def test_every_operational_reference_names_a_real_playbook() -> None:
    known, offenders = _known_playbooks(), []
    paths = [p for p in tracked_paths(repo_root(), *_SCOPE) if _in_scope(p)]
    assert len(paths) > 200, f"only {len(paths)} operational files enumerated"
    for path in paths:
        text = (repo_root() / path).read_text(encoding="utf-8", errors="replace")
        offenders += [f"{path}: {n}" for n in sorted(_missing(text, known)) if (path, n) not in _EXEMPT]
    assert not offenders, "these name a playbook that does not exist:\n  " + "\n  ".join(offenders)


def test_every_exemption_is_still_live() -> None:
    known = _known_playbooks()
    for (path, name), why in _EXEMPT.items():
        text = (repo_root() / path).read_text(encoding="utf-8")
        assert name in _missing(text, known), f"{path} no longer names {name} ({why}); drop the exemption"


def test_contrast_the_detector() -> None:
    known = {"deploy_role.yml", "deploy-aiml.yml"}
    assert _missing("ansible-playbook playbooks/deploy-backend.yml", known) == {"deploy-backend.yml"}
    assert _missing('run_playbook "rollback.yml" "Deployment rollback"', known) == {"rollback.yml"}
    assert _missing('"ansible_playbook": "deploy-frontend.yml",', known) == {"deploy-frontend.yml"}
    assert not _missing('run_playbook "deploy_role.yml" "x" "-e role_name=backend"', known)
    assert not _missing("ansible-playbook playbooks/<your-firewall-playbook>.yml", known)
