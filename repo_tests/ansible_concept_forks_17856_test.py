# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Three ansible settings that each had two owners, now one (#17856).

| Setting          | The one authority                                                        |
|------------------|--------------------------------------------------------------------------|
| backend_workers  | `roles/backend/defaults` (4) + `group_vars/slm.yml` (1); the deadlock playbook may force 1 |
| ai_stack_port    | `inventory/group_vars/all.yml` (8080); 11434 is Ollama, a different service |
| single-worker unit | none: the canonical backend unit renders with `backend_workers=1`      |

The detectors read text line by line against a contrast fixture, so prose that names a setting
without assigning it is not a definition.
"""

from __future__ import annotations

import functools
import re

import pytest
from repo_tests._paths import repo_root
from repo_tests._reach import declare

from tools.lint._comment_syntax import code_lines
from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

_ANSIBLE = "autobot-slm-backend/ansible"
_AI_STACK_PORT = "8080"
_SUFFIXES = (".yml", ".yaml", ".j2", ".sh")

_WORKERS_KEY = re.compile(r"^\s*backend_workers\s*:\s*\S")
_AI_PORT_LITERAL = re.compile(
    r"^\s*(?:backend_)?ai_stack_port\s*:\s*[\"']?\d+"  # yaml: ai_stack_port: 8080
    r"|^\s*ai_stack\s*:\s*[\"']?\d+"  # yaml: ports.ai_stack: 8080
    r"|\bai_stack_port\s*\|\s*default\(\s*\d+"  # jinja fallback: ai_stack_port | default(8080)
    r"|AI_STACK_PORT=[\"']?\d+"  # shell / env: AUTOBOT_AI_STACK_PORT=8080
    r"|AI_STACK_PORT:-\d+"  # shell fallback
    r"|AI_STACK_HOST[^\"\n]*\}:8080\b"  # shell: ${AUTOBOT_AI_STACK_HOST:-localhost}:8080
)
_SINGLE_UNIT_REF = re.compile(r"single-worker\.service\.j2")


def _defines_backend_workers(text: str) -> bool:
    """True when a yaml line assigns `backend_workers` (at any indent; comments don't count)."""
    return any(_WORKERS_KEY.match(line) for line in text.splitlines())


def _ai_stack_port_literals(text: str) -> list[str]:
    """Lines that restate the AI-stack port as a number instead of referencing `ai_stack_port`."""
    return [line.strip() for _lineno, line in code_lines(text, name="x.yml") if _AI_PORT_LITERAL.search(line)]


def _references_single_worker_unit(text: str) -> bool:
    return any(_SINGLE_UNIT_REF.search(line) for _lineno, line in code_lines(text, name="x.yml"))


@pytest.mark.parametrize(
    ("probe", "fork", "clean"),
    [
        (
            _defines_backend_workers,
            "backend_user: a\nbackend_workers: 1  # #876\n",
            "# backend_workers is not set here\nx: 1\n",
        ),
        (
            _defines_backend_workers,
            "  vars:\n    backend_workers: 4\n",
            "  vars:\n    backend_workers_note: 4\n# backend_workers: 4\n",
        ),
        (
            lambda t: bool(_ai_stack_port_literals(t)),
            '    ai_stack_port: "8080"\n',
            '    ai_stack_port: "{{ ai_stack_port }}"\n# ai_stack_port: 8080\nollama_port: 11434\n',
        ),
        (
            lambda t: bool(_ai_stack_port_literals(t)),
            "url: http://h:{{ ai_stack_port | default(8080) }}/health\n",
            "url: http://h:{{ ai_stack_port }}/health\n",
        ),
        (
            lambda t: bool(_ai_stack_port_literals(t)),
            "AUTOBOT_AI_STACK_PORT=8080\n",
            "AUTOBOT_AI_STACK_PORT=${AUTOBOT_AI_STACK_PORT}\n",
        ),
        (
            lambda t: bool(_ai_stack_port_literals(t)),
            'check "${AUTOBOT_AI_STACK_HOST:-localhost}:8080"\n',
            'check "${AUTOBOT_AI_STACK_HOST:-localhost}:${AUTOBOT_AI_STACK_PORT}"\n',
        ),
        (
            _references_single_worker_unit,
            "    src: templates/autobot-backend-single-worker.service.j2\n",
            "# the single-worker.service.j2 is retired\n",
        ),
    ],
)
def test_each_detector_tells_a_second_definition_from_prose(probe, fork: str, clean: str) -> None:
    assert probe(fork) is True
    assert probe(clean) is False


def _population(root) -> list[str]:
    try:
        tracked = tracked_paths(root, _ANSIBLE)
    except EmptyEnumeration:
        return []
    return [rel for rel in tracked if rel.endswith(_SUFFIXES)]


REACH = declare(
    "ansible-concept-forks-17856-scan",
    discover=_population,
    # Mid-window, from REACH.window(); the arithmetic is on the PR, not here.
    floor=451,  # mid-window: population 466, window (436, 466)
    what="ansible yaml, template and shell files",
    roots=(_ANSIBLE,),
    growth=30,
)


@functools.lru_cache(maxsize=1)
def _texts() -> dict[str, str]:
    root = repo_root()
    return {rel: (root / rel).read_text(encoding="utf-8", errors="replace") for rel in REACH.examined(root)}


def test_no_play_level_vars_file_sets_backend_workers() -> None:
    offenders = [r for r, t in _texts().items() if "/playbooks/vars/" in r and _defines_backend_workers(t)]
    assert (
        offenders == []
    ), f"#17856: {offenders} shadow roles/backend/defaults and group_vars/slm.yml; delete the line."


_AI_PORT_HOME = f"{_ANSIBLE}/inventory/group_vars/all.yml"
_SSOT_DEFAULT = re.compile(r"aistack:\s*int\s*=\s*Field\(default=(\d+),\s*alias=\"AUTOBOT_AI_STACK_PORT\"")


def test_the_ai_stack_port_is_a_number_in_exactly_one_ansible_file() -> None:
    homes = {r: b for r, t in _texts().items() if (b := _ai_stack_port_literals(t))}
    assert list(homes) == [_AI_PORT_HOME], f"#17856: the port is restated in {sorted(homes)}; reference ai_stack_port."
    assert homes[_AI_PORT_HOME] == [f"ai_stack_port: {_AI_STACK_PORT}"]


def test_the_ansible_port_equals_the_runtime_ssot_default() -> None:
    """The two literals cannot be one without new machinery, so a test keeps them equal."""
    source = (repo_root() / "autobot_shared/ssot_config.py").read_text(encoding="utf-8")
    match = _SSOT_DEFAULT.search(source)
    assert match is not None, "ssot_config.port.aistack field not found; update this guard"
    assert match.group(1) == _AI_STACK_PORT


def test_no_single_worker_unit_template_or_reference_remains() -> None:
    names = [r for r in _texts() if r.endswith("single-worker.service.j2")]
    refs = [r for r, t in _texts().items() if _references_single_worker_unit(t)]
    assert (names, refs) == ([], []), "#17856: render the canonical backend unit with backend_workers=1 instead."
