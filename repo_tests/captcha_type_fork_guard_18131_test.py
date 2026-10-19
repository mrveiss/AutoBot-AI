#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#18131 -- one CAPTCHA taxonomy, found by MEMBER SET rather than by name.

`services/captcha_solver.py` and `agents/browser/captcha_solver.py` each declared a
`CaptchaType` with different members, so a kind one could classify landed as UNKNOWN in the
other. The name-based symbol-fork ratchet saw the name clash but not the disagreement; this
guard probes members, so a rival under a fresh name still fails.
"""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path

import pytest
from repo_tests._paths import repo_root
from repo_tests._reach import ReachFloorError, declare

from autobot_shared.paths import scrubbed_git_env
from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

SCANNED_ROOTS = ("autobot-backend", "autobot_shared")
CANONICAL = "autobot_shared/captcha_types.py::CaptchaType"

#: Two of these in one enum is a CAPTCHA taxonomy, whatever the class is called.
PROBE = frozenset({"RECAPTCHA", "HCAPTCHA"})

#: Kinds the two former enums supported; none may be lost (the `text_image` spelling is an alias).
FORMER_KINDS = frozenset({"TEXT", "MATH", "IMAGE_SELECT", "SLIDER", "RECAPTCHA", "HCAPTCHA", "CLOUDFLARE", "UNKNOWN"})


def _discover(root: Path) -> list[str]:
    try:
        every = tracked_paths(root, "*.py")
    except EmptyEnumeration:
        return []
    prefixes = tuple(f"{r}/" for r in SCANNED_ROOTS)
    return [rel for rel in every if rel.startswith(prefixes)]


REACH = declare(
    "captcha-type-fork-scan",
    discover=_discover,
    floor=5_010,  # re-pinned mid-window (train 31): population 5160, window [4860, 5160]
    growth=300,
    roots=SCANNED_ROOTS,
    what="tracked Python files scanned for a re-declared CAPTCHA taxonomy",
)


def _members(node: ast.ClassDef) -> frozenset[str]:
    return frozenset(
        t.id
        for stmt in node.body
        if isinstance(stmt, ast.Assign)
        for t in stmt.targets
        if isinstance(t, ast.Name) and not t.id.startswith("_")
    )


def _taxonomies(root: Path) -> tuple[list[str], int]:
    """(`path::Class` of every class whose members include the probe, files parsed)."""
    found: list[str] = []
    parsed = 0
    for rel in REACH.examined(root):
        try:
            tree = ast.parse((root / rel).read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError, OSError):
            continue
        parsed += 1
        found += [f"{rel}::{n.name}" for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and PROBE <= _members(n)]
    return found, parsed


def test_exactly_one_captcha_taxonomy_exists() -> None:
    root = repo_root()
    REACH.verify_floor(root)
    found, parsed = _taxonomies(root)
    REACH.completed(parsed)
    assert found == [CANONICAL], f"a second CAPTCHA-type enum appeared (or the canonical moved): {found}"


def _result_classes(root: Path) -> tuple[list[str], int]:
    """`path::Class` of every class annotating both `success` and `captcha_type`: a CAPTCHA result."""
    found: list[str] = []
    parsed = 0
    for rel in REACH.examined(root):
        try:
            tree = ast.parse((root / rel).read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError, OSError):
            continue
        parsed += 1
        for n in ast.walk(tree):
            if isinstance(n, ast.ClassDef):
                fields = {
                    s.target.id for s in n.body if isinstance(s, ast.AnnAssign) and isinstance(s.target, ast.Name)
                }
                if {"success", "captcha_type"} <= fields:
                    found.append(f"{rel}::{n.name}")
    return found, parsed


def test_exactly_one_captcha_result_class_exists() -> None:
    root = repo_root()
    REACH.verify_floor(root)
    found, parsed = _result_classes(root)
    REACH.completed(parsed)
    assert found == ["autobot_shared/captcha_types.py::CaptchaSolveResult"]


def test_an_empty_tree_fails_the_scan_instead_of_passing_it(tmp_path: Path) -> None:
    """A scan that reached nothing must refuse, not report 'no second class'."""
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True, env=scrubbed_git_env())
    with pytest.raises(ReachFloorError):
        _result_classes(tmp_path)
    with pytest.raises(ReachFloorError):
        _taxonomies(tmp_path)


def test_canonical_carries_every_former_kind() -> None:
    from autobot_shared.captcha_types import CaptchaType

    assert FORMER_KINDS <= {m.name for m in CaptchaType}


def test_legacy_text_image_wire_value_resolves_to_text() -> None:
    from autobot_shared.captcha_types import CaptchaType

    assert CaptchaType("text_image") is CaptchaType.TEXT
    assert CaptchaType("slider") is CaptchaType.SLIDER
    assert CaptchaType("cloudflare") is CaptchaType.CLOUDFLARE
