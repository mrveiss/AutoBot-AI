# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Every entry that renders a log-directory template defines its variables and creates the directory (#20894).

A template naming `AUTOBOT_LOGS_DIR={{ <service>_app_log_dir }}` is rendered by more than one entry: a role's
task files, and playbooks that template it from outside the role. Two defects are the same class:

* the variable is declared for some entries only (`backend_app_log_dir` sat in the role defaults; the playbook
  `deploy-backend-env.yml` loads no role, takes its variables from `vars/backend-env.yml`, and rendered it
  undefined);
* the directory is created on the full-provision path only, so the updater's code-only paths and an overridden
  directory left file logging off.

Both checks walk every entry, so a new renderer, or a new variable in the template, is covered without an edit here.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml
from repo_tests._paths import repo_root
from repo_tests._reach import declare
from repo_tests._template_required_names import required_names

_ROOT = repo_root()
_ANSIBLE = "autobot-slm-backend/ansible"
_ENSURE = "ensure_app_log_dir.yml"
_APP_DIR = re.compile(r"AUTOBOT_LOGS_DIR=\{\{\s*(\w+_app_log_dir)\s*\}\}")
_TEMPLATE_ACTIONS = ("ansible.builtin.template", "template")
_INCLUDE_ACTIONS = (
    "ansible.builtin.include_tasks",
    "include_tasks",
    "ansible.builtin.import_tasks",
    "import_tasks",
)
# Measured population when written: 12 (task file, template) renderings; the floor sits mid-window ([6, 12]).
_MIN_ENTRIES = 9

#: Names no entry defines because the controller supplies them: inventory structure and gathered facts.
#: `slm_backend_port` is declared once, in inventory/group_vars/all.yml (#20600), which every play sees.
_SUPPLIED = frozenset(
    {
        "autobot",
        "hostvars",
        "groups",
        "inventory_hostname",
        "ansible_host",
        "ansible_facts",
        "slm_backend_port",
    }
)


#: Variables a playbook entry renders without defining, frozen as found (#21496). SHRINKS ONLY: the test fails on a
#: name not listed here, and on a listed name that is now defined, so the entry has to leave the table.
_KNOWN_GAPS: dict[str, frozenset[str]] = {
    f"{_ANSIBLE}/playbooks/deploy-backend-env.yml": frozenset(
        {
            "backend_chromadb_auth_token",
            "backend_frontend_tls_enabled",
            "backend_prometheus_scrape_token",
            "frontend_http_port",
            "frontend_tls_port",
        }
    ),
}


def _entry_files(root: Path) -> list[Path]:
    """Every file that can hold a template task: role task files (nested too), playbooks, and the tree root's."""
    base = root / _ANSIBLE
    files = [
        p for role in sorted((base / "roles").iterdir()) if (role / "tasks").is_dir() for p in _yaml(role / "tasks")
    ]
    if (base / "playbooks").is_dir():
        files += _yml(base / "playbooks")  # not recursive: `playbooks/vars/` holds variable files, not tasks
    return files + _yml(base)


_YAML_SUFFIXES = (".yml", ".yaml")


def _yml(directory: Path) -> list[Path]:
    return sorted(p for p in directory.iterdir() if p.is_file() and p.suffix in _YAML_SUFFIXES)


def _yaml(directory: Path) -> list[Path]:
    """Task files at any depth, under either suffix: a renderer in `tasks/env/main.yml` or `env.yaml` is an entry."""
    return sorted(p for p in directory.rglob("*") if p.is_file() and p.suffix in _YAML_SUFFIXES)


def _role_of(file: Path) -> Path | None:
    """The role directory a task file belongs to (at any depth under `tasks/`), else None for a playbook."""
    for parent in file.parents:
        if parent.name == "tasks" and parent.parent.parent.name == "roles":
            return parent.parent
    return None


def _walk(tasks: object) -> list[dict]:
    found: list[dict] = []
    for task in tasks if isinstance(tasks, list) else []:
        if not isinstance(task, dict):
            continue
        found.append(task)
        for key in ("block", "rescue", "always", "tasks", "pre_tasks", "post_tasks"):
            found += _walk(task.get(key))
    return found


def _docs(path: Path) -> list:
    """The YAML documents of a task file or playbook (some carry several `---` documents), as one flat list."""
    docs = [d for d in yaml.safe_load_all(path.read_text(encoding="utf-8")) if d]
    return [item for doc in docs for item in (doc if isinstance(doc, list) else [doc])]


