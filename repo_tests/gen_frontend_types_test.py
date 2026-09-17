# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#11020 — gen_frontend_types._ts_type must parenthesize union members inside an
array (`List[X | None]` → `(X | null)[]`, not `X | null[]`) and render bare
containers instead of `unknown`.

#16491 — the const-map renderer: module-level dicts emitted as typed TS ``const``
maps, entries and list elements in source order, keys quoted only when they are
not identifiers, and anything it cannot render refused rather than guessed."""

import importlib.util
from enum import Enum
from typing import Dict, List, Optional, Set

import pytest
from repo_tests._paths import repo_root

_GEN = repo_root() / "autobot-infrastructure" / "shared" / "scripts" / "gen_frontend_types.py"


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


class _Color(str, Enum):
    RED = "red"
    DARK_BLUE = "dark-blue"


def _spec(mod, **overrides):
    fields = {
        "source": "pkg/mod.py",
        "attr": "M",
        "ts_name": "M",
        "key_type": "Color",
        "value_type": "readonly string[]",
    }
    fields.update(overrides)
    return mod.ConstMap(**fields)


def test_const_map_keeps_order_quotes_non_identifier_keys_and_renders_empty_lists():
    mod = _load()
    out = mod._render_const_map(_spec(mod), {_Color.RED: ["b", _Color.RED], _Color.DARK_BLUE: []}, "pkg.mod")
    assert out == (
        "/** Generated from `pkg.mod.M` */\n"
        "export const M: Readonly<Record<Color, readonly string[]>> = {\n"
        "  red: [\n"
        "    'b',\n"
        "    'red',\n"
        "  ],\n"
        "  'dark-blue': [],\n"
        "};\n"
    )


def test_const_map_projects_one_field_of_dict_values():
    mod = _load()
    spec = _spec(mod, ts_name="RANK", value_type="number", field="priority")
    out = mod._render_const_map(spec, {_Color.RED: {"priority": 10, "description": "not emitted"}}, "pkg.mod")
    assert out == (
        "/** Generated from `pkg.mod.M` (field `priority`) */\n"
        "export const RANK: Readonly<Record<Color, number>> = {\n"
        "  red: 10,\n"
        "};\n"
    )


@pytest.mark.parametrize("value", [None, {"nested": 1}, "it's", "back\\slash", 1j])
def test_const_map_refuses_a_value_it_cannot_render(value):
    mod = _load()
    with pytest.raises(SystemExit):
        mod._render_const_map(_spec(mod), {_Color.RED: [value]}, "pkg.mod")


def test_const_map_refuses_a_missing_projected_field_and_a_non_dict_source():
    mod = _load()
    with pytest.raises(SystemExit):
        mod._render_const_map(_spec(mod, field="priority"), {_Color.RED: {"other": 1}}, "pkg.mod")
    with pytest.raises(SystemExit):
        mod._render_const_map(_spec(mod), [("red", [])], "pkg.mod")


def test_const_manifest_emits_the_role_maps_the_frontend_consumes():
    mod = _load()
    assert [(spec.attr, spec.ts_name, spec.field) for spec in mod.CONST_MANIFEST] == [
        ("ROLE_PERMISSIONS", "ROLE_PERMISSIONS", None),
        ("_ROLE_META", "ROLE_PRIORITY", "priority"),
    ]


@pytest.mark.parametrize(
    "path,expected",
    [
        ("autobot-backend/services/workflow_automation/models.py", "services.workflow_automation.models"),
        ("autobot_shared/auth/permissions.py", "autobot_shared.auth.permissions"),
    ],
)
def test_display_module_matches_the_committed_generated_comments(path, expected):
    assert _load()._display_module(path) == expected
