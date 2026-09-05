# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""B4 (#13539): every `autobot_shared` symlink target must be RELATIVE.

`ansible.builtin.file` tasks that create the `autobot_shared` symlink used to give
`src:` as an absolute path (``/opt/autobot/autobot_shared``,
``{{ backend_shared_standalone_dir }}``, ``{{ slm_shared_dir }}`` -- all of which
render absolute). An absolute symlink target is anchored to the live tree
regardless of where the directory holding the link itself lives, so it silently
escapes to `/opt/autobot` under any deploy-root relocation (release layout,
disposable test root, etc.) even though today, on the one tree that exists, the
absolute and relative forms happen to coincide.

This module locates each task BY NAME in the real ansible source (never a copied
rule) and proves the RESOLVED property with real filesystem symlinks under
`tmp_path` -- a root that is guaranteed not to be `/opt/autobot` -- rather than
asserting on the YAML text. `test_the_absolute_form_would_have_failed_this_check`
is the contrast mutation: it re-runs the same resolution against the historical
absolute `src` values and shows they escape `tmp_path`, which is what made B4 a
live defect and not a style nit.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[1]
_ANSIBLE_ROOT = _REPO_ROOT / "autobot-slm-backend" / "ansible"

_UPDATE_ALL_NODES = _ANSIBLE_ROOT / "playbooks" / "update-all-nodes.yml"
_DEPLOY_BACKEND_ENV = _ANSIBLE_ROOT / "playbooks" / "deploy-backend-env.yml"
_BACKEND_ENV_VARS = _ANSIBLE_ROOT / "playbooks" / "vars" / "backend-env.yml"
_BACKEND_TASKS = _ANSIBLE_ROOT / "roles" / "backend" / "tasks" / "main.yml"
_BACKEND_DEFAULTS = _ANSIBLE_ROOT / "roles" / "backend" / "defaults" / "main.yml"
_GROUP_VARS_ALL = _ANSIBLE_ROOT / "inventory" / "group_vars" / "all.yml"
_SLM_MANAGER_TASKS = _ANSIBLE_ROOT / "roles" / "slm_manager" / "tasks" / "main.yml"
_SLM_MANAGER_DEFAULTS = _ANSIBLE_ROOT / "roles" / "slm_manager" / "defaults" / "main.yml"

#: The historical (pre-#13539) absolute `src:` value for each site, kept here
#: ONLY as the contrast-mutation input -- never as the value under test.
_HISTORICAL_ABSOLUTE_SRC = {
    "update-all-nodes-slm-agent-play1": "/opt/autobot/autobot_shared",
    "update-all-nodes-slm-backend-play1": "/opt/autobot/autobot_shared",
    "update-all-nodes-backend-play2": "/opt/autobot/autobot_shared",
    "update-all-nodes-slm-agent-play2": "/opt/autobot/autobot_shared",
    "update-all-nodes-slm-backend-play2": "/opt/autobot/autobot_shared",
    "deploy-backend-env": "{{ backend_install_dir }}/../autobot_shared",
    "backend-role-10020": "{{ backend_shared_standalone_dir }}",
    "slm-manager-role-10912": "{{ slm_shared_dir }}",
}


def _load_yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _find_task(node: Any, name: str) -> dict | None:
    """Recursively find the task dict named *name*, wherever it is nested."""
    if isinstance(node, dict):
        if node.get("name") == name:
            return node
        for value in node.values():
            found = _find_task(value, name)
            if found is not None:
                return found
    elif isinstance(node, list):
        for item in node:
            found = _find_task(item, name)
            if found is not None:
                return found
    return None


def _file_module_args(task: dict) -> dict:
    for key in ("ansible.builtin.file", "file"):
        if key in task:
            return task[key]
    raise AssertionError(f"task {task.get('name')!r} carries no file/ansible.builtin.file module")


def _global_context() -> dict:
    """The inventory-wide vars every role default is rendered against.

    A role default may reference a global -- `roles/backend/defaults/main.yml`
    derives `code_source_dir` from `autobot.base_dir` (#15632), which is defined
    in `inventory/group_vars/all.yml`, not beside it. Ansible resolves that
    because group_vars are in scope for every play; a resolver seeded only with
    the role's own mapping is not modelling ansible, and raises UndefinedError
    on a file that is perfectly valid.

    Nested values are kept, not filtered to scalars: `autobot` is a mapping and
    the reference is to an attribute of it. They are made available for LOOKUP
    only -- see the render loop below for why they are not resolved themselves.
    """
    return dict(_load_yaml(_GROUP_VARS_ALL))


