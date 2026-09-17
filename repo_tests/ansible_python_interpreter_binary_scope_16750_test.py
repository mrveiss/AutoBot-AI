# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A `python_interpreter_binary` reference needs `python_interpreter` statically
in scope (#16750).

#16721 added `virtualenv_command: "{{ python_interpreter_binary }} -m venv"` to
the `browser` role's pip task, right after an
`ansible.builtin.include_role: {name: python_interpreter}` -- with no
`public: true`. `python_interpreter_binary` is a role DEFAULT
(`roles/python_interpreter/defaults/main.yml`), and a dynamic `include_role`
keeps an included role's defaults private to that role's own task execution
unless `public: true` is set -- even for tasks later in the SAME file. A real
`update-all` run on 2026-09-14 failed the browser role's
"Install Playwright and FastAPI dependencies via pip" task with
`'python_interpreter_binary' is undefined`.

Three shapes put `python_interpreter`'s defaults in scope for a task
referencing `python_interpreter_binary`, all STATIC (resolved before the play
runs, so the defaults are merged into play/role scope regardless of task
order):
  - a `meta/main.yml` role dependency on `python_interpreter`
  - `import_role: {name: python_interpreter}`
  - `include_role: {name: python_interpreter, public: true}` (the one dynamic
    shape that also counts, because `public: true` explicitly promotes the
    role's defaults to play scope)

A plain dynamic `include_role` (no `public: true`) does NOT count -- that is
exactly the browser shape that broke. The role that OWNS
`python_interpreter_binary` (`roles/python_interpreter` itself) is exempt: a
role's own `defaults/` are always visible to its own tasks, whatever included
it.

Swept live: the fix for this issue added `public: true` to the existing
`include_role: {name: python_interpreter}` in every role that referenced
`python_interpreter_binary` without it (agent_config, backend_services,
browser, npu-worker, tts-worker) rather than duplicating the default
elsewhere.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from repo_tests._paths import repo_root

yaml = pytest.importorskip("yaml")

_REPO_ROOT = repo_root()
_ANSIBLE = _REPO_ROOT / "autobot-slm-backend" / "ansible"

_ROLE_NAME = "python_interpreter"
_BINARY_VAR_RE = re.compile(r"\{\{\s*python_interpreter_binary\s*\}\}")

#: Floor on files REFERENCING python_interpreter_binary, never on offenders --
#: an offenders floor is satisfied by finding nothing, indistinguishable from a
#: collapsed sweep. 9 files measured 2026-09-14 (agent_config x4,
#: backend_services, browser, npu-worker, python_interpreter, tts-worker).
_MIN_BINARY_REFERENCING_FILES = 6

_IMPORT_ROLE_KEYS = ("ansible.builtin.import_role", "import_role")
_INCLUDE_ROLE_KEYS = ("ansible.builtin.include_role", "include_role")


def _walk_tasks(nodes) -> list[dict]:
    """Flatten a task list, descending into block/rescue/always bodies."""
    flat: list[dict] = []
    if not isinstance(nodes, list):
        return flat
    for node in nodes:
        if not isinstance(node, dict):
            continue
        flat.append(node)
        for key in ("block", "rescue", "always"):
            if isinstance(node.get(key), list):
                flat.extend(_walk_tasks(node[key]))
    return flat


def _load_yaml(path: Path):
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - a jinja-templated or malformed file
        return None


def _meta_declares_dependency(meta_path: Path) -> bool:
    doc = _load_yaml(meta_path)
    if not isinstance(doc, dict):
        return False
    for dep in doc.get("dependencies") or []:
        dep_name = dep.get("role") if isinstance(dep, dict) else dep
        if dep_name == _ROLE_NAME:
            return True
    return False


def _tasks_put_role_statically_in_scope(tasks: list[dict]) -> bool:
    for task in tasks:
        for key in _IMPORT_ROLE_KEYS:
            spec = task.get(key)
            if isinstance(spec, dict) and spec.get("name") == _ROLE_NAME:
                return True
        for key in _INCLUDE_ROLE_KEYS:
            spec = task.get(key)
            if isinstance(spec, dict) and spec.get("name") == _ROLE_NAME and spec.get("public") is True:
                return True
    return False


def _role_has_python_interpreter_statically_in_scope(role_dir: Path) -> bool:
    """meta dependency, import_role, or include_role(public: true) ANYWHERE
    under this role's tasks/ or meta/ (#16750: same-role scope)."""
    meta_main = role_dir / "meta" / "main.yml"
    if meta_main.is_file() and _meta_declares_dependency(meta_main):
        return True
    tasks_dir = role_dir / "tasks"
    if not tasks_dir.is_dir():
        return False
    for path in sorted(tasks_dir.rglob("*.yml")):
        doc = _load_yaml(path)
        if _tasks_put_role_statically_in_scope(_walk_tasks(doc)):
            return True
    return False


def _playbook_has_python_interpreter_statically_in_scope(path: Path) -> bool:
    """Same check, at PLAY scope, for a reference outside any role/ tree."""
    doc = _load_yaml(path)
    if not isinstance(doc, list):
        return False
    for play in doc:
        if not isinstance(play, dict):
            continue
        for entry in play.get("roles") or []:
            name = entry.get("role") if isinstance(entry, dict) else entry
            if name == _ROLE_NAME:
                return True
        if _tasks_put_role_statically_in_scope(_walk_tasks(play.get("tasks"))):
            return True
    return False


def _role_of(path: Path) -> str | None:
    parts = path.relative_to(_ANSIBLE).parts
    if len(parts) >= 2 and parts[0] == "roles":
        return parts[1]
    return None


def _files_referencing_python_interpreter_binary() -> list[Path]:
    found = []
    for path in sorted(_ANSIBLE.rglob("*.yml")):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if _BINARY_VAR_RE.search(text):
            found.append(path)
    return found


def test_the_sweep_reaches_the_files_it_claims_to() -> None:
    """Reach before findings -- an empty walk must fail, not pass silently."""
    referencing_files = _files_referencing_python_interpreter_binary()
    assert len(referencing_files) >= _MIN_BINARY_REFERENCING_FILES, (
        f"found only {len(referencing_files)} files referencing python_interpreter_binary "
        f"(floor {_MIN_BINARY_REFERENCING_FILES}) -- the walk has stopped reading"
    )


def test_every_python_interpreter_binary_reference_has_the_role_statically_in_scope() -> None:
    """#16750: every live site must resolve python_interpreter_binary -- no
    reference may depend on a dynamic include_role without public: true."""
    offenders = []
    for path in _files_referencing_python_interpreter_binary():
        role = _role_of(path)
        if role == _ROLE_NAME:
            continue  # a role's own defaults are always visible to its own tasks
        if role is not None:
            in_scope = _role_has_python_interpreter_statically_in_scope(_ANSIBLE / "roles" / role)
        else:
            in_scope = _playbook_has_python_interpreter_statically_in_scope(path)
        if not in_scope:
            offenders.append(str(path.relative_to(_REPO_ROOT)))

    assert not offenders, (
        "these files reference python_interpreter_binary with no meta dependency, import_role, "
        "or include_role(public: true) putting roles/python_interpreter's defaults statically in "
        "scope -- this is the #16721/#16750 browser regression shape "
        "('python_interpreter_binary' is undefined):\n  " + "\n  ".join(offenders)
    )


# --------------------------------------------------------------------------
# Fixture: prove the detector actually catches the old browser shape, rather
# than trusting the live sweep alone to exercise both branches.
# --------------------------------------------------------------------------

_OLD_BROWSER_SHAPE = """\
- name: "Browser | Install target Python interpreter"
  ansible.builtin.include_role:
    name: python_interpreter
  tags: ['browser', 'packages']

- name: "Browser | Install Playwright and FastAPI dependencies via pip"
  ansible.builtin.pip:
    virtualenv_command: "{{ python_interpreter_binary }} -m venv"
"""

_FIXED_BROWSER_SHAPE = """\
- name: "Browser | Install target Python interpreter"
  ansible.builtin.include_role:
    name: python_interpreter
    public: true
  tags: ['browser', 'packages']

- name: "Browser | Install Playwright and FastAPI dependencies via pip"
  ansible.builtin.pip:
    virtualenv_command: "{{ python_interpreter_binary }} -m venv"
"""


def _write_role(tmp_path: Path, role_name: str, main_yml_text: str) -> Path:
    role_dir = tmp_path / "roles" / role_name
    (role_dir / "tasks").mkdir(parents=True)
    (role_dir / "tasks" / "main.yml").write_text(main_yml_text, encoding="utf-8")
    return role_dir


def test_the_old_browser_shape_is_detected_as_broken(tmp_path) -> None:
    """#16750: an include_role with no public: true must fail the check --
    proving the detector would have caught the real regression."""
    role_dir = _write_role(tmp_path, "browser", _OLD_BROWSER_SHAPE)
    assert _role_has_python_interpreter_statically_in_scope(role_dir) is False


def test_the_fixed_browser_shape_is_detected_as_in_scope(tmp_path) -> None:
    """The SAME fixture, with public: true added, must pass -- proving the
    detector is not just always-false."""
    role_dir = _write_role(tmp_path, "browser", _FIXED_BROWSER_SHAPE)
    assert _role_has_python_interpreter_statically_in_scope(role_dir) is True


def test_a_meta_dependency_puts_the_role_statically_in_scope(tmp_path) -> None:
    role_dir = tmp_path / "roles" / "consumer"
    (role_dir / "meta").mkdir(parents=True)
    (role_dir / "meta" / "main.yml").write_text("dependencies:\n  - role: python_interpreter\n", encoding="utf-8")
    assert _role_has_python_interpreter_statically_in_scope(role_dir) is True


def test_import_role_puts_the_role_statically_in_scope(tmp_path) -> None:
    role_dir = _write_role(
        tmp_path,
        "consumer",
        "- name: Install target Python interpreter\n"
        "  ansible.builtin.import_role:\n"
        "    name: python_interpreter\n",
    )
    assert _role_has_python_interpreter_statically_in_scope(role_dir) is True