def _tasks(path: Path) -> list[dict]:
    return _walk(_docs(path))


def _action(task: dict, names: tuple[str, ...]) -> object:
    return next((task[n] for n in names if n in task), None)


def _src_path(task: dict, file: Path) -> Path | None:
    """The template file a `template:` task renders: beside the role (`templates/<src>`) or relative to the file."""
    spec = _action(task, _TEMPLATE_ACTIONS)
    if not isinstance(spec, dict) or "src" not in spec:
        return None
    src = str(spec["src"])
    role = _role_of(file)
    role_templates = role / "templates" / src if role else None
    for candidate in (role_templates, file.parent / src):
        if candidate is not None and candidate.is_file():
            return candidate.resolve()
    return None  # unresolvable (a templated name, or a role without the template): not read, and counted


def renderings(root: Path) -> list[tuple[Path, Path, str]]:
    """(entry file, template, variable) for every template task whose template sets `AUTOBOT_LOGS_DIR` to an app dir."""
    found = []
    for file in _entry_files(root):
        for task in _tasks(file):
            template = _src_path(task, file)
            match = _APP_DIR.search(template.read_text(encoding="utf-8")) if template else None
            if match:
                found.append((file, template, match.group(1)))
    return found


def _log_dir_template_names(root: Path) -> set[str]:
    """File names of the role templates that set `AUTOBOT_LOGS_DIR` to an application directory variable."""
    roles = root / _ANSIBLE / "roles"
    found = set()
    for template in roles.glob("*/templates/*") if roles.is_dir() else []:
        if template.is_file() and _APP_DIR.search(template.read_text(encoding="utf-8")):
            found.add(template.name)
    return found


def unresolvable(root: Path) -> list[str]:
    """Template tasks naming a log-directory template that is not found beside them: they render nothing readable."""
    names = _log_dir_template_names(root)
    found = []
    for file in _entry_files(root):
        for task in _tasks(file):
            spec = _action(task, _TEMPLATE_ACTIONS)
            if (
                isinstance(spec, dict)
                and Path(str(spec.get("src", ""))).name in names
                and _src_path(task, file) is None
            ):
                found.append(f"{file.relative_to(root)} -> {spec['src']}")
    return sorted(found)


#: Renderings of a log-directory template whose file does not exist where the task looks (#21496). SHRINKS ONLY:
#: a new one fails the test, and a listed one that resolves (or is removed) fails as stale.
_UNRESOLVABLE = frozenset({f"{_ANSIBLE}/roles/backend_services/tasks/main.yml -> backend.env.j2"})


REACH = declare(
    "ansible-log-dir-templates-complete-20894",
    discover=lambda root: renderings(root) if (root / _ANSIBLE).is_dir() else [],
    floor=_MIN_ENTRIES,
    growth=6,
    what="(task file, template) renderings of an AUTOBOT_LOGS_DIR template under the ansible tree",
)


def _keys(path: Path) -> set[str]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) if path.is_file() else None
    return set(data) if isinstance(data, dict) else set()


def _assigned(tasks: list[dict]) -> set[str]:
    """Names a task file sets itself: set_fact keys, `register:`, task and play `vars:`, loop variables."""
    names: set[str] = {"item"}
    for task in tasks:
        fact = _action(task, ("ansible.builtin.set_fact", "set_fact"))
        names |= {k for k in fact if k != "cacheable"} if isinstance(fact, dict) else set()
        names |= {task["register"]} if "register" in task else set()
        names |= set(task["vars"]) if isinstance(task.get("vars"), dict) else set()
        control = task.get("loop_control")
        names |= {control["loop_var"]} if isinstance(control, dict) and "loop_var" in control else set()
    return names


def _target(task: dict, path: Path) -> Path | None:
    """The task file an `include_tasks`/`import_tasks` task pulls in (None for anything else or a templated name)."""
    spec = _action(task, _INCLUDE_ACTIONS)
    name = spec.get("file") if isinstance(spec, dict) else spec
    if not isinstance(name, str) or "{{" in name:
        return None
    target = (path.parent / name).resolve()
    return target if target.is_file() else None


def _included(path: Path) -> list[Path]:
    return [t for task in _tasks(path) if (t := _target(task, path))]


def _closure(path: Path) -> set[Path]:
    seen: set[Path] = set()
    todo = [path.resolve()]
    while todo:
        current = todo.pop()
        if current not in seen:
            seen.add(current)
            todo += _included(current)
    return seen