def _resolve_defaults(raw: dict) -> dict:
    """Iteratively render a flat defaults/vars mapping against itself.

    roles/slm_manager/defaults/main.yml defines `slm_backend_dir:
    "{{ slm_base_dir }}/autobot-slm-backend"` -- a Jinja reference to a sibling
    key in the SAME mapping. Plain vars (jinja2) render only one level per pass,
    so this repeats until nothing changes (small, bounded mappings -- never a
    functional loop).

    Rendering happens against the role mapping PLUS the inventory globals, so a
    default deriving from `autobot.base_dir` resolves here as it does in a real
    play (#15632).
    """
    jinja2 = pytest.importorskip("jinja2")
    env = jinja2.Environment()  # nosec B701  # compiling repo-owned defaults, never user input
    globals_ = _global_context()
    context = {k: v for k, v in raw.items() if isinstance(v, (str, int, float, bool))}
    for _ in range(6):
        progressed = False
        # Only the ROLE's own keys are rendered. The globals are in scope for
        # lookup but are not themselves resolved here: group_vars/all.yml
        # contains entries built from ansible's inventory magic vars (`groups`),
        # which exist only inside a real play. Rendering those would fail on
        # files this test is not about.
        for key, value in list(context.items()):
            if isinstance(value, str) and "{{" in value:
                rendered = env.from_string(value).render(**{**globals_, **context})
                if rendered != value:
                    context[key] = rendered
                    progressed = True
        if not progressed:
            break
    return context


def _render(template: str, context: dict) -> str:
    jinja2 = pytest.importorskip("jinja2")
    env = jinja2.Environment()  # nosec B701
    return env.from_string(template).render(**context)


#: (site id, task file, task name, dest resolver) -- dest resolver returns the
#: rendered `dest:` this task uses TODAY, extracted from the task's own scope.
def _site_specs() -> list[tuple[str, Path, str, str]]:
    update_all_nodes = _load_yaml(_UPDATE_ALL_NODES)
    backend_env_vars = _load_yaml(_BACKEND_ENV_VARS)
    backend_defaults = _resolve_defaults(_load_yaml(_BACKEND_DEFAULTS))
    slm_defaults = _resolve_defaults(_load_yaml(_SLM_MANAGER_DEFAULTS))

    specs = []

    for site_id, task_name in (
        ("update-all-nodes-slm-agent-play1", "[PLAY 1] SLM Agent | Create autobot_shared symlink for agent imports"),
        (
            "update-all-nodes-slm-backend-play1",
            "[PLAY 1] SLM Backend | Create autobot_shared symlink for backend imports",
        ),
        ("update-all-nodes-backend-play2", "[PLAY 2] Backend | Ensure autobot_shared symlink inside backend dir (#2651)"),
        ("update-all-nodes-slm-agent-play2", "[PLAY 2] SLM Agent | Create autobot_shared symlink for agent imports"),
        (
            "update-all-nodes-slm-backend-play2",
            "[PLAY 2] SLM Backend | Create autobot_shared symlink for backend imports",
        ),
    ):
        task = _find_task(update_all_nodes, task_name)
        assert task is not None, f"{task_name!r} moved or was renamed in update-all-nodes.yml"
        args = _file_module_args(task)
        specs.append((site_id, _UPDATE_ALL_NODES, task_name, args["dest"], args["src"]))

    deploy_backend_env = _load_yaml(_DEPLOY_BACKEND_ENV)
    task = _find_task(deploy_backend_env, "Ensure autobot_shared symlink exists")
    assert task is not None, "'Ensure autobot_shared symlink exists' moved or was renamed"
    args = _file_module_args(task)
    dest = _render(args["dest"], backend_env_vars)
    specs.append(("deploy-backend-env", _DEPLOY_BACKEND_ENV, "Ensure autobot_shared symlink exists", dest, args["src"]))

    backend_tasks = _load_yaml(_BACKEND_TASKS)
    task_name = "Backend | Symlink embedded autobot_shared to standalone canonical copy (#10020)"
    task = _find_task(backend_tasks, task_name)
    assert task is not None, f"{task_name!r} moved or was renamed in roles/backend/tasks/main.yml"
    args = _file_module_args(task)
    dest = _render(args["dest"], backend_defaults)
    specs.append(("backend-role-10020", _BACKEND_TASKS, task_name, dest, args["src"]))

    slm_tasks = _load_yaml(_SLM_MANAGER_TASKS)
    task_name = "SLM | Symlink embedded autobot_shared to canonical SLM copy (#10912)"
    task = _find_task(slm_tasks, task_name)
    assert task is not None, f"{task_name!r} moved or was renamed in roles/slm_manager/tasks/main.yml"
    args = _file_module_args(task)
    dest = _render(args["dest"], slm_defaults)
    specs.append(("slm-manager-role-10912", _SLM_MANAGER_TASKS, task_name, dest, args["src"]))

    return specs


