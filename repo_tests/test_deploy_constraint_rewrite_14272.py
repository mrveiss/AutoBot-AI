# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A requirements file deployed to a different depth than it lives at must have
its relative includes rewritten (#14272).

`-c ../../../../constraints/shared.txt` is correct in the repo and resolves to
`/constraints/shared.txt` from `/opt/autobot/autobot-ai-stack/`. pip aborts, and
provisioning stops.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = _REPO_ROOT / "scripts" / "build-filtered-requirements.sh"
_ANSIBLE_ROLES = _REPO_ROOT / "autobot-slm-backend" / "ansible" / "roles"
_CODE_SOURCE = "/opt/autobot/code_source"

_RELATIVE_INCLUDE = re.compile(r"^\s*-(c|r)\s+(\.\./)+", re.MULTILINE)


def _rewrite(body: str, tmp_path: Path) -> str:
    source = tmp_path / "requirements.txt"
    source.write_text(body, encoding="utf-8")
    result = subprocess.run(
        ["bash", str(_SCRIPT), str(source), _CODE_SOURCE],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


@pytest.mark.parametrize("depth", [1, 2, 3, 4, 6])
def test_a_constraint_include_is_rewritten_at_any_depth(tmp_path, depth):
    """The original pattern was a literal `../`, which fitted the backend and
    silently missed the ai-stack's four levels. A rewrite that only handles the
    depth it was written against does not transfer to the next caller."""
    out = _rewrite("-c " + "../" * depth + "constraints/shared.txt\nnumpy\n", tmp_path)

    assert f"-c {_CODE_SOURCE}/constraints/shared.txt" in out
    assert "../" not in out


@pytest.mark.parametrize("depth", [1, 3])
def test_a_requirements_include_is_rewritten_at_any_depth(tmp_path, depth):
    out = _rewrite("-r " + "../" * depth + "requirements.txt\n", tmp_path)

    assert f"-r {_CODE_SOURCE}/requirements.txt" in out


def test_the_editable_shared_include_is_still_stripped(tmp_path):
    """Pre-existing behaviour: autobot_shared installs separately."""
    out = _rewrite("-e ../autobot_shared\nnumpy\n", tmp_path)

    assert "autobot_shared" not in out
    assert "numpy" in out


def test_an_absolute_include_is_left_alone(tmp_path):
    """Already-rewritten input must survive a second pass unchanged."""
    out = _rewrite(f"-c {_CODE_SOURCE}/constraints/shared.txt\n", tmp_path)

    assert out.strip() == f"-c {_CODE_SOURCE}/constraints/shared.txt"


# ---------------------------------------------------------------------------
# The invariant: no role pip-installs a file that still carries a relative include
# ---------------------------------------------------------------------------


def _pip_requirements_in(document) -> list[tuple[str, str]]:
    """(marker, requirements path) for every pip task in one parsed document."""
    found = []

    def walk(node):
        if isinstance(node, list):
            for item in node:
                walk(item)
        elif isinstance(node, dict):
            pip = node.get("ansible.builtin.pip") or node.get("pip")
            if isinstance(pip, dict) and pip.get("requirements"):
                found.append((str(node.get("name", "")), pip["requirements"]))
            for value in node.values():
                walk(value)

    walk(document)
    return found


def _pip_requirement_paths() -> list[tuple[str, str]]:
    """(role file, requirements path) for every ansible pip task."""
    found = []
    for path in sorted(_ANSIBLE_ROLES.rglob("*.yml")):
        try:
            document = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError:  # pragma: no cover - malformed yaml fails elsewhere
            continue

        def walk(node):
            if isinstance(node, list):
                for item in node:
                    walk(item)
            elif isinstance(node, dict):
                pip = node.get("ansible.builtin.pip") or node.get("pip")
                if isinstance(pip, dict) and pip.get("requirements"):
                    found.append((str(path.relative_to(_ANSIBLE_ROLES)), pip["requirements"]))
                for value in node.values():
                    walk(value)

        walk(document)
    return found


def test_the_scan_found_pip_tasks():
    """An empty scan would make the assertion below vacuous."""
    assert len(_pip_requirement_paths()) >= 2


def _copied_requirements(document) -> set[str]:
    """Basenames a role copies from the repo into the deploy dir."""
    copied: set[str] = set()

    def walk(node):
        if isinstance(node, list):
            for item in node:
                walk(item)
        elif isinstance(node, dict):
            copy = node.get("ansible.builtin.copy") or node.get("copy")
            if isinstance(copy, dict):
                for src in _sources(copy, node):
                    name = src.rsplit("/", 1)[-1]
                    if name.startswith("requirements") and name.endswith(".txt"):
                        copied.add(name)
            for value in node.values():
                walk(value)

    walk(document)
    return copied


def _sources(copy: dict, task: dict) -> list[str]:
    """Literal source paths a copy task reads.

    `src: "{{ item }}"` with a `loop:` is the shape the ai-stack role uses, so a
    scan that only reads `src` finds a template variable and concludes the role
    copies nothing — the rule above would then be vacuously true for exactly the
    role this issue is about.
    """
    src = copy.get("src")
    if isinstance(src, str) and "{{ item }}" not in src:
        return [src]
    loop = task.get("loop") or task.get("with_items")
    if isinstance(loop, list):
        return [item for item in loop if isinstance(item, str)]
    return []


def test_a_role_that_copies_a_requirements_file_does_not_pip_install_it_raw():
    """The #14272 shape, stated as a rule a role can be checked against.

    A file copied out of the repo lands at a different depth than it lives at,
    so its relative `-c`/`-r` includes resolve somewhere else — for the AI stack,
    four levels up from /opt/autobot/autobot-ai-stack/ is `/`, and pip aborted on
    a missing /constraints/shared.txt.

    Scoped to files the SAME role copies, because that is the mapping the YAML
    actually determines. A basename search across the repo cannot tell which
    source file a hardcoded deploy path like /opt/autobot/app/requirements.txt
    came from, and guessing produces false failures.
    """
    offenders = []
    for path in sorted(_ANSIBLE_ROLES.rglob("*.yml")):
        try:
            document = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError:  # pragma: no cover
            continue
        copied = _copied_requirements(document)
        if not copied:
            continue
        for _, requirements in _pip_requirements_in(document):
            name = requirements.rsplit("/", 1)[-1]
            if name in copied:
                offenders.append(
                    f"{path.relative_to(_ANSIBLE_ROLES)} copies {name} and pip-installs it raw — "
                    "install the build-filtered-requirements.sh output instead"
                )

    assert offenders == [], "\n".join(offenders)


def test_the_copy_scan_sees_the_ai_stack_role():
    """Without this, a scan that matched no copy task would make the rule above
    vacuously true."""
    document = yaml.safe_load((_ANSIBLE_ROLES / "ai-stack" / "tasks" / "main.yml").read_text(encoding="utf-8"))

    assert "requirements-ai.txt" in _copied_requirements(document)


def test_the_repo_file_still_carries_the_relative_include():
    """The premise of the whole fix. If this file ever stops using a relative
    constraint, the rewrite is dead code and should be reconsidered rather than
    left in place looking load-bearing."""
    text = (
        _REPO_ROOT / "autobot-infrastructure" / "shared" / "docker" / "ai-stack" / "requirements-ai.txt"
    ).read_text(encoding="utf-8")

    assert _RELATIVE_INCLUDE.search(text)