def _assigned_in(files: set[Path]) -> set[str]:
    return set().union(*(_assigned(_tasks(f)) for f in files)) if files else set()


def _caller_names(file: Path, role: Path) -> set[str]:
    """Names set by the files that reach *file* in its role, only by what runs BEFORE the include of it.

    `main.yml` sets facts and includes `code_only.yml`: those facts are in scope there. A sibling that never
    includes the entry (or runs after it) is not on its path, so what it sets is not.
    """
    names: set[str] = set()
    seen = {file.resolve()}
    todo = [file.resolve()]
    while todo:
        current = todo.pop()
        for caller in _yaml(role / "tasks"):
            tasks = _tasks(caller)
            hits = [i for i, t in enumerate(tasks) if _target(t, caller) == current]
            if not hits or caller.resolve() in seen:
                continue
            seen.add(caller.resolve())
            before = tasks[: hits[0]]
            names |= _assigned(before)
            names |= _assigned_in({c for t in before if (x := _target(t, caller)) for c in _closure(x)})
            todo.append(caller.resolve())
    return names


def defined_for(file: Path) -> set[str]:
    """Names in scope when `file` renders: role defaults and vars, play `vars_files`/`vars`, and what its own
    include chain sets (the files it includes, and what runs before the include of it in the files that reach it)."""
    names: set[str] = set(_SUPPLIED) | _assigned_in(_closure(file))
    role = _role_of(file)
    if role:  # role defaults and vars are shared by every file of the role
        names |= _keys(role / "defaults" / "main.yml") | _keys(role / "vars" / "main.yml")
        names |= _caller_names(file, role)
    else:  # a playbook: its vars_files (relative to the playbook) and play-level vars
        for play in _docs(file):
            if not isinstance(play, dict):
                continue
            names |= set(play.get("vars") or {})
            for vars_file in play.get("vars_files") or []:
                names |= _keys((file.parent / str(vars_file)).resolve())
    return names


def undefined_for(file: Path, template: Path) -> set[str]:
    return required_names(template.read_text(encoding="utf-8")) - defined_for(file)


def gaps(entries: list[tuple[Path, Path, str]], root: Path, known: dict[str, frozenset[str]]) -> dict[str, list[str]]:
    """Per entry: the required variables it leaves undefined and no baseline row accounts for, plus stale rows."""
    out: dict[str, list[str]] = {}
    for file, template, _ in entries:
        rel = str(file.relative_to(root))
        missing = undefined_for(file, template)
        new = sorted(missing - known.get(rel, frozenset()))
        stale = sorted(f"baseline row now defined: {n}" for n in known.get(rel, frozenset()) - missing)
        if new or stale:
            out[f"{rel} -> {template.name}"] = new + stale
    return out


def test_every_entry_defines_every_variable_its_template_requires() -> None:
    """The class: a template variable an entry leaves undefined fails that entry's render at run time."""
    bad = gaps(list(REACH.examined(_ROOT)), _ROOT, _KNOWN_GAPS)
    assert not bad, f"entry(ies) render a template with variable(s) they never define (#20894, #21496): {bad}"


def test_the_known_gaps_name_real_entries() -> None:
    entries = {str(f.relative_to(_ROOT)) for f, _, _ in REACH.examined(_ROOT)}
    assert (
        set(_KNOWN_GAPS) <= entries
    ), f"baseline row(s) for entries that no longer render the template: {set(_KNOWN_GAPS) - entries}"


def test_control_the_baseline_admits_only_what_it_lists(tmp_path: Path) -> None:
    """Control: a gap in the table passes, an unlisted one fails, and a listed name that is defined is stale."""
    base = tmp_path / _ANSIBLE
    _plant(
        base,
        {
            "roles/r/templates/t.env.j2": _TEMPLATE,
            "roles/r/tasks/main.yml": _RENDER.format(src="t.env.j2"),
        },
    )
    entries = renderings(tmp_path)
    rel = f"{_ANSIBLE}/roles/r/tasks/main.yml"
    listed = {rel: frozenset({"known", "svc_app_log_dir"})}
    assert gaps(entries, tmp_path, listed) == {}
    assert gaps(entries, tmp_path, {rel: frozenset({"known"})}) == {f"{rel} -> t.env.j2": ["svc_app_log_dir"]}
    assert gaps(entries, tmp_path, {rel: frozenset({"known", "svc_app_log_dir", "gone"})}) == {
        f"{rel} -> t.env.j2": ["baseline row now defined: gone"]
    }


