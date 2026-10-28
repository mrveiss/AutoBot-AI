# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tenancy is ``AUTOBOT_USER_MODE``; ``AUTOBOT_DEPLOYMENT_MODE`` is topology (#19437).

The user guide told operators to set ``AUTOBOT_DEPLOYMENT_MODE=single_user`` / ``=multi_user``.
The code reads tenancy from ``AUTOBOT_USER_MODE`` (``UserManagementMode``), so following the
docs changed nothing, and wrote an unrecognised value into the topology setting (#19187 class).

The sweep covers docs and deployment files (Markdown, env files, compose, Ansible YAML and
templates). It fails on a tenancy value assigned to ``AUTOBOT_DEPLOYMENT_MODE``, and on an
``AUTOBOT_USER_MODE`` value that is not a ``UserManagementMode`` member. Templated values
(``{{ ... }}``, ``${...}``) and comment lines are not assignments.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from repo_tests._paths import repo_root
from repo_tests._reach import declare

from tools.lint._comment_syntax import code_lines
from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

_ROOT = repo_root()
#: Shell, env and YAML files share the ``#`` comment syntax; the helper selects it by suffix.
_HASH_COMMENT_FILE = "x.sh"
_ENUM_FILE = "autobot-backend/user_management/config.py"
_PATTERNS = ("*.md", "*.env*", "*.yml", "*.yaml", "*.j2", "*.sh", "*.json", "Dockerfile*")
#: Historical records describe what was true then; they are not instructions.
_HISTORY = ("CHANGELOG.md", "changelog/", "docs/reports/", "docs/superpowers/plans/", "docs/archive/")
#: The tenancy values the docs used before #10636 retired the single-user mode.
_RETIRED = frozenset({"single_user", "multi_user"})
_ASSIGN = re.compile(r"\b(AUTOBOT_DEPLOYMENT_MODE|AUTOBOT_USER_MODE)[\"']?\s*[=:]\s*[\"'`]?([A-Za-z_]+)")
#: Prose and table rows assign nothing, yet "only when AUTOBOT_DEPLOYMENT_MODE != single_user" or a
#: table listing `single_user` as an AUTOBOT_USER_MODE value instructs the reader all the same.
_VARS = re.compile(r"\bAUTOBOT_(?:DEPLOYMENT|USER)_MODE\b")
_RETIRED_WORD = re.compile(r"\b(?:single_user|multi_user)\b")
#: 37 of the swept docs and deployment files name either variable at #19437.
MIN_MENTIONING = 25


def _swept(root: Path) -> list[str]:
    """Tracked docs and deployment files outside the history trees; ``[]`` on an empty tree."""
    try:
        paths = tracked_paths(root, *_PATTERNS)
    except EmptyEnumeration:
        return []
    return [p for p in paths if not p.startswith(_HISTORY)]


REACH = declare(
    "user-mode-values-sweep-19437",
    discover=_swept,
    floor=2170,  # measured at 2242 tracked files, pinned mid-window (#15928)
    growth=150,
    what="tracked docs and deployment files swept for a tenancy value in the wrong variable (#19437)",
)


def user_modes() -> frozenset[str]:
    """``UserManagementMode``'s values, read from its definition rather than restated."""
    tree = ast.parse((_ROOT / _ENUM_FILE).read_text(encoding="utf-8"))
    cls = next(n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name == "UserManagementMode")
    return frozenset(n.value.value for n in cls.body if isinstance(n, ast.Assign) and isinstance(n.value, ast.Constant))


def _line_findings(line: str, modes: frozenset[str]) -> list[str]:
    """What one line gets wrong: a wrong assignment, or else a retired value beside the variable."""
    hits = []
    for var, value in _ASSIGN.findall(line):
        wrong_var = var == "AUTOBOT_DEPLOYMENT_MODE" and value in modes | _RETIRED
        wrong_value = var == "AUTOBOT_USER_MODE" and value not in modes
        if wrong_var or wrong_value:
            hits.append(f"{var}={value}")
    named = _VARS.search(line)
    if not hits and named and _RETIRED_WORD.search(line):
        hits.append(f"a retired tenancy value beside {named.group(0)}")
    return hits


def misassignments(text: str, modes: frozenset[str], markdown: bool = True) -> list[str]:
    """Each ``line: finding`` in *text* that puts tenancy in the wrong variable or set.

    A ``#`` line is a comment in shell, env and YAML files; in Markdown it is a heading, and read.
    """
    lines = enumerate(text.splitlines(), 1) if markdown else code_lines(text, name=_HASH_COMMENT_FILE)
    return [f"{number}: {hit}" for number, line in lines for hit in _line_findings(line, modes)]


def test_no_doc_or_deployment_file_sets_tenancy_through_the_wrong_variable() -> None:
    paths = REACH.examined(_ROOT)
    texts = {p: (_ROOT / p).read_text(encoding="utf-8") for p in paths}
    mentioning = [p for p, t in texts.items() if _VARS.search(t)]
    assert len(mentioning) >= MIN_MENTIONING, f"only {len(mentioning)} files name the variables -- reach lost"
    modes = user_modes()
    findings = {p: misassignments(t, modes, p.endswith(".md")) for p, t in texts.items()}
    bad = [f"{p}:{hit}" for p, hits in findings.items() for hit in hits]
    assert not bad, "tenancy is AUTOBOT_USER_MODE=single_company|multi_company|provider:\n" + "\n".join(bad)


def test_the_enum_is_read_not_assumed() -> None:
    assert user_modes() == {"single_company", "multi_company", "provider"}


def test_the_old_guide_wording_is_caught() -> None:
    modes = frozenset({"single_company", "multi_company", "provider"})
    text = (
        "This message appears when `AUTOBOT_DEPLOYMENT_MODE=single_user`.\n"
        "1. Set `AUTOBOT_DEPLOYMENT_MODE=multi_user` in your environment.\n"
        "Set `AUTOBOT_DEPLOYMENT_MODE=single_company` (or higher) to enable.\n"
        "AUTOBOT_USER_MODE=single_user\n"
    )
    assert len(misassignments(text, modes)) == 4


def test_valid_and_templated_assignments_are_not_findings() -> None:
    modes = frozenset({"single_company", "multi_company", "provider"})
    text = (
        "AUTOBOT_USER_MODE=multi_company\n"
        "AUTOBOT_DEPLOYMENT_MODE=distributed\n"
        "AUTOBOT_USER_MODE={{ backend_user_mode | default('single_company') }}\n"
        "      - AUTOBOT_USER_MODE=${AUTOBOT_USER_MODE:-single_company}\n"
        "# override.conf set AUTOBOT_USER_MODE=single_user, silently disabling it\n"
    )
    assert misassignments(text, modes, markdown=False) == []


def test_prose_tables_json_and_headings_are_read() -> None:
    modes = frozenset({"single_company", "multi_company", "provider"})
    text = (
        "| `autobot` (user management, only when `AUTOBOT_DEPLOYMENT_MODE != single_user`) |\n"
        "| `AUTOBOT_USER_MODE` | `single_user`, `single_company` | User management model |\n"
        '{"AUTOBOT_USER_MODE": "multi_user"}\n'
        "### Set AUTOBOT_DEPLOYMENT_MODE=multi_company\n"
    )
    assert [hit.split(":")[0] for hit in misassignments(text, modes)] == ["1", "2", "3", "4"]
