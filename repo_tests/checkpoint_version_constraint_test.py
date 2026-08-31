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


def _tree() -> ast.Module:
    return ast.parse(_source_text())


def _version_re_assignments(tree: ast.Module) -> list[ast.expr]:
    """Every assignment to _VERSION_RE, so shadowing fails loudly rather than silently."""
    found: list[ast.expr] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "_VERSION_RE" for t in node.targets
        ):
            found.append(node.value)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id == "_VERSION_RE" and node.value is not None:
                found.append(node.value)
    return found


def _compiled_version_re() -> re.Pattern[str]:
    """The real pattern AND its flags -- reading one without the other judges a copy."""
    assignments = _version_re_assignments(_tree())
    if not assignments:
        pytest.fail("_VERSION_RE is gone from completion_trainer.py -- the version constraint was removed")
    assert len(assignments) == 1, (
        f"_VERSION_RE is assigned {len(assignments)} times. A later assignment shadows the first, and this "
        "guard would judge a pattern that is not the one bound at import."
    )
    call = assignments[0]
    assert isinstance(call, ast.Call), "_VERSION_RE is no longer a re.compile(...) call"
    args = list(call.args) + [kw.value for kw in call.keywords]
    assert args and isinstance(args[0], ast.Constant), "_VERSION_RE's pattern is not a literal this guard can read"
    flags = 0
    for extra in args[1:]:
        try:
            flags |= int(eval(compile(ast.Expression(extra), "<flags>", "eval"), {"re": re}))  # noqa: S307
        except Exception:  # noqa: BLE001 - an unreadable flag must fail loudly, not be ignored
            pytest.fail(f"_VERSION_RE passes a flag this guard cannot read: {ast.dump(extra)}")
    return re.compile(str(args[0].value), flags)


def _load_checkpoint_body() -> list[ast.stmt]:
    for node in ast.walk(_tree()):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "load_checkpoint":
            return list(node.body)
    pytest.fail("load_checkpoint is gone from completion_trainer.py")


def test_a_rejected_version_actually_raises() -> None:
    """The control is the raise, not the regex. Detecting and not raising is no control at all.

    Found by review of this file's first version: replacing the ``raise`` with a
    ``logger.warning`` removed the constraint entirely and every test here still
    passed, because they all asserted on the compiled pattern. The regex is what
    decides; this is what makes the decision bite.
    """
    guards = [
        node
        for node in ast.walk(ast.Module(body=_load_checkpoint_body(), type_ignores=[]))
        if isinstance(node, ast.If)
        and any(
            isinstance(inner, ast.Attribute)
            and inner.attr in {"fullmatch", "match"}
            and isinstance(inner.value, ast.Name)
            and inner.value.id == "_VERSION_RE"
            for inner in ast.walk(node.test)
        )
    ]
    assert guards, "load_checkpoint no longer branches on _VERSION_RE -- the version is not checked at all"
    unraised = [
        g
        for g in guards
        if not any(isinstance(n, ast.Raise) for n in ast.walk(ast.Module(body=g.body, type_ignores=[])))
    ]
    assert not unraised, (
        "load_checkpoint checks the version but does not raise on rejection. A constraint that "
        "logs and continues is not a constraint -- the caller-supplied value still reaches the "
        "filesystem lookup (#15340)."
    )


def test_the_constraint_uses_fullmatch_not_match() -> None:
    """`match` anchors only the start, so it would accept `best/../../etc/passwd`."""
    calls = [
        node
        for node in ast.walk(ast.Module(body=_load_checkpoint_body(), type_ignores=[]))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "_VERSION_RE"
    ]
    assert calls, "_VERSION_RE is not called in load_checkpoint"
    wrong = sorted({c.func.attr for c in calls if c.func.attr != "fullmatch"})
    assert not wrong, (
        f"_VERSION_RE is applied with {wrong} in load_checkpoint. `re.match` anchors only the start "
        "of the string, so `best/../../etc/passwd` would pass -- exactly the traversal this rejects. "
        "Read from the AST, so a comment mentioning `.match(` cannot trip this."
    )


def test_the_pattern_still_bounds_both_accepted_shapes() -> None:
    """Every rejection below is a real traversal or malformed value, not a style choice."""
    compiled = _compiled_version_re()
    accepted = ["best", "v20260830_123456"]
    rejected = [
        "../etc/passwd",
        "best/../x",
        "v2026_1",
        "",
        "best ",
        "vXXXXXXXX_123456",
        "best/x",
        # A traversal wearing a plausible suffix: a pattern widened to `.+\.pt`
        # accepts this while still rejecting every entry above it.
        "../../etc/passwd.pt",
        "..\\..\\x",
        "best\x00",
        "v٢٠٢٦٠٨٣٠_١٢٣٤٥٦",
    ]

    wrong = [f"{v!r} rejected" for v in accepted if not compiled.fullmatch(v)]
    wrong += [f"{v!r} accepted" for v in rejected if compiled.fullmatch(v)]
    assert not wrong, f"the checkpoint-version pattern changed meaning: {wrong}"


def test_the_checkpoint_is_chosen_by_enumeration_not_path_construction() -> None:
    """Enumerating means an unexpected value selects nothing, rather than resolving somewhere."""
    body = ast.Module(body=_load_checkpoint_body(), type_ignores=[])
    enumerates = any(
        isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "iterdir"
        for node in ast.walk(body)
    )
    assert enumerates, (
        "load_checkpoint no longer enumerates the model directory. Validating a version string and "
        "then interpolating it into a path is the weaker form -- `available.get(wanted)` over "
        "`iterdir()` is what makes traversal unrepresentable. Read from the AST and scoped to this "
        "function, so a comment mentioning iterdir() elsewhere cannot satisfy it."
    )
