# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#11020 — gen_frontend_types._ts_type must parenthesize union members inside an
array (`List[X | None]` → `(X | null)[]`, not `X | null[]`) and render bare
containers instead of `unknown`."""

import importlib.util
from pathlib import Path
from typing import Dict, List, Optional, Set

import pytest

_GEN = Path(__file__).resolve().parents[1] / "autobot-infrastructure" / "shared" / "scripts" / "gen_frontend_types.py"


def _load():
    spec = importlib.util.spec_from_file_location("gen_frontend_types", _GEN)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize(
    "annotation,expected",
    [
        (List[Optional[int]], "(number | null)[]"),
        (List[str | None], "(string | null)[]"),
        (Set[str | None], "(string | null)[]"),
        (List[str], "string[]"),  # non-union inner stays unparenthesized
        (Optional[List[str]], "string[] | null"),
        (Optional[dict], "Record<string, unknown> | null"),
        (Optional[list], "unknown[] | null"),
        (Dict[str, int], "Record<string, number>"),
    ],
)
def test_ts_type_array_and_bare_container_rendering(annotation, expected):
    mod = _load()
    assert mod._ts_type(annotation, set()) == expected


def test_ts_array_parenthesizes_only_unions():
    mod = _load()
    assert mod._ts_array("string") == "string[]"
    assert mod._ts_array("string | null") == "(string | null)[]"
