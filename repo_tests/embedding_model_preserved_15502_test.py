# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""An update never silently changes a deployed embedding model (#15502).

The backend env template defaults AUTOBOT_EMBEDDING_MODEL for FRESH installs only; every render
site first runs the shared read task so a value already on the host wins. A different model means
a different vector space and dimension (see knowledge/index_embedding_space.py, #18185/#18217), so
switching an existing deployment is a re-index proposal, never a template default.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml
from repo_tests._paths import repo_root
from repo_tests._reach import declare

from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

_ANS = "autobot-slm-backend/ansible"
_READ = f"{_ANS}/_shared/tasks/read_deployed_embedding_model.yml"
_INCLUDE = "read_deployed_embedding_model.yml"
_VAR = "AUTOBOT_EMBEDDING_MODEL"
_TEMPLATE_TASKS = ("template", "ansible.builtin.template")
_INCLUDE_TASKS = ("include_tasks", "ansible.builtin.include_tasks", "import_tasks", "ansible.builtin.import_tasks")
_CHILD_LISTS = ("block", "rescue", "always", "tasks", "pre_tasks", "post_tasks", "handlers")


def _probe_script(files: list[str]) -> str:
    task = yaml.safe_load((repo_root() / _READ).read_text(encoding="utf-8"))[0]
    return task["ansible.builtin.shell"]["cmd"].replace(
        "{{ deployed_embedding_env_files | join(' ') }}", " ".join(files)
    )


def _probe(files: list[str]) -> str:
    out = subprocess.run(["bash", "-c", _probe_script(files)], capture_output=True, text=True, check=True)
    return out.stdout.strip()


def test_a_deployed_value_is_read_back_so_it_is_preserved(tmp_path) -> None:
    env = tmp_path / "backend.env"
    env.write_text("FOO=1\nAUTOBOT_EMBEDDING_MODEL=phi3:mini\n", encoding="utf-8")
    assert _probe([str(env)]) == "phi3:mini"


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ('AUTOBOT_EMBEDDING_MODEL="phi3:mini"\n', "phi3:mini"),
        ("AUTOBOT_EMBEDDING_MODEL='phi3:mini'\n", "phi3:mini"),
        ("A=1\r\nAUTOBOT_EMBEDDING_MODEL=phi3:mini\r\n", "phi3:mini"),
        ('AUTOBOT_EMBEDDING_MODEL="phi3:mini"\r\n', "phi3:mini"),
        ("export AUTOBOT_EMBEDDING_MODEL=phi3:mini\n", "phi3:mini"),
        ("# AUTOBOT_EMBEDDING_MODEL=commented\nOTHER_AUTOBOT_EMBEDDING_MODEL=x\n", ""),
        ("AUTOBOT_EMBEDDING_MODEL=\n", ""),
    ],
)
def test_the_probe_strips_quotes_crlf_and_export(tmp_path, content: str, expected: str) -> None:
    env = tmp_path / "x.env"
    env.write_bytes(content.encode("utf-8"))
    assert _probe([str(env)]) == expected


def test_the_first_file_that_carries_a_value_wins(tmp_path) -> None:
    empty, a, b = tmp_path / "e.env", tmp_path / "a.env", tmp_path / "b.env"
    empty.write_text("AUTOBOT_EMBEDDING_MODEL=\n", encoding="utf-8")
    a.write_text("AUTOBOT_EMBEDDING_MODEL=model-a\n", encoding="utf-8")
    b.write_text("AUTOBOT_EMBEDDING_MODEL=model-b\n", encoding="utf-8")
    assert _probe([str(tmp_path / "missing.env"), str(empty), str(a), str(b)]) == "model-a"


def test_a_fresh_host_reads_nothing_so_the_canonical_default_applies(tmp_path) -> None:
    assert _probe([str(tmp_path / "absent.env")]) == ""


def test_the_adopt_task_only_fires_on_a_non_empty_read() -> None:
    tasks = yaml.safe_load((repo_root() / _READ).read_text(encoding="utf-8"))
    task = next(t for t in tasks if "ansible.builtin.set_fact" in t)
    assert task["ansible.builtin.set_fact"] == {"backend_embedding_model": "{{ _embedding_model_probe.stdout | trim }}"}
    assert any("length > 0" in cond for cond in task["when"])


# --- discovery: EVERY render of a template carrying the variable preserves it ----------------


def _ansible_yaml(root: Path) -> list[str]:
    try:
        return [p for p in tracked_paths(root, _ANS) if p.endswith((".yml", ".yaml"))]
    except EmptyEnumeration:
        return []


REACH_RENDERS = declare(
    "embedding-model-render-sites",
    discover=_ansible_yaml,
    # Mid-window (292..342), from REACH_RENDERS.window(); the arithmetic is on the PR, not here.
    floor=317,
    what="ansible yml/yaml files, scanned for tasks rendering a template that carries AUTOBOT_EMBEDDING_MODEL",
    roots=(_ANS,),
    growth=50,
)


