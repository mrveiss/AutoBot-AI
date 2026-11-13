# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#21400: every path that reads the scheme-matched backend port has loaded it first.

``backend_scheme_port`` is defined once, in ``_shared/vars/backend_scheme_port.yml``, and is not an inventory or
role variable: a consumer loads it. ``roles/frontend/tasks/code_only.yml`` is entered on its own
(``include_role: frontend, tasks_from: code_only``), where ``main.yml``'s load never runs, and it rendered
``nginx-frontend.conf.j2`` with the variable undefined. These tests read the YAML statically and also render the
role's default for that entry with jinja2's ``StrictUndefined``.
"""

import json
from pathlib import Path

import pytest
import yaml

_ANSIBLE = Path(__file__).resolve().parents[1] / "ansible"
_ROLE = _ANSIBLE / "roles" / "frontend"
_SHARED_VARS = _ANSIBLE / "_shared" / "vars" / "backend_scheme_port.yml"
_LOADER = "load_backend_scheme_port.yml"
_VARS_FILE = "backend_scheme_port.yml"
_READ_TOKENS = ("nginx-frontend.conf.j2", "frontend_upstream_backend_port", "backend_scheme_port")
_EXPRESSION_MARKER = "backend_nginx_port | default(backend_port"


def _flatten(node):
    """Tasks in file order, a block's children following the block itself."""
    if isinstance(node, list):
        for item in node:
            yield from _flatten(item)
    elif isinstance(node, dict):
        yield node
        for key in ("block", "rescue", "always", "tasks", "pre_tasks", "post_tasks"):
            if node.get(key):
                yield from _flatten(node[key])


def _is_loader(task: dict) -> bool:
    text = json.dumps({k: v for k, v in task.items() if k not in ("name", "tags")})
    return ("include_vars" in text and _VARS_FILE in text) or ("include_tasks" in text and _LOADER in text)


def _is_reader(task: dict) -> bool:
    return not _is_loader(task) and any(token in json.dumps(task) for token in _READ_TOKENS)


def readers_without_a_load(tasks) -> list:
    """Names of tasks that read the variable (or render its template) before any task has loaded it."""
    loaded, missing = False, []
    for task in _flatten(tasks):
        if _is_loader(task):
            loaded = True
        elif _is_reader(task) and not loaded:
            missing.append(task.get("name", "<unnamed>"))
    return missing


def _yaml_files() -> list:
    found = [p for ext in ("yml", "yaml") for p in _ANSIBLE.rglob(f"*.{ext}")]
    return sorted(p for p in found if "tests" not in p.relative_to(_ANSIBLE).parts)


class _Loader(yaml.SafeLoader):
    """SafeLoader that reads Ansible's custom tags (``!unsafe``, ``!vault``) as plain data."""


_Loader.add_multi_constructor("!", lambda loader, suffix, node: None)


def _load(path: Path):
    """Every document of the file: a list document contributes its items, a mapping document itself."""
    flat: list = []
    for doc in yaml.load_all(path.read_text(encoding="utf-8"), Loader=_Loader):  # noqa: S506 - SafeLoader subclass
        if isinstance(doc, list):
            flat.extend(doc)
        elif doc is not None:
            flat.append(doc)
    return flat


def _is_task_file(path: Path) -> bool:
    parts = path.relative_to(_ANSIBLE).parts
    return "tasks" in parts and path != _SHARED_VARS


def test_every_role_task_file_that_reads_the_variable_loads_it_first() -> None:
    reading = []
    for path in _yaml_files():
        text = path.read_text(encoding="utf-8")
        if not _is_task_file(path) or not any(token in text for token in _READ_TOKENS):
            continue
        reading.append(path.name)
        assert readers_without_a_load(_load(path)) == [], f"{path.relative_to(_ANSIBLE)} reads it before loading it"
    assert {"main.yml", "code_only.yml"} <= set(reading), f"control: the walk sees the role's readers, saw {reading}"


