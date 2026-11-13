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
from jinja2 import Environment, nodes
from repo_tests._paths import repo_root
from repo_tests._reach import declare

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
_MIN_ENTRIES = 12  # live count when written: 12 (task file, template) renderings; a drop means discovery broke

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
            "autobot_admin_password",
            "backend_chromadb_auth_token",
            "backend_frontend_tls_enabled",
            "backend_postgres_password",
            "backend_prometheus_scrape_token",
            "frontend_http_port",
            "frontend_tls_port",
            "tls_ca_cert",
        }
    ),
}


def _entry_files(root: Path) -> list[Path]:
    """Every file that can hold a template task: role task files, playbooks, and the playbooks at the tree root."""
    base = root / _ANSIBLE
    files = [
        p for role in sorted((base / "roles").iterdir()) if (role / "tasks").is_dir() for p in _yml(role / "tasks")
    ]
    if (base / "playbooks").is_dir():
        files += _yml(base / "playbooks")
    return files + _yml(base)


def _yml(directory: Path) -> list[Path]:
    return sorted(p for p in directory.iterdir() if p.is_file() and p.suffix == ".yml")


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
    role_templates = file.parent.parent / "templates" / src if file.parent.name == "tasks" else None
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


def _included(path: Path) -> list[Path]:
    out = []
    for task in _tasks(path):
        spec = _action(task, _INCLUDE_ACTIONS)
        name = spec.get("file") if isinstance(spec, dict) else spec
        target = (path.parent / str(name)).resolve() if isinstance(name, str) and "{{" not in name else None
        if target is not None and target.is_file():
            out.append(target)
    return out


def _closure(path: Path) -> set[Path]:
    seen: set[Path] = set()
    todo = [path.resolve()]
    while todo:
        current = todo.pop()
        if current not in seen:
            seen.add(current)
            todo += _included(current)
    return seen


def defined_for(file: Path) -> set[str]:
    """Names in scope when `file` renders: role defaults and vars, play `vars_files`/`vars`, and what its tasks set."""
    names: set[str] = set(_SUPPLIED)
    files = _closure(file)
    if file.parent.name == "tasks":  # a role entry: every task file of the role shares its defaults and facts
        role = file.parent.parent
        names |= _keys(role / "defaults" / "main.yml") | _keys(role / "vars" / "main.yml")
        files |= {c for sibling in _yml(file.parent) for c in _closure(sibling)}
    else:  # a playbook: its vars_files (relative to the playbook) and play-level vars
        for play in _docs(file):
            if not isinstance(play, dict):
                continue
            names |= set(play.get("vars") or {})
            for vars_file in play.get("vars_files") or []:
                names |= _keys((file.parent / str(vars_file)).resolve())
    for f in files:
        names |= _assigned(_tasks(f))
    return names


def required_names(text: str) -> set[str]:
    """Variables the template cannot render without: undeclared, and read somewhere without a `default`/`is defined`."""
    tree = Environment().parse(
        text
    )  # parsing needs no filter table; `meta.find_undeclared_variables` compiles and does
    undeclared = {n.name for n in tree.find_all(nodes.Name) if n.ctx == "load"} - {
        n.name for n in tree.find_all(nodes.Name) if n.ctx == "store"  # `{% set %}` and `{% for %}` targets
    }
    tested: set[str] = set()
    parents: dict[int, nodes.Node] = {}
    for parent in tree.find_all(nodes.Node):
        for child in parent.iter_child_nodes():
            parents[id(child)] = parent
    unguarded: set[str] = set()
    for name in tree.find_all(nodes.Name):
        if name.name not in undeclared:
            continue
        parent = parents.get(id(name))
        is_default = isinstance(parent, nodes.Filter) and parent.name in ("default", "d") and parent.node is name
        is_test = isinstance(parent, nodes.Test) and parent.name == "defined" and parent.node is name
        if is_test:
            tested.add(name.name)
        elif not is_default:
            unguarded.add(name.name)
    return unguarded - tested  # a name tested `is defined` is optional: its other reads sit under that test


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
