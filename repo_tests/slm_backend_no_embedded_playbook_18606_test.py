# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""No SLM-backend Python module embeds a playbook body or agent source (#18606).

Node enrollment used to run `_ENROLLMENT_PLAYBOOK_TEMPLATE`, a whole Ansible playbook held in
a Python string, one task of which wrote a hand-written copy of `slm/agent/` onto the node. The
copy drifted from the real agent and sat outside the playbook registry and the role guards.
Enrollment now runs the tracked `ansible/playbooks/enroll-slm-agent.yml`, which calls the
`slm_agent` role.

The detector reads the syntax tree: a *string literal* with a line-anchored `hosts:` key and a
line-anchored `tasks:` key is a playbook body, and one containing `class SLMAgent` is agent
source. A comment, or code that merely names these words, is not.
"""

from __future__ import annotations

import ast
import functools
import re
from pathlib import Path

import pytest
from repo_tests._paths import repo_root
from repo_tests._reach import declare

from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

_ROOT = "autobot-slm-backend"
_HOSTS = re.compile(r"^\s*(?:-\s+)?hosts\s*:", re.MULTILINE)
_TASKS = re.compile(r"^\s*tasks\s*:", re.MULTILINE)
_AGENT_CLASS = "class SLMAgent"

#: Known remaining embedders, to be emptied, never extended. #18610: the blue/green purge play.
_KNOWN = {"autobot-slm-backend/services/purge_playbook.py": ("playbook",)}


def _embedded(source: str) -> list[str]:
    """What a module embeds in string literals: `playbook` and/or `agent`."""
    found: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
            continue
        text = node.value
        if _HOSTS.search(text) and _TASKS.search(text):
            found.add("playbook")
        if _AGENT_CLASS in text:
            found.add("agent")
    return sorted(found)


def _is_source_python(rel: str) -> bool:
    name = rel.rsplit("/", 1)[-1]
    return rel.endswith(".py") and not (name.endswith("_test.py") or name.startswith("test_") or "/tests/" in rel)


def _population(root: Path) -> list[str]:
    try:
        tracked = tracked_paths(root, _ROOT)
    except EmptyEnumeration:
        return []
    return [rel for rel in tracked if _is_source_python(rel)]


REACH = declare(
    "slm-backend-embedded-playbook-scan",
    discover=_population,
    # Mid-window, from REACH.window(); the arithmetic is on the PR, not here.
    floor=236,
    what="non-test python source in the SLM backend",
    roots=(_ROOT,),
    growth=100,
)


@pytest.mark.parametrize(
    ("label", "source", "expected"),
    [
        ("a playbook body in a string", 'T = """\n- name: x\n  hosts: all\n  tasks:\n    - ping:\n"""\n', ["playbook"]),
        ("agent source in a string", 'S = "class SLMAgent:\\n    pass"\n', ["agent"]),
        ("a tasks list with no play", 'T = "tasks:\\n  - a\\n"\n', []),
        ("a comment describing a play", "# hosts: all\n# tasks:\nx = 1\n", []),
        ("the agent class as code", "class SLMAgent:\n    pass\n", []),
        ("a mapping with those keys", 'd = {"hosts": 1, "tasks": 2}\n', []),
    ],
)
def test_the_matcher_tells_an_embedded_body_from_a_mention(label: str, source: str, expected: list[str]) -> None:
    assert _embedded(source) == expected, label


@functools.lru_cache(maxsize=1)
def _offenders() -> tuple[tuple[str, tuple[str, ...]], ...]:
    out = []
    for rel in REACH.examined(repo_root()):
        kinds = _embedded((repo_root() / rel).read_text(encoding="utf-8"))
        if kinds:
            out.append((rel, tuple(kinds)))
    return tuple(out)


def test_the_real_agent_is_a_control_the_matcher_does_not_flag() -> None:
    """The agent module defines `class SLMAgent` as code; flagging it would make the scan useless."""
    source = (repo_root() / _ROOT / "slm" / "agent" / "agent.py").read_text(encoding="utf-8")
    assert _AGENT_CLASS in source
    assert _embedded(source) == []


def test_no_slm_backend_module_embeds_a_playbook_or_agent_source() -> None:
    new = {rel: kinds for rel, kinds in _offenders() if _KNOWN.get(rel) != kinds}
    assert not new, (
        f"#18606: {new} embed a playbook body or agent source in a string. Put the play in a tracked file "
        "under ansible/playbooks/ and pass variables with --extra-vars; deploy the agent through the "
        "slm_agent role. Do not add to _KNOWN."
    )


def test_a_known_embedder_that_was_fixed_leaves_the_allowance() -> None:
    """A stale allowance would hide a regression in the file it names."""
    found = dict(_offenders())
    stale = sorted(rel for rel in _KNOWN if rel not in found)
    assert not stale, f"#18610: {stale} no longer embed a playbook; delete them from _KNOWN."
