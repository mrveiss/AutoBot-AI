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

CI does not execute Ansible; this builds the reference graph from the sources as text/YAML and
fails on any cycle. Mutation check: make a url in `infrastructure` read `infrastructure.hosts`, or give
an inventory host `ansible_host: "{{ infrastructure.hosts.slm }}"`, and a test below goes red.
"""

from __future__ import annotations

import re

import pytest
from repo_tests._paths import repo_root

yaml = pytest.importorskip("yaml")

_ANSIBLE = repo_root() / "autobot-slm-backend" / "ansible"
_GROUP_VARS = sorted((_ANSIBLE / "inventory" / "group_vars").glob("*.yml"))
_INVENTORIES = sorted((_ANSIBLE / "inventory").glob("*.yml")) + [_ANSIBLE / "inventory.yml"]
_JINJA = re.compile(r"\{\{(.*?)\}\}|\{%(.*?)%\}", re.S)
_NAME = re.compile(r"(?<![\w.'\"])([A-Za-z_]\w*)")
_ANSIBLE_HOST = "ansible_host"


def _load(path) -> dict:
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    return loaded if isinstance(loaded, dict) else {}


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


def _repo_graph() -> dict[str, set[str]]:
    return _graph([_load(p) for p in _GROUP_VARS], [_load(p) for p in _INVENTORIES if p.is_file()])


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


def test_the_detector_flags_a_cycle_through_ansible_host() -> None:
    hosts = {"infrastructure": {"hosts": {"slm": "{{ hostvars[groups['slm'][0]]['ansible_host'] }}"}}}
    inventory = {"all": {"hosts": {"n": {"ansible_host": "{{ infrastructure.hosts.slm }}"}}}}
    assert _cycles(_graph([hosts], [inventory]))
    assert not _cycles(_graph([hosts], [{"all": {"hosts": {"n": {"ansible_host": "198.51.100.7"}}}}]))
