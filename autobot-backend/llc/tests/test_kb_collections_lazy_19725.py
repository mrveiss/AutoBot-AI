# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#19725: a collection appears on its first write, under the one name builder (#19519).

55 of 65 collections on a node were empty because every new work item, company and sprint made
its own. Stored names read ``work_item_<id>`` only because the KB client maps ``:`` to ``_``; code
must never build that form itself.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

_LLC = Path(__file__).resolve().parents[1]
_HAND_BUILT_NAME = re.compile(r"""f["'](?:work_item|company|project|sprint|agent)_\{[^}]*\}(?:_\w+)?["']""")
_NAME_BUILDER = _LLC / "kb" / "collections.py"


def _sources() -> list[Path]:
    return [p for p in _LLC.rglob("*.py") if "tests" not in p.parts and not p.name.endswith("_test.py")]


def _ensure_calls(source: str) -> int:
    calls = [n for n in ast.walk(ast.parse(source)) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)]
    return sum(call.func.attr == "ensure_collection" for call in calls)


def test_the_scan_sees_the_llc_package() -> None:
    assert len(_sources()) > 50, "the guard would be judging almost nothing"
    assert _ensure_calls("async def f(m):\n    await m.ensure_collection('a', 'b')\n") == 1
    assert _HAND_BUILT_NAME.search('x = f"work_item_{item_id}"')
    assert not _HAND_BUILT_NAME.search('x = f"company_{company_id}_template.json"'), "a download name isn't one"


def test_creating_an_entity_creates_no_collection() -> None:
    offenders = [str(p) for p in _sources() if _ensure_calls(p.read_text(encoding="utf-8"))]
    assert offenders == [], "a collection is created by its first write, not when the entity is"


def test_no_collection_name_is_built_by_hand() -> None:
    sources = [p for p in _sources() if p != _NAME_BUILDER]
    offenders = [str(p) for p in sources if _HAND_BUILT_NAME.search(p.read_text(encoding="utf-8"))]
    assert offenders == [], "use company_collection(), project_collection() and the others in llc/kb/collections.py"
