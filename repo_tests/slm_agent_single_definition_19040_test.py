# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""`class SLMAgent` is defined once, in autobot-slm-backend/slm/agent/ (#19040, #18548).

Four copies once drifted from the canonical agent: a mirror under the role's files/ (#18548), a
standalone script, and two playbooks that embedded the class in a `content:` block. Each wrote a
heartbeat the nodes router answered with 401. The role now deploys the one source tree, so a
definition anywhere else is a fork.

Python files are matched by AST (a docstring or string that merely names the class is not a
definition); YAML and Jinja are matched as text, because the class lives inside a `content:`
scalar there. A `.py` file that does not parse falls back to the text match rather than being
skipped.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Iterator
from pathlib import Path

import yaml
from repo_tests._paths import repo_root
from repo_tests._reach import declare

from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

_ROOT = repo_root()
_CANONICAL = "autobot-slm-backend/slm/agent/"
_CANONICAL_FILE = f"{_CANONICAL}agent.py"
_CLASS = "SLMAgent"
_TEXT_DEFINITION = re.compile(r"^\s*class\s+SLMAgent\b", re.MULTILINE)
_SUFFIXES = (".py", ".yml", ".yaml", ".j2")
_SKIP_PARTS = frozenset({"__pycache__", "node_modules", ".worktrees", "venv", ".venv"})


def _candidates(root: Path) -> list[str]:
    try:
        paths = tracked_paths(root, *(f"*{suffix}" for suffix in _SUFFIXES))
    except EmptyEnumeration:
        return []
    # Skip dirs are matched on the repo-RELATIVE parts: a checkout that itself lives under
    # `.worktrees` must not skip every file and read as clean (#18972).
    return [p for p in paths if not _SKIP_PARTS & set(Path(p).parts)]


REACH = declare(
    "slm-agent-single-definition-19040",
    discover=_candidates,
    floor=7612,  # mid-window: population 7813 (py 7163, yml 471, yaml 70, j2 109), window [7413, 7813]
    growth=400,
    what="tracked .py/.yml/.yaml/.j2 files",
)


def _yaml_strings(node: object) -> Iterator[str]:
    """Every decoded string in a parsed YAML document, keys and values (escapes resolved)."""
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for key, value in node.items():
            yield from _yaml_strings(key)
            yield from _yaml_strings(value)
    elif isinstance(node, (list, tuple)):
        for item in node:
            yield from _yaml_strings(item)


def _defined_in_yaml_scalar(text: str) -> bool:
    """A quoted scalar's `\\n` is an escape, so the raw text has no line start; decode it first."""
    try:
        documents = list(yaml.safe_load_all(text))
    except yaml.YAMLError:
        return False  # Jinja or otherwise unparsable: the raw-text match stands alone
    return any(_TEXT_DEFINITION.search(s) for doc in documents for s in _yaml_strings(doc))


def defines_slm_agent(rel: str, text: str) -> bool:
    """True when *text*, the content of repo-relative *rel*, defines `class SLMAgent`."""
    if rel.endswith(".py"):
        try:
            tree = ast.parse(text)
        except (SyntaxError, ValueError):
            return bool(_TEXT_DEFINITION.search(text))
        return any(isinstance(n, ast.ClassDef) and n.name == _CLASS for n in ast.walk(tree))
    if _TEXT_DEFINITION.search(text):
        return True
    return rel.endswith((".yml", ".yaml")) and _defined_in_yaml_scalar(text)


def offenders(files: dict[str, str]) -> list[str]:
    """Every path except the canonical ``agent.py`` that defines the class -- a sibling in the same dir too."""
    return sorted(rel for rel, text in files.items() if rel != _CANONICAL_FILE and defines_slm_agent(rel, text))


def test_no_file_outside_the_canonical_tree_defines_slm_agent() -> None:
    files = {}
    for rel in REACH.examined(_ROOT):
        try:
            files[rel] = (_ROOT / rel).read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue  # binary asset; carries no class definition
    assert offenders(files) == [], f"a second SLMAgent definition forks the agent; deploy {_CANONICAL} instead"


def test_the_canonical_definition_is_found_and_not_flagged() -> None:
    canonical = (_ROOT / _CANONICAL_FILE).read_text(encoding="utf-8")
    assert defines_slm_agent(_CANONICAL_FILE, canonical), "the detector no longer sees the real class"
    assert offenders({_CANONICAL_FILE: canonical}) == []


def test_a_planted_copy_is_caught_in_every_form() -> None:
    py = "class SLMAgent:\n    pass\n"
    nested = "def build():\n    class SLMAgent(object):\n        pass\n"
    yml = "- copy:\n    content: |\n      class SLMAgent:\n          pass\n"
    j2 = "# {{ managed }}\nclass SLMAgent:\n    pass\n"
    unparsable = "class SLMAgent(:\n"
    quoted = 'tasks:\n  - copy:\n      content: "class SLMAgent:\\n    pass\\n"\n'
    planted = {
        "scripts/a.py": py,
        "scripts/b.py": nested,
        "ansible/c.yml": yml,
        "ansible/d.yaml": yml,
        "ansible/e.py.j2": j2,
        "scripts/f.py": unparsable,
        "ansible/i.yml": quoted,
        "ansible/j.yaml": quoted.replace("class SLMAgent:", "  class SLMAgent:"),
    }
    assert offenders(planted) == sorted(planted)


def test_a_sibling_in_the_canonical_directory_is_caught() -> None:
    """Only the canonical agent.py is exempt; another module beside it is still a fork."""
    sibling = f"{_CANONICAL}legacy.py"
    assert offenders({_CANONICAL_FILE: "class SLMAgent:\n    pass\n", sibling: "class SLMAgent:\n    pass\n"}) == [
        sibling
    ]


def test_a_mention_is_not_a_definition() -> None:
    mention = '"""Replaces the class SLMAgent copy."""\nOTHER = "class SLMAgent:"\nclass SLMAgentHelper:\n    pass\n'
    quoted_mention = 'tasks:\n  - copy:\n      content: "the SLMAgent copy was removed\\nsee class SLMAgentHelper\\n"\n'
    assert (
        offenders({"scripts/g.py": mention, "docs/h.yml": "# see class SLMAgentHelper\n", "docs/k.yml": quoted_mention})
        == []
    )
