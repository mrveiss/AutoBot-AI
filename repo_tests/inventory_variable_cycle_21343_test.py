# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""No Ansible variable can template itself, directly or through an inventory `ansible_host` (#21343).

Ansible resolves a variable whole: looking up `infrastructure` templates the entire dict. So when
`infrastructure.urls` read `infrastructure.hosts.*`, the lookup recursed until Python gave up
("recursive loop detected in template string"), and the SLM play's nginx task died on the first
update that carried the guarded host expressions (#21399). Before that the recursion was hidden:
an unguarded `groups['vnc_nodes'][0]` left `infrastructure` undefined and the role fell back to a
literal. The same loop is possible through `ansible_host` if an inventory ever defines it in terms
of `infrastructure.*`, because `infrastructure.hosts.*` reads `hostvars[...]['ansible_host']`.

CI does not execute Ansible; this builds the reference graph from group_vars, role defaults/vars and
every inventory as YAML (names read as `x`, `vars['x']` and `lookup('vars','x')`) and fails on any cycle.
A missing or non-mapping source fails, and floors bound how little it may examine. Mutation check: make a url in `infrastructure` read `infrastructure.hosts`, or give
an inventory host `ansible_host: "{{ infrastructure.hosts.slm }}"`, and a test below goes red.
"""

from __future__ import annotations

import re

import yaml
from repo_tests._paths import repo_root
from repo_tests._reach import declare

_ROOT = repo_root()
_ANSIBLE = _ROOT / "autobot-slm-backend" / "ansible"

#: Floors on the number of SOURCE FILES read (shrink guards; the variable and reference floors are the
#: `declare(...)` calls below, because they bound a sweep of the tree).
_MIN_VAR_FILES = 40
_MIN_INVENTORY_FILES = 5
_JINJA = re.compile(r"\{\{(.*?)\}\}|\{%(.*?)%\}", re.S)
_NAME = re.compile(r"(?<![\w.'\"])([A-Za-z_]\w*)")
#: `vars['x']`, `vars["x"]` and `lookup('vars', 'x')` read a variable by NAME, which `_NAME` cannot see.
_BY_NAME = re.compile(r"""(?:\bvars\[\s*|lookup\(\s*['"]vars['"]\s*,\s*)['"](\w+)['"]""")
_ANSIBLE_HOST = "ansible_host"


def _load(path) -> dict:
    """A source that is missing or not a mapping FAILS the guard: a quiet `{}` would shrink the sweep."""
    assert path.is_file(), f"{path}: expected source file is missing"
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict), f"{path}: expected a YAML mapping, got {type(loaded).__name__}"
    return loaded


def _strings(node):
    """Every string inside a YAML value."""
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for value in node.values():
            yield from _strings(value)
    elif isinstance(node, list):
        for value in node:
            yield from _strings(value)


def _references(value, known: set[str]) -> set[str]:
    """Known variable names a value's templates read; `hostvars[..]['ansible_host']` counts as `ansible_host`."""
    found: set[str] = set()
    for text in _strings(value):
        for match in _JINJA.finditer(text):
            expr = match.group(1) or match.group(2) or ""
            found |= set(_NAME.findall(expr)) & known
            found |= set(_BY_NAME.findall(expr)) & known
            if f"['{_ANSIBLE_HOST}']" in expr or f'["{_ANSIBLE_HOST}"]' in expr:
                found.add(_ANSIBLE_HOST)
    return found


def _ansible_host_values(node):
    if isinstance(node, dict):
        for key, value in node.items():
            if key == _ANSIBLE_HOST:
                yield value
            else:
                yield from _ansible_host_values(value)
    elif isinstance(node, list):
        for value in node:
            yield from _ansible_host_values(value)


def _graph(group_var_docs: list[dict], inventory_docs: list[dict]) -> dict[str, set[str]]:
    known = {name for doc in group_var_docs for name in doc} | {_ANSIBLE_HOST}
    graph: dict[str, set[str]] = {name: set() for name in known}
    for doc in group_var_docs:
        for name, value in doc.items():
            graph[name] |= _references(value, known)
    for doc in inventory_docs:
        for value in _ansible_host_values(doc):
            graph[_ANSIBLE_HOST] |= _references(value, known)
    return graph


def _cycle_from(graph: dict[str, set[str]], start: str) -> list[str] | None:
    stack, on_path, done = [start], {start}, set()

    def walk(node: str) -> list[str] | None:
        for nxt in sorted(graph.get(node, ())):
            if nxt in on_path:
                return [*stack[stack.index(nxt) :], nxt]
            if nxt in done:
                continue
            stack.append(nxt)
            on_path.add(nxt)
            found = walk(nxt)
            if found:
                return found
            stack.pop()
            on_path.discard(nxt)
        done.add(node)
        return None

    return walk(start)


def _cycles(graph: dict[str, set[str]]) -> list[list[str]]:
    return [c for name in sorted(graph) if (c := _cycle_from(graph, name))]


def _sources(root) -> tuple[list, list]:
    """(variable files, inventory files) under *root*; empty lists when the tree has none."""
    ansible = root / "autobot-slm-backend" / "ansible"
    variables = sorted(ansible.glob("inventory/group_vars/*.yml"))
    variables += sorted(ansible.glob("roles/*/defaults/*.yml")) + sorted(ansible.glob("roles/*/vars/*.yml"))
    inventories = sorted(ansible.glob("inventory/*.yml"))
    inventories += [ansible / "inventory.yml"] if (ansible / "inventory.yml").is_file() else []
    return variables, inventories


def _graph_of(root) -> dict[str, set[str]]:
    variables, inventories = _sources(root)
    return _graph([_load(p) for p in variables], [_load(p) for p in inventories])


def _repo_graph() -> dict[str, set[str]]:
    return _graph_of(_ROOT)


def _variables(root) -> list[str]:
    return sorted(_graph_of(root)) if _sources(root)[0] else []


def _reference_pairs(root) -> list[str]:
    graph = _graph_of(root) if _sources(root)[0] else {}
    return sorted(f"{src} -> {dst}" for src, targets in graph.items() for dst in targets)


#: MEASURED 2026-11-13 against this tree: 744 variable names (every group_vars / role defaults / role vars
#: top-level key, plus the `ansible_host` pseudo-node) and 198 references between them. `growth` is about 8%
#: and 15% of those: a new role default or group var moves them on unrelated PRs, so they are not pinned to
#: equality. Items are names and pairs, not paths, so there is no `roots=` (recorded in `_reach_unscoped`).
VARIABLES = declare(
    "inventory-variable-cycle-variables-21343",
    discover=_variables,
    floor=700,
    growth=60,
    what="Ansible variables in group_vars and role defaults/vars",
)
REFERENCES = declare(
    "inventory-variable-cycle-references-21343",
    discover=_reference_pairs,
    floor=180,
    growth=30,
    what="references between Ansible variables",
)


def _edges(graph: dict[str, set[str]]) -> int:
    return sum(len(targets) for targets in graph.values())


def test_the_sweep_reaches_what_it_claims_to() -> None:
    """Reach before findings: an empty or shrunken walk must fail, not pass."""
    graph = _repo_graph()
    variables, inventories = _sources(_ROOT)
    assert len(variables) >= _MIN_VAR_FILES, "variable files examined fell below the floor"
    assert len(inventories) >= _MIN_INVENTORY_FILES, "inventory files examined fell below the floor"
    VARIABLES.examined(_ROOT)
    REFERENCES.examined(_ROOT)
    VARIABLES.completed(len(graph))
    REFERENCES.completed(_edges(graph))
    assert "infrastructure_hosts" in graph["infrastructure"], "known edge infrastructure -> infrastructure_hosts"
    assert (
        "model_storage_directories" in graph["model_storage"]
    ), "known edge model_storage -> model_storage_directories"


def test_no_variable_in_the_inventory_sources_can_reach_itself() -> None:
    cycles = _cycles(_repo_graph())
    assert not cycles, f"variables that template themselves: {[' -> '.join(c) for c in cycles]}"


def test_the_infrastructure_urls_read_the_flat_host_and_port_variables() -> None:
    """The one edge that mattered: urls must not read back into `infrastructure`."""
    doc = _load(_ANSIBLE / "inventory" / "group_vars" / "infrastructure.yml")
    urls = doc["infrastructure"]["urls"]
    assert urls, "expected service urls"
    assert not [u for u in urls.values() if "infrastructure." in u], urls
    assert doc["infrastructure"]["hosts"] == doc["infrastructure_hosts"]
    assert doc["infrastructure"]["ports"] == doc["infrastructure_ports"]


def test_the_host_expressions_still_fall_back_when_a_group_is_absent() -> None:
    """The #21399 contract survives: every templated entry is guarded by `groups.get(<same group>)`."""
    hosts = _load(_ANSIBLE / "inventory" / "group_vars" / "infrastructure.yml")["infrastructure_hosts"]
    for key, value in hosts.items():
        if "{{" in str(value):
            group = re.search(r"groups\['(\w+)'\]\[0\]", value).group(1)
            assert f"if groups.get('{group}') else" in value, key


def test_the_detector_flags_the_self_reference_that_broke_the_slm_play() -> None:
    broken = {"infrastructure": {"hosts": {"slm": "x"}, "urls": {"backend": "{{ infrastructure.hosts.backend }}"}}}
    assert _cycles(_graph([broken], []))


def test_the_detector_flags_the_model_storage_shape_and_by_name_reads() -> None:
    broken = {"model_storage": {"categories": {"a": {"path": "{{ model_storage.directories.base_dir }}/a"}}}}
    assert _cycles(_graph([broken], []))
    by_name = {"x": {"y": "{{ vars['x'] }}"}}
    assert _cycles(_graph([by_name], []))
    assert _cycles(_graph([{"x": "{{ lookup('vars', 'x') }}"}], []))
    fixed = {
        "model_storage_directories": {"base_dir": "/d"},
        "model_storage": {"p": "{{ model_storage_directories.base_dir }}"},
    }
    assert not _cycles(_graph([fixed], []))


def test_the_detector_flags_a_cycle_through_ansible_host() -> None:
    hosts = {"infrastructure": {"hosts": {"slm": "{{ hostvars[groups['slm'][0]]['ansible_host'] }}"}}}
    inventory = {"all": {"hosts": {"n": {"ansible_host": "{{ infrastructure.hosts.slm }}"}}}}
    assert _cycles(_graph([hosts], [inventory]))
    assert not _cycles(_graph([hosts], [{"all": {"hosts": {"n": {"ansible_host": "198.51.100.7"}}}}]))