def _ensured(file: Path) -> set[str]:
    """Variables a file passes to the shared directory task as `app_log_dir`."""
    found: set[str] = set()
    for task in _tasks(file):
        spec = _action(task, _INCLUDE_ACTIONS)
        target = spec.get("file") if isinstance(spec, dict) else spec
        value = (task.get("vars") or {}).get("app_log_dir") if isinstance(target, str) else None
        if isinstance(target, str) and target.endswith(_ENSURE) and isinstance(value, str):
            found |= set(re.findall(r"\{\{\s*(\w+)\s*\}\}", value))
    return found


def test_every_entry_that_renders_a_log_dir_template_also_ensures_the_directory() -> None:
    """The class: a path that installs or restarts the unit but never creates the directory it logs to."""
    missing = sorted(
        f"{f.relative_to(_ROOT)} -> {var}" for f, _, var in REACH.examined(_ROOT) if var not in _ensured(f)
    )
    assert not missing, f"entry(ies) render AUTOBOT_LOGS_DIR templates without {_ENSURE} for the directory: {missing}"


def test_the_shared_task_creates_the_directory_with_become_on_the_inner_task() -> None:
    shared = _ROOT / _ANSIBLE / "_shared" / "tasks" / _ENSURE
    (task,) = _tasks(shared)
    assert task["become"] is True
    assert task["ansible.builtin.file"]["state"] == "directory"


def _plant(root: Path, files: dict[str, str]) -> None:
    for rel, body in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(body, encoding="utf-8")


_TEMPLATE = "A={{ known }}\nB={{ guarded | default('x') }}\nAUTOBOT_LOGS_DIR={{ svc_app_log_dir }}\n"
_RENDER = "- ansible.builtin.template:\n    src: {src}\n    dest: /x\n"


def test_control_a_variable_defined_nowhere_is_reported_and_each_source_clears_it(
    tmp_path: Path,
) -> None:
    """Control: an undefined template variable fails; a role default, a vars file or a set_fact each define it."""
    base = tmp_path / _ANSIBLE
    _plant(
        base,
        {
            "roles/r/templates/t.env.j2": _TEMPLATE,
            "roles/r/tasks/main.yml": _RENDER.format(src="t.env.j2"),
        },
    )
    (entry,) = renderings(tmp_path)
    file, template, var = entry
    assert var == "svc_app_log_dir"
    assert undefined_for(file, template) == {
        "known",
        "svc_app_log_dir",
    }  # `guarded` carries a default: not required
    _plant(base, {"roles/r/defaults/main.yml": "known: 1\nsvc_app_log_dir: /l\n"})
    assert undefined_for(file, template) == set()
    (base / "roles/r/defaults/main.yml").unlink()
    facts = "- set_fact:\n    known: 1\n    svc_app_log_dir: /l\n"
    _plant(base, {"roles/r/tasks/main.yml": facts + _RENDER.format(src="t.env.j2")})
    assert undefined_for(file, template) == set()


def test_control_a_playbook_is_complete_only_through_its_vars_file(
    tmp_path: Path,
) -> None:
    """Control: the playbook case from #20894 -- no role loaded, so only `vars_files` can define the variable."""
    base = tmp_path / _ANSIBLE
    play = (
        "- hosts: all\n  vars_files:\n    - vars/p.yml\n  tasks:\n"
        "    - ansible.builtin.template:\n        src: ../roles/r/templates/t.env.j2\n        dest: /x\n"
    )
    _plant(
        base,
        {
            "roles/r/templates/t.env.j2": _TEMPLATE,
            "playbooks/p.yml": play,
            "playbooks/vars/p.yml": "known: 1\n",
        },
    )
    file, template, _ = renderings(tmp_path)[0]
    assert undefined_for(file, template) == {"svc_app_log_dir"}
    _plant(base, {"playbooks/vars/p.yml": "known: 1\nsvc_app_log_dir: /l\n"})
    assert undefined_for(file, template) == set()


