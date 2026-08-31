# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The #15340 checkpoint-version control, pinned without importing torch (#15344).

``training/completion_trainer.py`` constrains the caller-supplied checkpoint
version before it is used to select a file. The behavioural tests for it live in
``training/completion_trainer_test.py``, which cannot run without ``torch`` and
``torchmetrics`` -- both module-level ``importorskip``s. On a box without them
that file collects **zero** tests, so nothing pins the control at all and the
pre-push hook refuses the push (#15344).

This file closes that gap by reading the source rather than importing it, so the
control is pinned everywhere the repository is checked out. It is deliberately a
*complement* to the behavioural tests, not a replacement: it proves the shape of
the guard, they prove what it does.

Three properties, each a real regression this control exists to prevent:

* ``fullmatch``, not ``match``. ``re.match`` anchors only the start, so
  ``match`` would accept ``best/../../etc/passwd`` -- the traversal the
  constraint exists to reject.
* the pattern still bounds both accepted shapes.
* the checkpoint is selected by **enumerating** the directory, not by building a
  path out of the version. Validating a string and then interpolating it is the
  weaker form; ``iterdir()`` means an unexpected value selects nothing.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

_SOURCE = Path(__file__).resolve().parents[1] / "autobot-backend" / "training" / "completion_trainer.py"
_MIN_ACCEPTED_SHAPES = 2


def _source_text() -> str:
    assert _SOURCE.is_file(), f"{_SOURCE} is missing -- this guard is pinned to the wrong path"
    return _SOURCE.read_text(encoding="utf-8")


def _version_pattern() -> str:
    """The literal handed to re.compile for _VERSION_RE, read from the AST."""
    tree = ast.parse(_source_text())
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        names = [t.id for t in node.targets if isinstance(t, ast.Name)]
        if "_VERSION_RE" not in names:
            continue
        call = node.value
        assert isinstance(call, ast.Call), "_VERSION_RE is no longer a re.compile(...) call"
        assert call.args and isinstance(call.args[0], ast.Constant), "_VERSION_RE's pattern is not a literal"
        return str(call.args[0].value)
    pytest.fail("_VERSION_RE is gone from completion_trainer.py -- the version constraint was removed")


def test_the_constraint_uses_fullmatch_not_match() -> None:
    """`match` anchors only the start, so it would accept `best/../../etc/passwd`."""
    text = _source_text()
    assert "_VERSION_RE.fullmatch(" in text, (
        "_VERSION_RE is no longer applied with fullmatch. `re.match` anchors only the "
        "start of the string, so `best/../../etc/passwd` would pass the check -- exactly "
        "the traversal this control rejects (#15340)."
    )
    assert "_VERSION_RE.match(" not in text, "_VERSION_RE.match( is present -- see above, it must be fullmatch"


def test_the_pattern_still_bounds_both_accepted_shapes() -> None:
    """Every rejection below is a real traversal or malformed value, not a style choice."""
    compiled = re.compile(_version_pattern())
    accepted = ["best", "v20260830_123456"]
    rejected = ["../etc/passwd", "best/../x", "v2026_1", "", "best ", "vXXXXXXXX_123456", "best/x"]

    assert len(accepted) >= _MIN_ACCEPTED_SHAPES, "the fixture stopped covering both documented shapes"
    wrong = [value for value in accepted if not compiled.fullmatch(value)]
    wrong += [f"{value!r} accepted" for value in rejected if compiled.fullmatch(value)]
    assert not wrong, f"the checkpoint-version pattern changed meaning: {wrong}"


def test_the_checkpoint_is_chosen_by_enumeration_not_path_construction() -> None:
    """Enumerating means an unexpected value selects nothing, rather than resolving somewhere."""
    text = _source_text()
    assert ".iterdir()" in text, (
        "the checkpoint is no longer selected by enumerating model_dir. Validating a "
        "version string and then interpolating it into a path is the weaker form -- "
        "CodeQL flagged that shape here before (#15340)."
    )