_SITE_SPECS = _site_specs()
_SITE_IDS = [spec[0] for spec in _SITE_SPECS]


def _resolves_inside_sibling(dest_abs: str, src: str, tmp_path: Path) -> bool:
    """Materialize the exact task's dest/src as REAL filesystem entries under
    tmp_path and prove (via os.path.realpath) whether the link lands inside
    tmp_path's own `autobot_shared` sibling -- the property B4 exists for.

    tmp_path is guaranteed not to be `/opt/autobot`, so an absolute `src` can
    only pass this by accident; a relative `src` passes by construction.
    """
    component_dir_name = Path(dest_abs).parent.name
    component_dir = tmp_path / component_dir_name
    component_dir.mkdir(parents=True, exist_ok=True)
    shared_dir = tmp_path / "autobot_shared"
    shared_dir.mkdir(parents=True, exist_ok=True)

    link_path = component_dir / "autobot_shared"
    if link_path.is_symlink() or link_path.exists():
        link_path.unlink()
    os.symlink(src, link_path)

    return os.path.realpath(link_path) == os.path.realpath(shared_dir)


@pytest.mark.parametrize("site_id, task_file, task_name, dest, src", _SITE_SPECS, ids=_SITE_IDS)
def test_the_symlink_target_is_relative_in_the_yaml(
    site_id: str, task_file: Path, task_name: str, dest: str, src: str
) -> None:
    """Grep-proof: the extracted `src:` string itself must not be absolute."""
    assert not src.startswith("/"), (
        f"{task_file.relative_to(_REPO_ROOT)}::{task_name!r} still writes an absolute autobot_shared "
        f"symlink target ({src!r}); it escapes the live tree under any deploy-root relocation (#13539/B4)."
    )


@pytest.mark.parametrize("site_id, task_file, task_name, dest, src", _SITE_SPECS, ids=_SITE_IDS)
def test_the_symlink_resolves_to_its_sibling_under_an_unrelated_root(
    site_id: str, task_file: Path, task_name: str, dest: str, src: str, tmp_path: Path
) -> None:
    """The resolved-target proof: real symlink, real os.path.realpath, a root
    that is deliberately NOT /opt/autobot."""
    assert _resolves_inside_sibling(dest, src, tmp_path), (
        f"{task_file.relative_to(_REPO_ROOT)}::{task_name!r} -- src={src!r} does not resolve to the "
        f"autobot_shared sibling of its own dest under a relocated root (#13539/B4)."
    )


@pytest.mark.parametrize("site_id, task_file, task_name, dest, src", _SITE_SPECS, ids=_SITE_IDS)
def test_the_absolute_form_would_have_failed_this_check(
    site_id: str, task_file: Path, task_name: str, dest: str, src: str, tmp_path: Path
) -> None:
    """Contrast mutation: restore the pre-#13539 absolute `src:` for this exact
    site and prove the SAME resolution helper now reports an escape -- i.e. the
    green result above is not vacuous."""
    historical_src = _HISTORICAL_ABSOLUTE_SRC[site_id]
    # These sites originally rendered a template ({{ backend_install_dir }}, etc.);
    # what matters for the property is that it is ABSOLUTE, so any absolute
    # stand-in reproduces the escape this test proves.
    if not historical_src.startswith("/"):
        historical_src = "/opt/autobot/autobot_shared"
    assert not _resolves_inside_sibling(dest, historical_src, tmp_path), (
        f"{task_file.relative_to(_REPO_ROOT)}::{task_name!r} -- the historical absolute src "
        f"{historical_src!r} unexpectedly resolved inside the relocated root; the contrast "
        "mutation is not discriminating anything (#13539/B4)."
    )
