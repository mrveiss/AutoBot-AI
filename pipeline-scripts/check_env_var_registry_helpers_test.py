# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The env-registry checker must see every way this repo reads an env var (#14265)."""

from __future__ import annotations

import ast
import importlib.util
import textwrap
from pathlib import Path

import pytest

_MODULE = Path(__file__).with_name("check_env_var_registry.py")
_REPO_ROOT = _MODULE.resolve().parents[1]


@pytest.fixture
def checker():
    spec = importlib.util.spec_from_file_location("check_env_var_registry_14265", _MODULE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _extract(checker, tmp_path, source: str):
    target = tmp_path / "sample.py"
    target.write_text(textwrap.dedent(source), encoding="utf-8")
    return [name for _, name in checker._extract_autobot_getenv_names(target)]


def test_os_getenv_is_still_seen(checker, tmp_path):
    assert _extract(checker, tmp_path, 'import os\nx = os.getenv("AUTOBOT_A", "1")\n') == ["AUTOBOT_A"]


@pytest.mark.parametrize("helper", ["env_int", "env_flag", "env_str", "env_float", "env_int_clamped"])
def test_every_env_utils_helper_is_seen(checker, tmp_path, helper):
    """The gap this closes: 45 variables were read this way and none were checked."""
    assert _extract(checker, tmp_path, f'x = {helper}("AUTOBOT_B", 1)\n') == ["AUTOBOT_B"]


def test_the_reader_set_is_derived_not_hardcoded(checker):
    """A helper added to env_utils next year must be covered without anyone
    editing this checker — that omission is exactly what this issue is."""
    readers = checker._env_reader_names()
    declared = {
        node.name
        for node in ast.parse(
            (_REPO_ROOT / "autobot_shared" / "env_utils.py").read_text(encoding="utf-8")
        ).body
        if isinstance(node, ast.FunctionDef)
        and node.name.startswith("env_")
        and node.args.args
        and node.args.args[0].arg == "name"
    }

    assert readers == declared
    assert len(readers) >= 5


def test_a_non_env_call_is_not_matched(checker, tmp_path):
    assert _extract(checker, tmp_path, 'x = some_other("AUTOBOT_C", 1)\n') == []


def test_a_non_autobot_name_is_not_matched(checker, tmp_path):
    assert _extract(checker, tmp_path, 'x = env_int("OTHER_D", 1)\n') == []


# ---------------------------------------------------------------------------
# The baseline is a ceiling
# ---------------------------------------------------------------------------


def test_the_baseline_is_not_empty(checker):
    """An empty baseline would make the shrink assertion vacuous."""
    assert len(checker._UNREGISTERED_BASELINE) >= 40


def test_no_baselined_name_is_already_registered(checker):
    """A stranded entry exempts whatever arrives under that name next, silently."""
    already = sorted(checker._UNREGISTERED_BASELINE & set(checker.REGISTRY))

    assert already == [], f"remove these from _UNREGISTERED_BASELINE — they are registered: {already}"


def test_a_registered_baseline_entry_is_reported(checker):
    """The mechanism that keeps the list shrinking rather than rotting."""
    name = sorted(checker._UNREGISTERED_BASELINE)[0]
    checker.REGISTRY[name] = next(iter(checker.REGISTRY.values()))
    try:
        violations = checker._stale_baseline_entries()
    finally:
        del checker.REGISTRY[name]

    assert any(name in v for v in violations)


def test_nothing_is_reported_while_the_baseline_is_all_unregistered(checker):
    assert checker._stale_baseline_entries() == []


def test_the_ceiling_is_reached_from_main_not_only_by_calling_it(checker, tmp_path):
    """A guard defined and never invoked is decorative.

    The first version of this defined the check, populated a set for it, and
    never called either — while a test that invoked the function directly passed.
    This runs `main` on a file that mentions nothing, so the ONLY way a violation
    can appear is the wired-in ceiling.
    """
    import io
    import sys as _sys

    name = sorted(checker._UNREGISTERED_BASELINE)[0]
    sample = tmp_path / "empty.py"
    sample.write_text("x = 1\n", encoding="utf-8")
    checker.REGISTRY[name] = next(iter(checker.REGISTRY.values()))
    captured = io.StringIO()
    original = _sys.stderr
    _sys.stderr = captured
    try:
        checker.main([str(sample)])
    finally:
        _sys.stderr = original
        del checker.REGISTRY[name]

    # Asserting on the exit code alone is not enough: mutating REGISTRY also
    # makes the generated docs stale, so `main` returns non-zero either way and
    # the test would pass with the ceiling unwired. Assert the specific message.
    assert f"{name} is in _UNREGISTERED_BASELINE" in captured.getvalue()


def test_the_reader_set_is_parsed_once_not_per_node(checker):
    """It used to be called inside the AST walk, re-reading and re-parsing
    env_utils.py for every node of every file."""
    checker._env_reader_names.cache_clear()
    first = checker._env_reader_names()
    second = checker._env_reader_names()

    assert first is second
    assert checker._env_reader_names.cache_info().hits >= 1