def _templates_carrying_the_variable(root: Path) -> set[str]:
    """Basenames of every .j2 under the ansible tree that names the variable (grep the variable, not a template)."""
    try:
        tracked = tracked_paths(root, _ANS)
    except EmptyEnumeration:
        return set()
    return {
        Path(p).name
        for p in tracked
        if p.endswith(".j2") and _VAR in (root / p).read_text(encoding="utf-8", errors="replace")
    }


def _task_arg(task: dict, keys: tuple[str, ...]):
    return next((task[k] for k in keys if k in task), None)


def _renders(task: dict, templates: set[str]) -> bool:
    arg = _task_arg(task, _TEMPLATE_TASKS)
    src = arg.get("src", "") if isinstance(arg, dict) else ""
    return bool(arg) and any(t in str(src) for t in templates)


def _includes_read(task: dict) -> bool:
    arg = _task_arg(task, _INCLUDE_TASKS)
    return _INCLUDE in (arg.get("file", "") if isinstance(arg, dict) else str(arg or ""))


def _unprotected(tasks: list, templates: set[str], seen: bool = False) -> list[str]:
    """Names of render tasks with no read include earlier in their own list or an enclosing one."""
    bad: list[str] = []
    for task in tasks:
        if not isinstance(task, dict):
            continue
        seen = seen or _includes_read(task)
        if _renders(task, templates) and not seen:
            bad.append(str(task.get("name", "<unnamed>")))
        for key in _CHILD_LISTS:
            if isinstance(task.get(key), list):
                bad += _unprotected(task[key], templates, seen)
    return bad


def _plays_or_tasks(doc) -> list:
    return doc if isinstance(doc, list) else []


def _unprotected_in_text(text: str, templates: set[str]) -> list[str]:
    return _unprotected(_plays_or_tasks(yaml.safe_load(text)), templates)


def _scan(root: Path) -> tuple[dict[str, list[str]], int]:
    """(file -> unprotected render tasks, number of render tasks seen). A file naming a target template
    that cannot be parsed is an error, never silently skipped."""
    templates = _templates_carrying_the_variable(root)
    found: dict[str, list[str]] = {}
    renders = 0
    for rel in REACH_RENDERS.examined(root):
        text = (root / rel).read_text(encoding="utf-8", errors="replace")
        if not any(t in text for t in templates):
            continue
        tasks = _plays_or_tasks(yaml.safe_load(text))
        renders += _count_renders(tasks, templates)
        if bad := _unprotected(tasks, templates):
            found[rel] = bad
    return found, renders


def _count_renders(tasks: list, templates: set[str]) -> int:
    total = 0
    for task in tasks:
        if isinstance(task, dict):
            total += _renders(task, templates)
            for key in _CHILD_LISTS:
                if isinstance(task.get(key), list):
                    total += _count_renders(task[key], templates)
    return total


def test_the_variable_is_carried_by_the_known_template_only() -> None:
    assert _templates_carrying_the_variable(repo_root()) == {"backend.env.j2"}


def test_every_render_of_a_template_carrying_the_variable_reads_the_deployed_value_first() -> None:
    found, renders = _scan(repo_root())
    assert renders >= 5, f"discovery went vacuous: only {renders} render task(s) seen"
    assert found == {}, f"#15502: these renders can replace a deployed embedding model: {found}"


_T = {"backend.env.j2"}
_READ_TASK = {"ansible.builtin.include_tasks": "../_shared/tasks/read_deployed_embedding_model.yml"}
_RENDER = {"name": "render", "ansible.builtin.template": {"src": "roles/backend/templates/backend.env.j2", "dest": "x"}}


def test_a_second_render_without_its_own_read_is_flagged() -> None:
    text = yaml.safe_dump(
        [
            {"name": "read", **_READ_TASK},
            _RENDER,
            {"name": "other", "debug": {}},
            {**_RENDER, "name": "second", "template": {"src": "backend.env.j2"}},
        ]
    )
    assert _unprotected_in_text(text, _T) == []  # an earlier read covers later siblings
    own_play = [
        {"hosts": "a", "tasks": [{"name": "read", **_READ_TASK}, _RENDER]},
        {"hosts": "b", "tasks": [{**_RENDER, "name": "second"}]},
    ]
    assert _unprotected(own_play, _T) == ["second"]


def test_a_new_file_with_no_read_is_flagged_and_a_read_in_a_block_is_honoured() -> None:
    assert _unprotected([_RENDER], _T) == ["render"]
    assert _unprotected([{"block": [{"name": "r", **_READ_TASK}, _RENDER]}], _T) == []
    assert _unprotected([_RENDER, {"name": "late", **_READ_TASK}], _T) == ["render"]
    assert _unprotected([{"name": "unrelated", "ansible.builtin.template": {"src": "other.conf.j2"}}], _T) == []
    assert _unprotected([{"name": "via-var", "template": {"src": "{{ tpl }}/backend.env.j2"}}], _T) == ["via-var"]
