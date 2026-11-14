# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every declared-egress entry still describes real code (#17576, #18229)."""

import ast
from pathlib import Path

import pytest

from autobot_shared.declared_egress import DECLARED_EGRESS

ROOT = Path(__file__).resolve().parent.parent


def _called_names(path: Path) -> list[str]:
    """Names of every function/method called in *path*, by AST (not by substring)."""
    names = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Call):
            func = node.func
            names.append(func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", ""))
    return names


def test_called_names_ignores_comments_and_strings(tmp_path) -> None:
    src = tmp_path / "m.py"
    src.write_text("# recognize_google\nx = 'recognize_google'\nr.recognize_google(a)\n", encoding="utf-8")
    assert _called_names(src) == ["recognize_google"]
    src.write_text("# recognize_google\nx = 'recognize_google'\n", encoding="utf-8")
    assert _called_names(src) == []


def test_registry_is_not_empty_and_carries_the_seed_entries() -> None:
    symbols = {(e.path, e.symbol) for e in DECLARED_EGRESS}
    assert ("autobot-backend/voice_processing/speech_recognition.py", "recognize_google") in symbols
    assert ("autobot-backend/voice_interface.py", "recognize_google") in symbols


@pytest.mark.parametrize("entry", DECLARED_EGRESS, ids=lambda e: f"{e.path}::{e.symbol}")
def test_entry_path_exists_and_symbol_still_appears(entry) -> None:
    target = ROOT / entry.path
    assert target.is_file(), f"declared egress path is gone: {entry.path} (#{entry.issue}) -- remove or move the entry"
    assert _called_names(target).count(entry.symbol), (
        f"{entry.symbol!r} is no longer CALLED in {entry.path} (a comment or string does not count): the call "
        f"was removed or renamed, so this declaration is stale (#{entry.issue}) -- remove or update it"
    )


@pytest.mark.parametrize("entry", DECLARED_EGRESS, ids=lambda e: f"{e.path}::{e.symbol}")
def test_entry_states_destination_reason_and_issue(entry) -> None:
    assert entry.destination.strip() and entry.reason.strip() and entry.issue > 0