def test_control_an_entry_without_the_shared_directory_task_is_reported(
    tmp_path: Path,
) -> None:
    base = tmp_path / _ANSIBLE
    _plant(
        base,
        {
            "roles/r/templates/t.env.j2": _TEMPLATE,
            "roles/r/tasks/main.yml": _RENDER.format(src="t.env.j2"),
        },
    )
    file, _, var = renderings(tmp_path)[0]
    assert var not in _ensured(file)
    include = (
        "- ansible.builtin.include_tasks:\n    file: ../../../_shared/tasks/ensure_app_log_dir.yml\n"
        '  vars:\n    app_log_dir: "{{ svc_app_log_dir }}"\n'
    )
    _plant(base, {"roles/r/tasks/main.yml": include + _RENDER.format(src="t.env.j2")})
    assert var in _ensured(file)
    other = include.replace("svc_app_log_dir", "another_dir")  # ensuring a different directory does not count
    _plant(base, {"roles/r/tasks/main.yml": other + _RENDER.format(src="t.env.j2")})
    assert var not in _ensured(file)


def test_every_unresolvable_rendering_is_listed_and_every_listed_one_still_is() -> None:
    """A renderer whose template file is missing is reported, not skipped: a new one fails, a fixed one is stale."""
    found = frozenset(unresolvable(_ROOT))
    assert found == _UNRESOLVABLE, f"new: {sorted(found - _UNRESOLVABLE)}; stale: {sorted(_UNRESOLVABLE - found)}"


def test_control_a_template_task_without_its_template_is_reported(tmp_path: Path) -> None:
    """Control: `src` names a log-directory template that the task's role does not ship."""
    base = tmp_path / _ANSIBLE
    _plant(base, {"roles/r/templates/t.env.j2": _TEMPLATE, "roles/r/tasks/main.yml": _RENDER.format(src="t.env.j2")})
    _plant(base, {"roles/other/tasks/main.yml": _RENDER.format(src="t.env.j2")})
    _plant(base, {"roles/other/tasks/unrelated.yml": _RENDER.format(src="not-a-log-template.j2")})
    assert unresolvable(tmp_path) == [f"{_ANSIBLE}/roles/other/tasks/main.yml -> t.env.j2"]


def test_control_a_nested_or_yaml_renderer_is_an_entry_and_needs_the_directory_task(tmp_path: Path) -> None:
    """Control: a renderer in `tasks/env/main.yml` or `tasks/env.yaml` is discovered; a top-level one still is."""
    base = tmp_path / _ANSIBLE
    _plant(base, {"roles/r/templates/t.env.j2": _TEMPLATE, "roles/r/tasks/main.yml": "- debug: {}\n"})
    assert renderings(tmp_path) == []  # near miss: a role that renders nothing has no entry
    _plant(base, {"roles/r/tasks/env/main.yml": _RENDER.format(src="t.env.j2")})
    _plant(base, {"roles/r/tasks/env.yaml": _RENDER.format(src="t.env.j2")})
    found = sorted(str(f.relative_to(tmp_path)) for f, _, _ in renderings(tmp_path))
    assert found == [f"{_ANSIBLE}/roles/r/tasks/env.yaml", f"{_ANSIBLE}/roles/r/tasks/env/main.yml"]
    assert all("svc_app_log_dir" not in _ensured(f) for f, _, _ in renderings(tmp_path))


def test_control_only_the_entrys_own_include_chain_defines_names(tmp_path: Path) -> None:
    """Control: a sibling that sets the variable counts only when the entry includes it, or the file that reaches
    the entry sets it before including it."""
    base = tmp_path / _ANSIBLE
    render = _RENDER.format(src="t.env.j2")
    _plant(base, {"roles/r/templates/t.env.j2": _TEMPLATE, "roles/r/tasks/env_only.yml": render})
    _plant(base, {"roles/r/tasks/sibling.yml": "- set_fact:\n    known: 1\n    svc_app_log_dir: /l\n"})
    file, template, _ = renderings(tmp_path)[0]
    assert undefined_for(file, template) == {"known", "svc_app_log_dir"}  # the unreferenced sibling does not count
    inc = "- include_tasks: {}\n"
    _plant(base, {"roles/r/tasks/env_only.yml": inc.format("sibling.yml") + render})  # the entry includes it
    assert undefined_for(file, template) == set()
    _plant(base, {"roles/r/tasks/env_only.yml": render})
    _plant(
        base,
        {"roles/r/tasks/main.yml": "- set_fact:\n    known: 1\n    svc_app_log_dir: /l\n" + inc.format("env_only.yml")},
    )
    assert undefined_for(file, template) == set()  # the caller sets them before including the entry
    _plant(
        base,
        {"roles/r/tasks/main.yml": inc.format("env_only.yml") + "- set_fact:\n    known: 1\n    svc_app_log_dir: /l\n"},
    )
    assert undefined_for(file, template) == {"known", "svc_app_log_dir"}  # set only AFTER the include: not in scope
