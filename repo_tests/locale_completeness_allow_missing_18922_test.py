# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The locale-completeness gate follows the English-only ruling (#18922).

``--allow-missing`` (the main app): a key only in en.json falls back to English and passes.
Stale orphans and object/string shape drift fail in both modes. Strict mode (the SLM's
generated locales, #14781) still fails on a missing key.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from repo_tests._paths import repo_root

_SCRIPT = repo_root() / "autobot-frontend" / "scripts" / "check-locale-completeness.py"
_LANGS = ["ar", "de", "es", "fa", "fr", "he", "lv", "pl", "pt", "ur"]
_EN = {"a": "A", "group": {"b": "B", "new": "N"}}
_COMPLETE = {"a": "a*", "group": {"b": "b*", "new": "n*"}}


def _run(tmp_path: Path, locale: dict, *flags: str) -> subprocess.CompletedProcess:
    (tmp_path / "en.json").write_text(json.dumps(_EN), encoding="utf-8")
    for lang in _LANGS:
        (tmp_path / f"{lang}.json").write_text(json.dumps(locale), encoding="utf-8")
    cmd = [sys.executable, str(_SCRIPT), "--locales", str(tmp_path), *flags]
    return subprocess.run(cmd, capture_output=True, text=True, check=False)


def test_a_complete_set_passes_in_both_modes(tmp_path):
    assert _run(tmp_path, _COMPLETE).returncode == 0
    assert _run(tmp_path, _COMPLETE, "--allow-missing").returncode == 0


def test_a_new_english_only_key_passes_with_allow_missing_and_fails_strict(tmp_path):
    english_only = {"a": "a*", "group": {"b": "b*"}}  # group.new exists only in en.json
    assert _run(tmp_path, english_only, "--allow-missing").returncode == 0
    strict = _run(tmp_path, english_only)
    assert strict.returncode == 1 and "MISSING" in strict.stderr


@pytest.mark.parametrize("flags", [(), ("--allow-missing",)], ids=["strict", "allow-missing"])
def test_a_stale_orphan_fails_in_both_modes(tmp_path, flags):
    orphan = {**_COMPLETE, "gone": "old text"}
    result = _run(tmp_path, orphan, *flags)
    assert result.returncode == 1 and "gone (not in en.json)" in result.stderr


@pytest.mark.parametrize("flags", [(), ("--allow-missing",)], ids=["strict", "allow-missing"])
def test_an_object_versus_string_mismatch_fails_in_both_modes(tmp_path, flags):
    mismatch = {"a": "a*", "group": "flattened"}
    result = _run(tmp_path, mismatch, *flags)
    assert result.returncode == 1 and "group (object vs string)" in result.stderr


def test_the_main_app_runs_the_gate_with_allow_missing():
    scripts = json.loads((repo_root() / "autobot-frontend" / "package.json").read_text(encoding="utf-8"))["scripts"]
    assert "--allow-missing" in scripts["check:locales"]


def test_the_slm_keeps_strict_parity():
    scripts = json.loads((repo_root() / "autobot-slm-frontend" / "package.json").read_text(encoding="utf-8"))["scripts"]
    assert "--allow-missing" not in scripts["check:locales"]
