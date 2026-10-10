# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Contrast cases for the response-model secret guard (#17865).

Each case pairs a route that must be REPORTED with one that must be clean, so
neither matching rule can pass by being inert: path-aware `response_model_exclude`
and per-module resolution of the constant it names.
"""

from __future__ import annotations

from pathlib import Path

from repo_tests.no_secret_in_response_model_17865_test import _build_index, _violations

_PROVIDER = "class Provider(BaseModel):\n    api_key: str | None = None\n"
_OUTER = "class Outer(BaseModel):\n    api_key: str | None = None\n    providers: list[Provider] = []\n"
_MODELS = "autobot-slm-backend/models/s.py"
_ROUTES = "autobot-slm-backend/api/r.py"


def _hits(tmp_path: Path, files: dict[str, str]) -> set[tuple[str, str]]:
    for rel, src in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(src, encoding="utf-8")
    return {(v[-2], v[-1]) for v in _violations(_build_index(tmp_path))}


def _outer_route(exclude: str) -> dict[str, str]:
    return {
        _MODELS: _PROVIDER + _OUTER,
        _ROUTES: f"@router.get('/x', response_model=Outer, response_model_exclude={exclude})\ndef h(): ...\n",
    }


def test_a_nested_exclusion_still_flags_the_top_level_api_key(tmp_path):
    nested = "{'providers': {'__all__': {'api_key'}}}"
    assert _hits(tmp_path, _outer_route(nested)) == {("Outer", "api_key")}


def test_a_top_level_exclusion_removes_only_the_top_level_api_key(tmp_path):
    # Reverse direction: the top-level path is excluded, the nested one is not.
    assert _hits(tmp_path, _outer_route("{'api_key'}")) == {("Outer", "api_key")}


def test_excluding_both_paths_is_clean(tmp_path):
    both = "{'api_key': True, 'providers': {'__all__': {'api_key'}}}"
    assert _hits(tmp_path, _outer_route(both)) == set()


def test_a_top_level_exclusion_on_a_flat_model_is_clean(tmp_path):
    files = {
        _MODELS: "class Flat(BaseModel):\n    api_key: str | None = None\n",
        _ROUTES: "@router.get('/x', response_model=Flat, response_model_exclude={'api_key'})\ndef h(): ...\n",
    }
    assert _hits(tmp_path, files) == set()


def _two_modules(first_set: str, second_set: str | None) -> dict[str, str]:
    route = "@router.get('/{p}', response_model={m}, response_model_exclude=_NO_KEYS)\ndef h(): ...\n"
    second = (f"_NO_KEYS = {second_set}\n" if second_set else "") + route.format(p="b", m="ModelB")
    return {
        "autobot-slm-backend/models/m.py": "class ModelA(BaseModel):\n    api_key: str | None = None\n"
        "class ModelB(BaseModel):\n    api_key: str | None = None\n",
        "autobot-slm-backend/api/a_routes.py": f"_NO_KEYS = {first_set}\n" + route.format(p="a", m="ModelA"),
        "autobot-slm-backend/api/b_routes.py": second,
    }


def test_the_same_constant_name_resolves_per_module(tmp_path):
    # A excludes api_key, B's same-named constant excludes something else.
    hits = _hits(tmp_path, _two_modules("{'api_key'}", "{'other'}"))
    assert hits == {("ModelB", "api_key")}


def test_a_module_does_not_inherit_the_constant_of_an_earlier_module(tmp_path):
    # B uses _NO_KEYS without defining it; A's set must not apply to B's route.
    hits = _hits(tmp_path, _two_modules("{'api_key'}", None))
    assert hits == {("ModelB", "api_key")}


def test_each_module_uses_its_own_constant_when_both_exclude(tmp_path):
    assert _hits(tmp_path, _two_modules("{'api_key'}", "{'api_key'}")) == set()
