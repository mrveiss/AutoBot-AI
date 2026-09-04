# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#15560: the three backend path defects, each asserted on the property, not the text.

1. ``roles/ai-stack/tasks/main.yml`` built its ``src/`` symlink targets as
   absolute paths under the backend install directory. Same family as #13539/B4
   but wider -- B4 was one well-known link, this is an arbitrary loop of backend
   modules. A link whose target does not depend on where the link itself lives
   cannot survive the tree moving, which is the property #13539's release scheme
   depends on. Proved here the way ``autobot_shared_symlink_relative_13539_test``
   proves it: real symlinks under a ``tmp_path`` root that is guaranteed not to
   be the live tree, resolved with ``os.path.realpath`` -- plus the contrast
   mutation that shows the historical absolute form escapes.

2. ``playbooks/fix-backend-environment.yml`` rendered
   ``roles/backend/templates/autobot-backend.service.j2`` and then rewrote the
   unit's ``PYTHONPATH`` (and ``EnvironmentFile``) with ``lineinfile`` a few
   lines later. Two writers for one setting, and the template is the canonical
   one -- this is the playbook that was producing
   ``PYTHONPATH=…:/opt/autobot_shared``, a directory that does not exist
   (#13539/B3, rendered value fixed in #15559). Asserted as *one writer*: the
   playbook may render the unit, and may read the value back, but may not write
   that setting itself.

3. ``setup-user-backend.yml`` defined ``backend_shared_dir``, which nothing
   consumed -- the right value under a name no role reads, so the play's
   declared deploy root never reached the standalone ``autobot_shared`` copy.
   Asserted generally: no variable that play defines may be unreferenced, so the
   next dead one fails too.

Lives in ``repo_tests/`` because CI's shard command passes an explicit path list
and ``autobot-slm-backend/ansible`` is not on it.
"""

from __future__ import annotations

import os
import re
from pathlib import Path, PurePosixPath
from typing import Any, Iterator

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[1]
_ANSIBLE_ROOT = _REPO_ROOT / "autobot-slm-backend" / "ansible"

_AI_STACK_TASKS = _ANSIBLE_ROOT / "roles" / "ai-stack" / "tasks" / "main.yml"
_AI_STACK_DEFAULTS = _ANSIBLE_ROOT / "roles" / "ai-stack" / "defaults" / "main.yml"
_FIX_BACKEND_ENV = _ANSIBLE_ROOT / "playbooks" / "fix-backend-environment.yml"
_SETUP_USER_BACKEND = _ANSIBLE_ROOT / "setup-user-backend.yml"

_SYMLINK_TASK = "Create src/ symlinks to backend modules (co-located deployment)"

#: The pre-#15560 ``src:`` for the ai-stack links, kept ONLY as the contrast
#: mutation input -- never as a value under test.
_HISTORICAL_ABSOLUTE_SRC = "{{ backend_install_dir }}/{{ item }}"

#: Vacuity floors.
_MIN_SYMLINK_LOOP_ITEMS = 2
_MIN_PLAY_VARS = 10
_MIN_ANSIBLE_FILES_SWEPT = 60


def _load(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _walk(node: Any) -> Iterator[dict]:
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _walk(value)
    elif isinstance(node, list):
        for item in node:
            yield from _walk(item)


def _find_task(document: Any, name: str) -> dict:
    for mapping in _walk(document):
        if mapping.get("name") == name:
            return mapping
    raise AssertionError(f"task {name!r} moved or was renamed")


def _jinja_env():
    jinja2 = pytest.importorskip("jinja2")
    env = jinja2.Environment()  # nosec B701  # repo-owned Ansible sources, never user input
    # Ansible's path filters, which plain Jinja does not carry.
    env.filters["basename"] = lambda value: PurePosixPath(str(value)).name
    env.filters["dirname"] = lambda value: str(PurePosixPath(str(value)).parent)
    return env


def _render(template: str, context: dict) -> str:
    return _jinja_env().from_string(template).render(**context)


def _resolved_defaults(path: Path) -> dict:
    """Render a flat defaults mapping against itself until it stops changing."""
    raw = _load(path)
    context = {k: v for k, v in raw.items() if isinstance(v, (str, int, float, bool))}
    env = _jinja_env()
    for _ in range(6):
        progressed = False
        for key, value in list(context.items()):
            if isinstance(value, str) and "{{" in value:
                rendered = env.from_string(value).render(**context)
                if rendered != value:
                    context[key] = rendered
                    progressed = True
        if not progressed:
            break
    return context


# ---------------------------------------------------------------------------
# 1. ai-stack src/ symlinks resolve relative to the link's own directory
# ---------------------------------------------------------------------------


def _symlink_task() -> dict:
    return _find_task(_load(_AI_STACK_TASKS), _SYMLINK_TASK)


def _symlink_loop_items() -> list[str]:
    items = _symlink_task().get("loop")
    assert isinstance(items, list), f"{_SYMLINK_TASK!r} no longer loops over a literal module list"
    return items


def _file_args(task: dict) -> dict:
    for key in ("ansible.builtin.file", "file"):
        if key in task:
            return task[key]
    raise AssertionError(f"task {task.get('name')!r} carries no file module")


def _resolves_inside_backend_sibling(src_template: str, item: str, tmp_path: Path) -> bool:
    """Materialize the task's dest/src as REAL entries under *tmp_path*.

    ``tmp_path`` is guaranteed not to be the live deploy root, so an absolute
    ``src`` can only pass by accident; a link-relative one passes by
    construction.
    """
    defaults = _resolved_defaults(_AI_STACK_DEFAULTS)
    context = dict(defaults, item=item)
    src = _render(src_template, context)
    dest = _render(_file_args(_symlink_task())["dest"], context)

    link_dir = tmp_path / PurePosixPath(dest).parent.relative_to("/").as_posix()
    link_dir.mkdir(parents=True, exist_ok=True)
    backend_dir = tmp_path / PurePosixPath(defaults["backend_install_dir"]).relative_to("/").as_posix()
    target = backend_dir / item
    target.mkdir(parents=True, exist_ok=True)

    link = link_dir / item
    if link.is_symlink() or link.exists():
        link.unlink()
    os.symlink(src, link)
    return os.path.realpath(link) == os.path.realpath(target)


def test_the_symlink_loop_is_not_empty() -> None:
    items = _symlink_loop_items()
    assert len(items) >= _MIN_SYMLINK_LOOP_ITEMS, (
        f"{_SYMLINK_TASK!r} loops over {items!r}; below {_MIN_SYMLINK_LOOP_ITEMS} the "
        "parametrised checks below would prove almost nothing."
    )


def test_the_symlink_target_is_not_absolute() -> None:
    """Grep-proof: the extracted ``src:`` must not start at the filesystem root."""
    src = _file_args(_symlink_task())["src"]
    assert not src.startswith("/"), (
        f"{_AI_STACK_TASKS.relative_to(_REPO_ROOT)}::{_SYMLINK_TASK!r} writes an absolute " f"symlink target ({src!r})."
    )
    defaults = _resolved_defaults(_AI_STACK_DEFAULTS)
    rendered = _render(src, dict(defaults, item="agents"))
    assert not rendered.startswith("/"), (
        f"{src!r} renders absolute ({rendered!r}) — it re-anchors to the live tree under any "
        "deploy-root relocation (#15560/1, same family as #13539/B4)."
    )


@pytest.mark.parametrize("item", _symlink_loop_items())
def test_the_symlink_resolves_to_the_backend_module_under_a_relocated_root(item: str, tmp_path: Path) -> None:
    src = _file_args(_symlink_task())["src"]
    assert _resolves_inside_backend_sibling(src, item, tmp_path), (
        f"{_AI_STACK_TASKS.relative_to(_REPO_ROOT)}::{_SYMLINK_TASK!r} — src={src!r} does not "
        f"resolve to the backend's {item!r} under a relocated root (#15560/1)."
    )


@pytest.mark.parametrize("item", _symlink_loop_items())
def test_the_absolute_form_would_have_failed_this_check(item: str, tmp_path: Path) -> None:
    """Contrast mutation: restore the pre-#15560 absolute ``src`` and prove the
    SAME resolution helper reports an escape."""
    assert not _resolves_inside_backend_sibling(_HISTORICAL_ABSOLUTE_SRC, item, tmp_path), (
        f"the historical absolute src {_HISTORICAL_ABSOLUTE_SRC!r} unexpectedly resolved inside "
        "the relocated root; the contrast mutation discriminates nothing (#15560/1)."
    )


# ---------------------------------------------------------------------------
# 2. one writer for the backend unit's PYTHONPATH
# ---------------------------------------------------------------------------

_PYTHONPATH_SETTING = re.compile(r'Environment\s*=\s*"?PYTHONPATH')


def _tasks_writing_the_unit(document: Any) -> list[dict]:
    """Every task in *document* that edits the systemd unit in place."""
    writers = []
    for mapping in _walk(document):
        if not isinstance(mapping.get("name"), str):
            continue
        for key in (
            "lineinfile",
            "ansible.builtin.lineinfile",
            "replace",
            "ansible.builtin.replace",
            "blockinfile",
            "ansible.builtin.blockinfile",
        ):
            args = mapping.get(key)
            if isinstance(args, dict) and "autobot-backend.service" in str(args.get("path", "")):
                writers.append(mapping)
    return writers


def test_the_playbook_never_hand_writes_the_units_pythonpath() -> None:
    document = _load(_FIX_BACKEND_ENV)
    offenders = [
        task["name"] for task in _tasks_writing_the_unit(document) if _PYTHONPATH_SETTING.search(yaml.safe_dump(task))
    ]
    assert not offenders, (
        f"{_FIX_BACKEND_ENV.relative_to(_REPO_ROOT)} edits the unit's PYTHONPATH after rendering "
        f"roles/backend/templates/autobot-backend.service.j2, which already writes it: {offenders}. "
        "Two writers for one setting is how this play came to be producing "
        "PYTHONPATH=…:/opt/autobot_shared (#13539/B3, #15560/2)."
    )


def test_the_playbook_derives_the_pythonpath_from_the_rendered_unit() -> None:
    """The positive half: having no second writer must not mean having no value."""
    text = _FIX_BACKEND_ENV.read_text(encoding="utf-8")
    assert "backend_unit_pythonpath" in text, (
        "the play no longer derives a PYTHONPATH from the rendered unit — the import test would "
        "then be exporting nothing (#15560/2)."
    )
    document = _load(_FIX_BACKEND_ENV)
    setters = [
        task
        for task in _walk(document)
        if isinstance(task.get("set_fact") or task.get("ansible.builtin.set_fact"), dict)
        and "backend_unit_pythonpath" in (task.get("set_fact") or task["ansible.builtin.set_fact"])
    ]
    assert len(setters) == 1, f"expected exactly one derivation of backend_unit_pythonpath, found {len(setters)}"
    expression = str((setters[0].get("set_fact") or setters[0]["ansible.builtin.set_fact"])["backend_unit_pythonpath"])
    assert "backend_unit_rendered" in expression, (
        f"backend_unit_pythonpath is not read back out of the rendered unit: {expression!r}. "
        "Restating the template's expression instead is the second writer wearing a different hat."
    )


# ---------------------------------------------------------------------------
# 3. no variable defined and consumed by nobody
# ---------------------------------------------------------------------------


def _ansible_sources() -> list[Path]:
    return sorted(
        path for path in _ANSIBLE_ROOT.rglob("*") if path.is_file() and path.suffix in {".yml", ".yaml", ".j2"}
    )


def _play_vars(path: Path) -> dict:
    document = _load(path)
    assert isinstance(document, list) and document, f"{path} is not a playbook"
    variables = document[0].get("vars")
    assert isinstance(variables, dict), f"{path}'s first play declares no vars mapping"
    return variables


def _is_referenced(name: str, definition_file: Path) -> bool:
    """True when *name* appears outside its own definition, in real YAML (not a comment)."""
    pattern = re.compile(rf"\b{re.escape(name)}\b")
    definition = re.compile(rf"^\s*{re.escape(name)}\s*:")
    for path in _ansible_sources():
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.lstrip().startswith("#"):
                continue
            if path == definition_file and definition.match(line):
                continue
            if pattern.search(line):
                return True
    return False


def test_the_variable_sweep_is_not_vacuous() -> None:
    variables = _play_vars(_SETUP_USER_BACKEND)
    assert len(variables) >= _MIN_PLAY_VARS, (
        f"setup-user-backend.yml declares {len(variables)} play vars (floor {_MIN_PLAY_VARS}) — "
        "the extraction collapsed rather than the play shrinking."
    )
    assert (
        len(_ansible_sources()) >= _MIN_ANSIBLE_FILES_SWEPT
    ), f"swept only {len(_ansible_sources())} Ansible sources — the sweep collapsed."
    assert not _is_referenced("backend_shared_dir", _SETUP_USER_BACKEND), (
        "backend_shared_dir is back. It is the right value under a name no role reads; the name "
        "roles consume is backend_shared_standalone_dir (#15560/3)."
    )


@pytest.mark.parametrize("name", sorted(_play_vars(_SETUP_USER_BACKEND)))
def test_every_variable_setup_user_backend_defines_is_consumed(name: str) -> None:
    assert _is_referenced(name, _SETUP_USER_BACKEND), (
        f"setup-user-backend.yml defines {name!r} and nothing in the Ansible tree reads it. "
        "Dead configuration reads as meaningful to whoever edits next — wire it in under the "
        "name its consumer actually uses, or it is not configuration at all (#15560/3)."
    )
