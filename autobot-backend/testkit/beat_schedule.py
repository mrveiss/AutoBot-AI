# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``celery_app.py``'s beat schedule, read from its source for tests (#22280).

The root conftest stubs ``celery_app`` (#7766), so ``celery_app.conf.beat_schedule`` is empty under
pytest and a test that reads it sees nothing scheduled. This reads the literal assignment by AST instead.
"""

from __future__ import annotations

import ast
from pathlib import Path

_CELERY_APP = Path(__file__).resolve().parents[1] / "celery_app.py"
_TARGET = "celery_app.conf.beat_schedule"


def _text(node: ast.AST) -> str:
    """A string constant's value; any other expression as its source text."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return ast.unparse(node)


def _entries(schedule: ast.Dict) -> dict[str, dict[str, str]]:
    return {
        key.value: {_text(k): _text(v) for k, v in zip(entry.keys, entry.values) if k is not None}
        for key, entry in zip(schedule.keys, schedule.values)
        if isinstance(key, ast.Constant) and isinstance(entry, ast.Dict)
    }


def beat_schedule_entries() -> dict[str, dict[str, str]]:
    """Entry name -> ``{"task": <task name>, "schedule": <source of the schedule expression>, ...}``."""
    tree = ast.parse(_CELERY_APP.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Assign) and isinstance(node.value, ast.Dict)):
            continue
        if any(ast.unparse(target) == _TARGET for target in node.targets):
            return _entries(node.value)
    raise AssertionError(f"celery_app.py has no literal {_TARGET} assignment")