def test_every_play_that_reads_the_variable_lists_the_shared_file() -> None:
    reading = []
    for path in _yaml_files():
        if path.relative_to(_ANSIBLE).parts[0] != "playbooks":
            continue
        for play in _load(path):
            if not isinstance(play, dict) or not any(token in json.dumps(play) for token in _READ_TOKENS):
                continue
            reading.append(path.name)
            listed = any(str(f).endswith("_shared/vars/" + _VARS_FILE) for f in play.get("vars_files") or [])
            assert listed or readers_without_a_load(play.get("tasks") or []) == [], f"{path.name}: {play.get('name')}"
    assert "rotate-service-keys.yml" in reading, f"control: the walk sees the rotation play, saw {reading}"


def _frontend_entries() -> set:
    entries = set()
    for path in _yaml_files():
        for task in _flatten(_load(path)):
            for key in ("ansible.builtin.include_role", "include_role", "ansible.builtin.import_role", "import_role"):
                spec = task.get(key)
                if isinstance(spec, dict) and spec.get("name") == "frontend":
                    entries.add(spec.get("tasks_from", "main"))
    return entries


def test_every_entry_into_the_frontend_role_is_a_task_file_that_exists() -> None:
    entries = _frontend_entries()
    assert {"main", "code_only"} <= entries, f"control: the walk sees both entries, saw {sorted(entries)}"
    missing = [e for e in sorted(entries) if not (_ROLE / "tasks" / f"{e}.yml").is_file()]
    assert missing == [], f"include_role of frontend names task files that do not exist: {missing}"


def test_the_expression_is_defined_in_exactly_one_file() -> None:
    holders = [p for p in _yaml_files() if _EXPRESSION_MARKER in p.read_text(encoding="utf-8")]
    assert holders == [_SHARED_VARS], holders


def _render_role_default(entry_loads_the_variable: bool) -> str:
    """Render the role's upstream-port default as the ``code_only`` entry would have it: defaults plus what it loads."""
    import jinja2

    defaults = _load(_ROLE / "defaults" / "main.yml")[0]
    variables = {"frontend_upstream_backend_port": defaults["frontend_upstream_backend_port"]}
    if entry_loads_the_variable:
        variables.update(_load(_SHARED_VARS)[0])
    env = jinja2.Environment(undefined=jinja2.StrictUndefined)
    for _ in range(4):  # a variable's value may name another: render until nothing is left to resolve
        variables = {
            k: env.from_string(v).render(**variables) if isinstance(v, str) else v for k, v in variables.items()
        }
    return variables["frontend_upstream_backend_port"]


def test_code_only_entry_renders_the_upstream_port_with_strict_undefined() -> None:
    entry = _load(_ROLE / "tasks" / "code_only.yml")
    assert readers_without_a_load(entry) == [], "code_only.yml must load the variable before it renders the template"
    assert _render_role_default(entry_loads_the_variable=True) == "8443"


def test_contrast_an_entry_that_does_not_load_the_variable_fails_loudly() -> None:
    import jinja2

    with pytest.raises(jinja2.UndefinedError):
        _render_role_default(entry_loads_the_variable=False)
    unloaded = yaml.safe_load("- name: Configure nginx\n  ansible.builtin.template:\n    src: nginx-frontend.conf.j2\n")
    assert readers_without_a_load(unloaded) == ["Configure nginx"]
    loaded = yaml.safe_load(
        "- name: Load\n  ansible.builtin.include_tasks: ../../../_shared/tasks/load_backend_scheme_port.yml\n"
        "- name: Configure nginx\n  ansible.builtin.template:\n    src: nginx-frontend.conf.j2\n"
    )
    assert readers_without_a_load(loaded) == []
    late = yaml.safe_load(
        "- name: Configure nginx\n  ansible.builtin.template:\n    src: nginx-frontend.conf.j2\n"
        "- name: Load\n  ansible.builtin.include_vars:\n    file: x/backend_scheme_port.yml\n"
    )
    assert readers_without_a_load(late) == ["Configure nginx"]
