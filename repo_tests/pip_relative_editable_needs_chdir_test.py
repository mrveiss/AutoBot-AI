# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A pip task installing a manifest with a relative editable needs chdir (#15733).

pip resolves ``-e ../autobot_shared`` in a requirements file against the
**current working directory**, not against the file it is written in. An
Ansible ``command:``/``shell:`` task runs from the remote user's home unless
told otherwise, so ``../autobot_shared`` resolved to a path beside that home
and pip refused the whole install:

    ERROR: ../autobot_shared is not a valid editable requirement.

That took out the backend dependency step on every fleet self-update. Three
manifests carry a relative editable and three tasks install them; only the
first surfaced, because the play aborts there.

This pairs the two halves that have to agree: a manifest's opening line, and
the working directory of the task that installs it. Neither file mentions the
other, which is why nothing caught the mismatch.

#15733's own fix missed a shape of the same task: this originally walked only
``command:``/``shell:`` tasks whose ``cmd:`` string embeds ``pip install -r``,
because that was the shape the backend failure took. `roles/npu-worker`'s own
role-side install (`roles/npu-worker/tasks/main.yml`) uses the
``ansible.builtin.pip`` MODULE instead -- a literal ``requirements:`` key, not
a shell string -- so it was invisible to this guard and failed on a live
fleet on 2026-09-14 with the exact same error, despite this file reporting
green. Both shapes are walked now.
"""

from __future__ import annotations

import re

import pytest
from repo_tests._paths import repo_root

yaml = pytest.importorskip("yaml")

_REPO_ROOT = repo_root()
_ANSIBLE = _REPO_ROOT / "autobot-slm-backend" / "ansible"

#: A requirements line pip resolves against the cwd rather than the file.
_RELATIVE_EDITABLE = re.compile(r"^\s*-e\s+\.\.?/", re.M)

#: `-r <path>` in a pip invocation.
_REQUIREMENTS_ARG = re.compile(r"-r\s+(\S+requirements[\w.-]*\.txt)")

#: Floor on the sweep's REACH -- pip tasks discovered, never findings.
_MIN_PIP_TASKS = 3


def _manifests_with_relative_editables() -> set[str]:
    """Repo manifests whose first lines pip cannot resolve without a cwd."""
    found = set()
    for path in _REPO_ROOT.rglob("requirements*.txt"):
        # Relative to the repo root, not absolute: this checkout may itself live
        # under a `.worktrees/` directory, and matching absolute parts would
        # exclude the entire tree and leave the sweep with nothing (#15714).
        if any(
            part in {".worktrees", ".claude", "node_modules", ".git"} for part in path.relative_to(_REPO_ROOT).parts
        ):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if _RELATIVE_EDITABLE.search(text):
            found.add(path.relative_to(_REPO_ROOT).as_posix())
    return found


#: (module-parameter dict) shapes: the pip module's own `requirements:`/`chdir:`,
#: one level flatter than the shell shape below -- no `cmd:` string to parse.
_PIP_MODULE_KEYS = ("pip", "ansible.builtin.pip")
#: (task-directive dict) shapes: a shell string embedding `pip install -r`.
_SHELL_KEYS = ("command", "ansible.builtin.command", "shell", "ansible.builtin.shell")


def _pip_tasks() -> list[tuple[str, str, str | None, object]]:
    """(file, task name, requirements path installed, chdir) for every pip install task.

    Two shapes, both real (#15733's live failure was the second one, and this
    guard originally only walked the first): a `command:`/`shell:` task whose
    `cmd:` embeds `pip install -r PATH`, and an `ansible.builtin.pip` MODULE
    task with a literal `requirements:` key. `chdir` sits in a different place
    in each -- inside the shell task's own mapping for the first, inside the
    pip module's parameter mapping for the second -- so each shape reads its
    own.
    """
    tasks: list[tuple[str, str, str | None, object]] = []

    def walk(node, where: str, name: str = "") -> None:
        if isinstance(node, dict):
            name = str(node.get("name", name))
            for key in _SHELL_KEYS:
                value = node.get(key)
                if isinstance(value, dict) and "pip" in str(value.get("cmd", "")):
                    match = _REQUIREMENTS_ARG.search(str(value.get("cmd", "")))
                    if match:
                        tasks.append((where, name, match.group(1), value.get("chdir")))
            for key in _PIP_MODULE_KEYS:
                value = node.get(key)
                if isinstance(value, dict) and isinstance(value.get("requirements"), str):
                    tasks.append((where, name, value["requirements"], value.get("chdir")))
            for value in node.values():
                walk(value, where, name)
        elif isinstance(node, list):
            for item in node:
                walk(item, where, name)

    for path in sorted(_ANSIBLE.rglob("*.yml")):
        try:
            documents = list(yaml.safe_load_all(path.read_text(encoding="utf-8")))
        except Exception:  # noqa: BLE001 - a jinja-templated file ansible renders before parsing
            continue
        walk(documents, path.name)
    return tasks


def test_the_sweep_reaches_the_pip_tasks_it_claims_to() -> None:
    """Reach before findings -- an empty walk must fail, not pass silently."""
    tasks = _pip_tasks()
    assert (
        len(tasks) >= _MIN_PIP_TASKS
    ), f"found only {len(tasks)} pip tasks (floor {_MIN_PIP_TASKS}) — the walk has stopped reading"


def test_a_task_installing_a_relative_editable_manifest_sets_chdir() -> None:
    """The pairing nothing else checks: manifest shape against task cwd."""
    risky = _manifests_with_relative_editables()
    assert risky, "no manifest carries a relative editable — this guard has lost its subject"

    offenders = []
    for where, name, installed, chdir in _pip_tasks():
        if installed is None:
            continue
        # Match on the manifest's REPO-RELATIVE path, not its basename. Every
        # component names its file requirements.txt, so a basename comparison
        # matches all of them and flags tasks whose manifest is fine.
        if not any(installed.endswith(manifest) for manifest in risky):
            continue
        if not chdir:
            offenders.append(f"{where}: {name} installs {installed} with no chdir")

    assert not offenders, (
        "these install a manifest opening with a relative editable, which pip resolves against the "
        "CWD rather than the file — without chdir the install fails outright (#15733):\n  " + "\n  ".join(offenders)
    )
