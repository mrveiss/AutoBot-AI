# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""How `/problems` narrows what it reads (#20493)."""

from enum import Enum
from typing import Dict, List

FILE_CATEGORY_FIELD = "file_category"


class ProblemCategory(str, Enum):
    """``code`` and ``test`` select that category; ``all`` applies no filter.

    Rows written before categories existed carry no ``file_category`` and are read as ``code``.
    """

    CODE = "code"
    TEST = "test"
    ALL = "all"


def problem_where(source_id: str | None, problem_type: str | None, category: str | None) -> Dict:
    """Chroma ``where`` for problem rows.

    ``test`` is pushed down because only rows that carry the field can match it.
    ``code`` is not: legacy rows without the field count as ``code`` and a ``where``
    cannot match a missing key, so it is applied by ``select_category`` after the read.
    """
    clauses: List[Dict] = [{"type": "problem"}]
    if source_id:
        clauses.append({"source_id": source_id})
    if problem_type:
        clauses.append({"problem_type": problem_type})
    if category == ProblemCategory.TEST.value:
        clauses.append({FILE_CATEGORY_FIELD: category})
    return {"$and": clauses} if len(clauses) > 1 else clauses[0]


def select_category(problems: List[Dict], category: str | None) -> List[Dict]:
    """Keep one category's findings; ``None`` and ``all`` keep everything."""
    if not category or category == ProblemCategory.ALL.value:
        return problems
    return [p for p in problems if p.get(FILE_CATEGORY_FIELD, "code") == category]
