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

    violations = checker._assert_baseline_only_shrinks(set())

    assert any(name in v for v in violations)


def test_nothing_is_reported_when_the_baseline_matches(checker):
    assert checker._assert_baseline_only_shrinks(set(checker._UNREGISTERED_BASELINE)) == []
